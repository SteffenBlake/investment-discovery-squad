import json
import math
import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo

from .backtesting import prepare_plan, test_rows, validate
from .configuration import instrument, reject_secrets
from .messages import alert_message
from .ledger import Store
from .util import canonical, digest, finite, instant, stamp, wilson

TRANSITIONS = {
    "DISCOVERED": {"BACKTESTED", "REJECTED", "INVALIDATED"},
    "BACKTESTED": {"QUALIFIED", "REJECTED", "INVALIDATED"},
    "FORWARD_TESTING": {"QUALIFIED", "DEGRADED", "INVALIDATED"},
    "QUALIFIED": {"ALERTED", "DEGRADED", "INVALIDATED"},
    "ALERTED": {"DEGRADED", "INVALIDATED"},
    "REJECTED": {"INVALIDATED"}, "DEGRADED": {"INVALIDATED"}, "INVALIDATED": set(),
}


class CandidateLimit(ValueError):
    pass


class Engine:
    def __init__(self, store: Store, settings):
        self.store, self.settings = store, settings
        self.blockers = []

    def _transition(self, signal_id, state, evidence):
        old = self.store.state(signal_id)
        if state not in TRANSITIONS[old]:
            raise ValueError(f"Invalid transition {old} -> {state}")
        self.store.db.execute("UPDATE signals SET state=? WHERE id=?", (state, signal_id))
        self.store.event("transition", signal_id, previous=old, state=state, evidence=evidence)

    def discover(self, spec):
        reject_secrets(spec)
        allowed = {"id", "name", "phenomenon", "mechanism", "symbol", "limitations", "horizon_days", "target_return", "article", "family_id", "input_id", "feature_formula"}
        if not isinstance(spec, dict) or set(spec) - allowed:
            raise ValueError("Unknown signal specification fields")
        for field in ("id", "name", "phenomenon", "mechanism", "symbol", "family_id", "input_id"):
            if not isinstance(spec.get(field), str) or not spec[field].strip():
                raise ValueError(f"Signal needs {field}")
        if not isinstance(spec.get("limitations"), list) or not spec["limitations"] or any(not isinstance(item, str) or not item.strip() for item in spec["limitations"]):
            raise ValueError("limitations must be a nonempty list of nonempty text")
        if "article" in spec and (not isinstance(spec["article"], str) or not spec["article"].strip()):
            raise ValueError("article must be nonempty text")
        if type(spec.get("horizon_days")) is not int or not 1 <= spec["horizon_days"] <= 90:
            raise ValueError("horizon_days must be an integer from 1 to 90")
        if type(spec.get("target_return")) not in (int, float):
            raise ValueError("target_return must be numeric")
        if not 0 < finite(spec["target_return"]) < 1:
            raise ValueError("target_return must be between 0 and 1")
        formula = spec.get('feature_formula')
        if not isinstance(formula, dict) or not isinstance(formula.get('operation'), str) or not formula['operation'].strip():
            raise ValueError('feature_formula needs a canonical operation and its parameters')
        instrument(self.settings, spec["symbol"])
        with self.store.transaction():
            existing = self.store.db.execute("SELECT data FROM specs WHERE id=?", (spec["id"],)).fetchone()
            if existing:
                if existing[0] != canonical(spec):
                    raise ValueError("Signal specification immutable; register a new version/ID")
                return False
            zone = ZoneInfo(self.settings["timezone"])
            today = instant(self.store.clock()).astimezone(zone).date()
            count = sum(instant(row[0]).astimezone(zone).date() == today for row in self.store.db.execute("SELECT at FROM specs"))
            if count >= self.settings["max_candidates_per_day"]:
                raise CandidateLimit("Daily candidate cap reached")
            self.store.db.execute("INSERT INTO specs VALUES(?,?,?)",
                                  (spec["id"], stamp(self.store.clock()), canonical(spec)))
            self.store.db.execute("INSERT INTO signals VALUES(?, 'DISCOVERED')", (spec["id"],))
            self.store.event("transition", spec["id"], previous=None, state="DISCOVERED", evidence=spec)
        return True

    def _check_premise(self, spec):
        for row in self.store.db.execute("SELECT s.id,s.data FROM specs s JOIN test_plans p ON p.signal_id=s.id WHERE s.id!=?", (spec['id'],)):
            old = json.loads(row['data'])
            same_input = old['input_id'] == spec['input_id']
            same_operation = old['feature_formula']['operation'] == spec['feature_formula']['operation']
            if same_input or old['family_id'] == spec['family_id'] and same_operation:
                raise ValueError('Same premise already planned/tested; related retry requires different measured input and formula operation')

    def prepare_test(self, signal_id, development, test_windows, *, holdout_unseen):
        reject_secrets(development)
        reject_secrets(test_windows)
        if holdout_unseen is not True:
            raise ValueError('Confirm test outcomes remain unseen during hypothesis development')
        with self.store.transaction():
            if self.store.state(signal_id) != 'DISCOVERED':
                raise ValueError('Prepare one test for a discovered hypothesis')
            if self.store.db.execute('SELECT 1 FROM test_plans WHERE signal_id=?', (signal_id,)).fetchone():
                raise ValueError('Test plan immutable; one shot per hypothesis')
            spec = self.store.spec(signal_id)
            self._check_premise(spec)
            if development.get('synthetic') and self.store.mode != 'synthetic':
                raise ValueError('Synthetic evidence prohibited in production')
            planned = self.store.db.execute("SELECT COALESCE(MAX(json_extract(data,'$.trial_number')),0) FROM test_plans").fetchone()[0]
            tested = self.store.db.execute('SELECT COALESCE(MAX(id),0) FROM trials').fetchone()[0]
            number = max(planned, tested) + 1
            plan = prepare_plan(development, spec, test_windows, self.settings, number, self.store.clock())
            for row in self.store.db.execute("""SELECT p.data FROM test_plans p JOIN specs s ON s.id=p.signal_id
              WHERE json_extract(s.data,'$.family_id')=?""", (spec['family_id'],)):
                previous = json.loads(row[0])
                if instant(test_windows[0]['entry_at']) <= instant(previous['test_windows'][-1]['exit_at']):
                    raise ValueError('Related new premise requires untouched later test history')
            self.store.db.execute('INSERT OR IGNORE INTO datasets VALUES(?,?)', (digest(development), canonical(development)))
            self.store.db.execute('INSERT INTO test_plans VALUES(?,?,?)', (signal_id, stamp(self.store.clock()), canonical(plan)))
            self.store.event('test_planned', signal_id, **plan)
        return plan

    def backtest(self, signal_id, dataset):
        reject_secrets(dataset)
        with self.store.transaction():
            if self.store.state(signal_id) != 'DISCOVERED':
                raise ValueError('One test per hypothesis; failed hypotheses remain rejected')
            saved = self.store.db.execute('SELECT data FROM test_plans WHERE signal_id=?', (signal_id,)).fetchone()
            if saved is None:
                raise ValueError('Freeze development rule and untouched test windows with prepare-test first')
            plan, spec = json.loads(saved[0]), self.store.spec(signal_id)
            try:
                rows = test_rows(dataset, spec, plan, self.store.clock())
                if dataset.get('synthetic') and self.store.mode != 'synthetic':
                    raise ValueError('Synthetic evidence prohibited in production')
                previous = self.store.db.execute("""SELECT d.data FROM trials t JOIN specs s ON s.id=t.signal_id
                  JOIN datasets d ON d.hash=t.dataset_hash WHERE json_extract(s.data,'$.symbol')=?""", (spec['symbol'],))
                for old in previous:
                    for old_row in json.loads(old[0]).get('rows', []):
                        start, end = instant(old_row['entry_at']), instant(old_row['exit_at'])
                        if any(instant(w['entry_at']) <= end and start <= instant(w['exit_at']) for w in plan['test_windows']):
                            raise ValueError('Test price windows already consumed for this instrument; supply untouched later history')
            except (ValueError, KeyError, TypeError) as exc:
                self.store.event('test_submission_invalid', signal_id, error=str(exc),
                                 submission_hash=digest(json.dumps(dataset, sort_keys=True)))
                return {'tested': False, 'error': str(exc), 'trial_number': plan['trial_number']}
            result = validate(dataset, spec, plan, self.store.clock(), rows=rows)
            self.store.db.execute('INSERT OR IGNORE INTO datasets VALUES(?,?)', (digest(dataset), canonical(dataset)))
            self.store.db.execute('INSERT INTO trials(id,signal_id,at,dataset_hash,data) VALUES(?,?,?,?,?)',
                                  (plan['trial_number'], signal_id, stamp(self.store.clock()), digest(dataset), canonical(result)))
            self.store.event('historical_validation', signal_id, **result)
            if result['passed']:
                self._transition(signal_id, 'BACKTESTED', {'trial': plan['trial_number']})
                self._transition(signal_id, 'QUALIFIED', {'historical_test': plan['trial_number'], 'meaning': 'worth further investigation'})
                self._queue_qualification(signal_id)
            else:
                self._transition(signal_id, 'REJECTED', {'trial': plan['trial_number'], 'reasons': result['reasons']})
        return result

    def _queue_qualification(self, signal_id):
        alert_id = 'qualification:' + signal_id
        self.store.db.execute("INSERT INTO outbox VALUES(?,?,?,'pending',NULL,NULL,?)",
                              (alert_id, signal_id, stamp(self.store.clock()), canonical(self.report(signal_id))))
        self.store.event('notification_queued', signal_id, alert_id=alert_id, priority='high')

    def change_state(self, signal_id, state, reason):
        reject_secrets(reason)
        if state not in {"REJECTED", "DEGRADED", "INVALIDATED"} or not reason.strip():
            raise ValueError("Manual changes limited to rejection/degradation/invalidation with evidence")
        with self.store.transaction():
            self._transition(signal_id, state, {"reason": reason})

    def record_price(self, symbol, market_at, price, *, kind="close", source, currency=None):
        reject_secrets({"symbol": symbol, "source": source, "currency": currency})
        at, now = instant(market_at), instant(self.store.clock())
        price = finite(price, positive=True)
        expected = instrument(self.settings, symbol)["currency"]
        currency = currency or expected
        if at > now or currency != expected:
            raise ValueError("Reject future or mismatched-currency market data")
        data = {"price": price, "source": source, "currency": currency}
        with self.store.transaction():
            old = self.store.db.execute("SELECT data FROM prices WHERE symbol=? AND market_at=? AND kind=?",
                                        (symbol, stamp(at), kind)).fetchone()
            if old:
                if json.loads(old[0])["price"] != price:
                    self.store.event("price_revision_ignored", symbol=symbol, market_at=stamp(at), new=data,
                                     original=json.loads(old[0]))
                return False
            self.store.db.execute("INSERT INTO prices VALUES(?,?,?,?,?)",
                                  (symbol, stamp(at), stamp(now), kind, canonical(data)))
        return True

    def register(self, signal_id, event_id, *, event_available_at, quote_at, reference_price,
                 feature_value, source, direction=None):
        reject_secrets({"signal_id": signal_id, "event_id": event_id, "source": source})
        now = instant(self.store.clock())
        quote, available = map(instant, (quote_at, event_available_at))
        spec = self.store.spec(signal_id)
        due = now + timedelta(days=spec["horizon_days"])
        if not event_id.strip() or not source.strip():
            raise ValueError("Event identity and source required")
        if available > now or quote > now:
            raise ValueError("Forecast must be registered after evidence and before its horizon")
        if quote < available:
            raise ValueError("Reference quote must follow event availability")
        if (now - quote).total_seconds() > self.settings["max_quote_age_seconds"]:
            raise ValueError("Quote too stale to register a live forecast")
        price = finite(reference_price, positive=True)
        feature = finite(feature_value)
        with self.store.transaction():
            if self.store.state(signal_id) not in {"FORWARD_TESTING", "QUALIFIED", "ALERTED"}:
                raise ValueError("Historical validation must pass before live registration")
            trial = json.loads(self.store.db.execute("SELECT data FROM trials WHERE signal_id=?", (signal_id,)).fetchone()[0])
            expected_direction = trial["rule"]["direction"]
            if feature <= trial["rule"]["threshold"]:
                raise ValueError("Observed feature must exceed the frozen historical threshold")
            if direction and direction != expected_direction:
                raise ValueError("Direction must match the frozen historically tested rule")
            previous = self.store.db.execute("""SELECT p.due_at,o.data FROM predictions p
              LEFT JOIN outcomes o ON o.prediction_id=p.id WHERE p.signal_id=? ORDER BY p.at DESC,p.id DESC LIMIT 1""", (signal_id,)).fetchone()
            if previous:
                if previous["data"] is None:
                    raise ValueError("Previous forecast endpoint remains unresolved")
                endpoint = max(instant(previous["due_at"]), instant(json.loads(previous["data"])["price_at"]))
                if quote <= endpoint:
                    raise ValueError("Reference quote must follow the previous realized endpoint")
            if self.store.db.execute("SELECT 1 FROM predictions WHERE signal_id=? AND event_id=?",
                                     (signal_id, event_id)).fetchone():
                raise ValueError("Underlying event already registered")
            prediction_id = digest({"signal": signal_id, "event": event_id})[:24]
            data = {"direction": expected_direction, "target_return": spec["target_return"],
                    "horizon_days": spec["horizon_days"], "reference_price": price,
                    "reference_at": stamp(quote), "event_available_at": stamp(available), "source": source,
                    "feature_value": feature,
                    "cost_bps": trial["round_trip_cost_bps"],
                    "success_criteria": "Signed endpoint return minus frozen round-trip cost >= target_return",
                    "endpoint_rule": "First observed market close at or after due_at, no more than 7 calendar days later",
                    "synthetic": self.store.mode == "synthetic"}
            self.store.db.execute("INSERT INTO predictions VALUES(?,?,?,?,?,?)",
                                  (prediction_id, signal_id, event_id, stamp(now), stamp(due), canonical(data)))
            self.store.event("prediction_registered", signal_id, prediction_id=prediction_id,
                             event_id=event_id, due_at=stamp(due), **data)
        return prediction_id

    def evaluate(self):
        """Atomic evaluation and outbox creation. Missing data remain pending."""
        evaluated = []
        self.blockers = []
        now = instant(self.store.clock())
        with self.store.transaction():
            self._review_outcomes()
            pending = list(self.store.db.execute("""
              SELECT p.* FROM predictions p LEFT JOIN outcomes o ON o.prediction_id=p.id
              WHERE o.prediction_id IS NULL AND p.due_at<=? ORDER BY p.due_at,p.id""", (stamp(now),)))
            for row in pending:
                spec, prediction = self.store.spec(row["signal_id"]), json.loads(row["data"])
                price_row = self.store.db.execute("""SELECT * FROM prices WHERE symbol=? AND kind='close'
                  AND market_at>=? AND market_at<=? AND captured_at<=? ORDER BY market_at LIMIT 1""",
                  (spec["symbol"], row["due_at"], stamp(now), stamp(now))).fetchone()
                if price_row is None:
                    if now > instant(row["due_at"]) + timedelta(days=7):
                        self._block_prediction(row, "Eligible closing price still unavailable")
                    continue
                if instant(price_row["market_at"]) > instant(row["due_at"]) + timedelta(days=7):
                    self._block_prediction(row, "Endpoint beyond frozen seven-day tolerance")
                    continue
                split = self.store.db.execute("""SELECT 1 FROM events WHERE kind='stock_split'
                  AND signal_id=? AND json_extract(data,'$.market_at')>? AND json_extract(data,'$.market_at')<=? LIMIT 1""",
                  (row["signal_id"], prediction["reference_at"], price_row["market_at"])).fetchone()
                if split:
                    state = self.store.state(row["signal_id"])
                    if state != "INVALIDATED":
                        self._transition(row["signal_id"], "INVALIDATED", {"reason": "Split crossed a price-return forecast; manual corporate-action review required"})
                    continue
                price = json.loads(price_row["data"])
                sign = 1 if prediction["direction"] == "up" else -1
                net_return = sign * (price["price"] / prediction["reference_price"] - 1) - prediction["cost_bps"] / 10000
                success = net_return >= prediction["target_return"]
                outcome = {"net_return": net_return, "price": price["price"], "price_at": price_row["market_at"],
                           "source": price["source"], "synthetic": self.store.mode == "synthetic"}
                self.store.db.execute("INSERT INTO outcomes VALUES(?,?,?,?)",
                                      (row["id"], stamp(now), int(success), canonical(outcome)))
                self.store.event("prediction_evaluated", row["signal_id"], prediction_id=row["id"], success=success, **outcome)
                evaluated.append(row["id"])
            self._review_outcomes()
        return evaluated

    def _block_prediction(self, row, reason):
        blocker = {"prediction_id": row["id"], "reason": reason}
        self.blockers.append({"signal_id": row["signal_id"], **blocker})
        exists = self.store.db.execute("""SELECT 1 FROM events WHERE kind='evaluation_blocked'
          AND signal_id=? AND json_extract(data,'$.prediction_id')=?
          AND json_extract(data,'$.reason')=? LIMIT 1""", (row["signal_id"], row["id"], reason)).fetchone()
        if not exists:
            self.store.event("evaluation_blocked", row["signal_id"], **blocker)

    def _review_outcomes(self):
        """Append corrections for late actions and legacy overlapping forecasts."""
        for signal in self.store.db.execute("SELECT id FROM signals"):
            previous = None
            for prediction in self.record(signal[0])["predictions"]:
                outcome = prediction["outcome"]
                reason = None
                if previous and (previous["evaluated_at"] is None or
                                 instant(previous["evaluated_at"]) > instant(prediction["registered_at"]) or
                                 instant(prediction["reference_at"]) <= max(instant(previous["due_at"]), instant(previous["outcome"]["price_at"]))):
                    reason = "Overlapping or unresolved preceding endpoint"
                if outcome and self.store.db.execute("""SELECT 1 FROM events WHERE kind='stock_split' AND signal_id=?
                  AND json_extract(data,'$.market_at')>? AND json_extract(data,'$.market_at')<=?""",
                  (signal[0], prediction["reference_at"], outcome["price_at"])).fetchone():
                    reason = "Split crossed realized price-return window"
                if outcome and reason and prediction["outcome_valid"]:
                    self.store.event("outcome_invalidated", signal[0], prediction_id=prediction["id"], reason=reason,
                                     original_outcome=outcome, original_success=prediction["success"])
                    if self.store.state(signal[0]) != "INVALIDATED":
                        self._transition(signal[0], "INVALIDATED", {"reason": reason, "prediction_id": prediction["id"]})
                    self.store.db.execute("UPDATE outbox SET status='cancelled' WHERE signal_id=? AND status='pending'", (signal[0],))
                    self.store.event("qualification_support_corrected", signal[0], prediction_id=prediction["id"],
                                     delivery_review_required=True)
                previous = prediction
            if self.store.state(signal[0]) not in {"QUALIFIED", "ALERTED"}:
                cancelled = self.store.db.execute("UPDATE outbox SET status='cancelled' WHERE signal_id=? AND status='pending'", (signal[0],))
                if cancelled.rowcount:
                    self.store.event("notification_cancelled", signal[0], reason="Qualification no longer supported")

    def record(self, signal_id):
        predictions = []
        invalid = {r[0] for r in self.store.db.execute("SELECT json_extract(data,'$.prediction_id') FROM events WHERE kind='outcome_invalidated' AND signal_id=?", (signal_id,))}
        for row in self.store.db.execute("""SELECT p.*,o.at evaluated_at,o.success,o.data outcome
          FROM predictions p LEFT JOIN outcomes o ON p.id=o.prediction_id
          WHERE p.signal_id=? ORDER BY p.at,p.id""", (signal_id,)):
            predictions.append({"id": row["id"], "event_id": row["event_id"], "registered_at": row["at"],
                                "due_at": row["due_at"], **json.loads(row["data"]),
                                "evaluated_at": row["evaluated_at"],
                                "outcome_valid": row["outcome"] is not None and row["id"] not in invalid,
                                "success": bool(row["success"]) if row["success"] is not None else None,
                                "outcome": json.loads(row["outcome"]) if row["outcome"] else None})
        successes = sum(p["success"] is True and p["outcome_valid"] for p in predictions)
        evaluated = sum(p["outcome_valid"] for p in predictions)
        returns = [p['outcome']['net_return'] for p in predictions if p['outcome_valid']]
        buy_and_hold = None
        if predictions:
            first = predictions[0]
            endpoint = self.store.db.execute("""SELECT data FROM prices WHERE symbol=? AND kind='close'
              AND market_at>=? AND market_at<=? ORDER BY market_at DESC LIMIT 1""",
              (self.store.spec(signal_id)['symbol'], first['reference_at'], stamp(self.store.clock()))).fetchone()
            if endpoint:
                buy_and_hold = json.loads(endpoint[0])['price'] / first['reference_price'] - 1 - first['cost_bps'] / 10000
        return {"registered": len(predictions), "evaluated": evaluated, "successes": successes,
                "failures": evaluated - successes, "pending": sum(p["outcome"] is None for p in predictions),
                "invalidated": len(invalid),
                "forecast_net_returns": returns,
                "forecast_compounded_net_return": math.prod(1 + value for value in returns) - 1 if returns else None,
                "buy_and_hold_net_return": buy_and_hold,
                "hit_rate_wilson_95": wilson(successes, evaluated), "predictions": predictions}

    def report(self, signal_id):
        spec = self.store.spec(signal_id)
        trial = self.store.db.execute("SELECT data FROM trials WHERE signal_id=?", (signal_id,)).fetchone()
        active = list(self.store.db.execute("SELECT id,due_at FROM predictions WHERE signal_id=? AND due_at>?",
                                            (signal_id, stamp(self.store.clock()))))
        return {"signal_id": signal_id, "name": spec["name"], "discovered_signal": spec["phenomenon"],
                "hypothesized_mechanism": spec["mechanism"], "symbol": spec["symbol"],
                "state": self.store.state(signal_id), "historical_evidence": json.loads(trial[0]) if trial else None,
                "forward_predictions": self.record(signal_id), "predictive_horizon_days": spec["horizon_days"],
                "corrections": [{"at": row["at"], **json.loads(row["data"])} for row in self.store.db.execute(
                    "SELECT at,data FROM events WHERE kind='outcome_invalidated' AND signal_id=? ORDER BY seq", (signal_id,))],
                "current_status": {"active_predictions": [dict(r) for r in active],
                                   "opportunity": "Unconfirmed; a fresh indicator, quote and affordability check are required"},
                "confidence_and_limitations": spec["limitations"] + [
                    "Qualification means historical evidence worth further investigation",
                    "Report all attempts; Wilson interval is descriptive and assumes independence",
                    "Forecast returns describe research predictions"],
                "synthetic": self.store.mode == "synthetic"}

    def claim(self, alert_id):
        with self.store.transaction():
            self._review_outcomes()
            row = self.store.db.execute("SELECT * FROM outbox WHERE id=?", (alert_id,)).fetchone()
            if not row or row["status"] != "pending":
                return None
            token = secrets.token_hex(16)
            payload = self.report(row["signal_id"])
            self.store.db.execute("UPDATE outbox SET status='claimed',token=?,data=? WHERE id=?",
                                  (token, canonical(payload), alert_id))
            self.store.event("notification_claimed", row["signal_id"], alert_id=alert_id)
        return {"alert_id": alert_id, "token": token, "priority": "high", "payload": payload,
                "message": alert_message(payload, self.settings["timezone"])}

    def acknowledge(self, alert_id, token, receipt):
        reject_secrets(receipt)
        if not receipt.strip():
            raise ValueError("A supported-delivery receipt or visible message link is required")
        with self.store.transaction():
            row = self.store.db.execute("SELECT * FROM outbox WHERE id=?", (alert_id,)).fetchone()
            if not row or row["token"] != token:
                raise ValueError("Invalid claim")
            if row["status"] == "delivered":
                if row["receipt"] != receipt:
                    raise ValueError("Existing delivery receipt differs")
                return False
            if row["status"] != "claimed":
                raise ValueError("Alert is not claimed")
            self.store.db.execute("UPDATE outbox SET status='delivered',receipt=? WHERE id=?", (receipt, alert_id))
            if self.store.state(row["signal_id"]) == "QUALIFIED":
                self._transition(row["signal_id"], "ALERTED", {"alert_id": alert_id, "receipt": receipt})
            self.store.event("notification_delivered", row["signal_id"], alert_id=alert_id, receipt=receipt)
        return True

    def release(self, alert_id, token, evidence):
        """Only after the delivery adapter confirms that nothing was sent."""
        reject_secrets(evidence)
        if not evidence.strip():
            raise ValueError("Evidence of confirmed non-delivery required")
        with self.store.transaction():
            cursor = self.store.db.execute("UPDATE outbox SET status='pending',token=NULL WHERE id=? AND token=? AND status='claimed'",
                                           (alert_id, token))
            if cursor.rowcount != 1:
                raise ValueError("No matching outstanding claim")
            self.store.event("notification_confirmed_not_sent", alert_id=alert_id, evidence=evidence)
