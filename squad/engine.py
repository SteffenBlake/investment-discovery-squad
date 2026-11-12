import json
import secrets
from datetime import timedelta

from .research import validate
from .configuration import instrument
from .messages import alert_message
from .store import Store
from .util import canonical, digest, finite, instant, stamp, wilson

TRANSITIONS = {
    "DISCOVERED": {"BACKTESTED", "REJECTED", "INVALIDATED"},
    "BACKTESTED": {"FORWARD_TESTING", "REJECTED", "INVALIDATED"},
    "FORWARD_TESTING": {"QUALIFIED", "DEGRADED", "INVALIDATED"},
    "QUALIFIED": {"ALERTED", "DEGRADED", "INVALIDATED"},
    "ALERTED": {"DEGRADED", "INVALIDATED"},
    "REJECTED": {"INVALIDATED"}, "DEGRADED": {"INVALIDATED"}, "INVALIDATED": set(),
}


class Engine:
    def __init__(self, store: Store, settings):
        self.store, self.settings = store, settings

    def _transition(self, signal_id, state, evidence):
        old = self.store.state(signal_id)
        if state not in TRANSITIONS[old]:
            raise ValueError(f"Invalid transition {old} -> {state}")
        self.store.db.execute("UPDATE signals SET state=? WHERE id=?", (state, signal_id))
        self.store.event("transition", signal_id, previous=old, state=state, evidence=evidence)

    def discover(self, spec):
        for field in ("id", "name", "phenomenon", "mechanism", "symbol", "limitations"):
            if not spec.get(field):
                raise ValueError(f"Signal needs {field}")
        if not isinstance(spec.get("horizon_days"), int) or not 1 <= spec["horizon_days"] <= 90:
            raise ValueError("horizon_days must be an integer from 1 to 90")
        if not 0 < finite(spec["target_return"]) < 1:
            raise ValueError("target_return must be between 0 and 1")
        instrument(self.settings, spec["symbol"])
        with self.store.transaction():
            existing = self.store.db.execute("SELECT data FROM specs WHERE id=?", (spec["id"],)).fetchone()
            if existing:
                if existing[0] != canonical(spec):
                    raise ValueError("Signal specification immutable; register a new version/ID")
                return False
            self.store.db.execute("INSERT INTO specs VALUES(?,?,?)",
                                  (spec["id"], stamp(self.store.clock()), canonical(spec)))
            self.store.db.execute("INSERT INTO signals VALUES(?, 'DISCOVERED')", (spec["id"],))
            self.store.event("transition", spec["id"], previous=None, state="DISCOVERED", evidence=spec)
        return True

    def backtest(self, signal_id, dataset):
        with self.store.transaction():
            if self.store.state(signal_id) != "DISCOVERED":
                raise ValueError("One holdout per immutable signal version; register revisions as new trials")
            if dataset.get("synthetic") and self.store.mode != "synthetic":
                raise ValueError("Synthetic evidence prohibited in production")
            if self.store.db.execute("SELECT 1 FROM trials WHERE signal_id=?", (signal_id,)).fetchone():
                raise ValueError("Holdout already consumed; do not rerun or tune on it")
            number = self.store.db.execute("SELECT COALESCE(MAX(id),0)+1 FROM trials").fetchone()[0]
            result = validate(dataset, self.store.spec(signal_id), self.settings, number, self.store.clock())
            self.store.db.execute("INSERT OR IGNORE INTO datasets VALUES(?,?)", (digest(dataset), canonical(dataset)))
            self.store.db.execute("INSERT INTO trials(id,signal_id,at,dataset_hash,data) VALUES(?,?,?,?,?)",
                                  (number, signal_id, stamp(self.store.clock()), digest(dataset), canonical(result)))
            self.store.event("historical_validation", signal_id, **result)
            if result["passed"]:
                self._transition(signal_id, "BACKTESTED", {"trial": number, "dataset_hash": digest(dataset)})
                self._transition(signal_id, "FORWARD_TESTING", {"historical_only": True, "live_successes": 0})
            else:
                self._transition(signal_id, "REJECTED", {"trial": number, "reasons": result["reasons"]})
        return result

    def change_state(self, signal_id, state, reason):
        if state not in {"REJECTED", "DEGRADED", "INVALIDATED"} or not reason.strip():
            raise ValueError("Manual changes limited to rejection/degradation/invalidation with evidence")
        with self.store.transaction():
            self._transition(signal_id, state, {"reason": reason})

    def record_price(self, symbol, market_at, price, *, kind="close", source, currency=None):
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

    def register(self, signal_id, event_id, *, event_available_at, due_at, quote_at, reference_price,
                 source, direction=None):
        now = instant(self.store.clock())
        due, quote, available = map(instant, (due_at, quote_at, event_available_at))
        spec = self.store.spec(signal_id)
        if not event_id.strip() or not source.strip():
            raise ValueError("Event identity and source required")
        if available > now or quote > now or due <= now:
            raise ValueError("Forecast must be registered after evidence and before its horizon")
        if (now - quote).total_seconds() > self.settings["max_quote_age_seconds"]:
            raise ValueError("Quote too stale to register a live forecast")
        horizon = (due - now).total_seconds() / 86400
        if not spec["horizon_days"] <= horizon <= spec["horizon_days"] + 7:
            raise ValueError("Forecast horizon differs from the historically tested rule")
        price = finite(reference_price, positive=True)
        with self.store.transaction():
            if self.store.state(signal_id) not in {"FORWARD_TESTING", "QUALIFIED", "ALERTED"}:
                raise ValueError("Historical validation must pass before live registration")
            trial = json.loads(self.store.db.execute("SELECT data FROM trials WHERE signal_id=?", (signal_id,)).fetchone()[0])
            expected_direction = trial["rule"]["direction"]
            if direction and direction != expected_direction:
                raise ValueError("Direction must match the frozen historically tested rule")
            if self.store.db.execute("SELECT 1 FROM predictions WHERE signal_id=? AND due_at>?",
                                     (signal_id, stamp(now))).fetchone():
                raise ValueError("Overlapping prediction windows are not independent")
            if self.store.db.execute("SELECT 1 FROM predictions WHERE signal_id=? AND event_id=?",
                                     (signal_id, event_id)).fetchone():
                raise ValueError("Underlying event already registered")
            prediction_id = digest({"signal": signal_id, "event": event_id})[:24]
            data = {"direction": expected_direction, "target_return": spec["target_return"],
                    "horizon_days": spec["horizon_days"], "reference_price": price,
                    "reference_at": stamp(quote), "event_available_at": stamp(available), "source": source,
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
        now = instant(self.store.clock())
        with self.store.transaction():
            pending = list(self.store.db.execute("""
              SELECT p.* FROM predictions p LEFT JOIN outcomes o ON o.prediction_id=p.id
              WHERE o.prediction_id IS NULL AND p.due_at<=? ORDER BY p.due_at,p.id""", (stamp(now),)))
            touched = set()
            for row in pending:
                spec, prediction = self.store.spec(row["signal_id"]), json.loads(row["data"])
                price_row = self.store.db.execute("""SELECT * FROM prices WHERE symbol=? AND kind='close'
                  AND market_at>=? AND market_at<=? AND captured_at<=? ORDER BY market_at LIMIT 1""",
                  (spec["symbol"], row["due_at"], stamp(now), stamp(now))).fetchone()
                if price_row is None:
                    if now > instant(row["due_at"]) + timedelta(days=7):
                        self.store.event("evaluation_blocked", row["signal_id"], prediction_id=row["id"],
                                         reason="Missing endpoint; remains pending, never treated as a win")
                    continue
                if instant(price_row["market_at"]) > instant(row["due_at"]) + timedelta(days=7):
                    self.store.event("evaluation_blocked", row["signal_id"], prediction_id=row["id"],
                                     reason="Endpoint beyond frozen seven-day tolerance")
                    continue
                split = self.store.db.execute("""SELECT 1 FROM events WHERE kind='stock_split'
                  AND signal_id=? AND json_extract(data,'$.market_at')>? AND json_extract(data,'$.market_at')<=? LIMIT 1""",
                  (row["signal_id"], row["at"], price_row["market_at"])).fetchone()
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
                touched.add(row["signal_id"])
                evaluated.append(row["id"])
            # Process every matured outcome before composing an alert, retaining losses in the same run.
            for signal_id in sorted(touched):
                record = self.record(signal_id)
                if self.store.state(signal_id) == "FORWARD_TESTING" and record["successes"] >= 3:
                    self._transition(signal_id, "QUALIFIED", {"successes": record["successes"], "attempts": record["evaluated"]})
                    alert_id = f"qualification:{signal_id}"
                    payload = self.report(signal_id)
                    self.store.db.execute("INSERT INTO outbox VALUES(?,?,?,'pending',NULL,NULL,?)",
                                          (alert_id, signal_id, stamp(now), canonical(payload)))
                    self.store.event("notification_queued", signal_id, alert_id=alert_id, priority="high")
        return evaluated

    def record(self, signal_id):
        predictions = []
        for row in self.store.db.execute("""SELECT p.*,o.at evaluated_at,o.success,o.data outcome
          FROM predictions p LEFT JOIN outcomes o ON p.id=o.prediction_id
          WHERE p.signal_id=? ORDER BY p.at,p.id""", (signal_id,)):
            predictions.append({"id": row["id"], "event_id": row["event_id"], "registered_at": row["at"],
                                "due_at": row["due_at"], **json.loads(row["data"]),
                                "evaluated_at": row["evaluated_at"],
                                "success": bool(row["success"]) if row["success"] is not None else None,
                                "outcome": json.loads(row["outcome"]) if row["outcome"] else None})
        successes = sum(p["success"] is True for p in predictions)
        evaluated = sum(p["success"] is not None for p in predictions)
        return {"registered": len(predictions), "evaluated": evaluated, "successes": successes,
                "failures": evaluated - successes, "pending": len(predictions) - evaluated,
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
                "current_status": {"active_predictions": [dict(r) for r in active],
                                   "opportunity": "Unconfirmed; a fresh indicator, quote and affordability check are required"},
                "confidence_and_limitations": spec["limitations"] + [
                    "Three successes are a minimum gate, not proof of a reliable strategy",
                    "Report all attempts; Wilson interval is descriptive and assumes independence",
                    "Research forecasts and user-confirmed brokerage fills are separate records"],
                "synthetic": self.store.mode == "synthetic"}

    def claim(self, alert_id):
        with self.store.transaction():
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
        if not evidence.strip():
            raise ValueError("Evidence of confirmed non-delivery required")
        with self.store.transaction():
            cursor = self.store.db.execute("UPDATE outbox SET status='pending',token=NULL WHERE id=? AND token=? AND status='claimed'",
                                           (alert_id, token))
            if cursor.rowcount != 1:
                raise ValueError("No matching outstanding claim")
            self.store.event("notification_confirmed_not_sent", alert_id=alert_id, evidence=evidence)
