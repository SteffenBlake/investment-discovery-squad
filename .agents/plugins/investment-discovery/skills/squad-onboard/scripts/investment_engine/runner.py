import json

from . import feeds
from .configuration import instrument, redact
from .engine import CandidateLimit
from .portfolio import Portfolio
from .util import instant, stamp
from .trial import trial_status


def run(engine, *, research=False, offline=False, forecast_enabled=True, continue_work=False):
    store, settings = engine.store, engine.settings
    now = store.clock()
    result = {"at": stamp(now), "mode": store.mode, "errors": [], "evaluated": [],
              "registered": [], "research": [], "blocked_predictions": [], "corrections": []}
    starting_sequence = store.db.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0]
    delivery_waiting = _delivery_work(store, result)
    previous_deliveries = {row["id"] for row in result["alerts"] + result["uncertain_deliveries"]}
    if not continue_work and delivery_waiting:
        result["remaining_work"] = True
        return result
    result['trial'] = trial_status(engine)
    if result['trial']['status'] in {'review_required', 'stopped'}:
        result['remaining_work'] = False
        return result
    if research:
        for spec in settings["research_universe"]:
            if not store.db.execute("SELECT 1 FROM specs WHERE id=?", (spec["id"],)).fetchone():
                try:
                    engine.discover(spec)
                except CandidateLimit:
                    break
    if research:
        result['research'] = [{'signal_id': row[0], 'status': 'HISTORICAL_RESEARCH_REQUIRED',
                               'action': 'Develop on earlier history; freeze test plan; test untouched later history once'}
                              for row in store.db.execute("SELECT id FROM signals WHERE state='DISCOVERED' ORDER BY id")]
    market_data = {}
    for row in list(store.db.execute("SELECT id FROM signals ORDER BY id")):
        signal_id = row[0]
        spec = store.spec(signal_id)
        active = store.state(signal_id) in {'DISCOVERED', 'FORWARD_TESTING', 'QUALIFIED', 'ALERTED'}
        pending = store.db.execute("""SELECT 1 FROM predictions p LEFT JOIN outcomes o ON o.prediction_id=p.id
          WHERE p.signal_id=? AND o.prediction_id IS NULL LIMIT 1""", (signal_id,)).fetchone()
        if not active and not pending:
            continue
        if offline:
            continue
        try:
            data = market_data.get(spec["symbol"])
            fetched = data is None
            if fetched:
                data = feeds.market(spec["symbol"], store.path.parent / "cache", now, instrument(settings, spec["symbol"]))
                market_data[spec["symbol"]] = data
            for warning in data.get('warnings', []):
                result['errors'].append({'signal_id': signal_id, 'stage': 'session_close', 'error': warning})
            for split in data.get("splits", []):
                seen = store.db.execute("SELECT 1 FROM events WHERE kind='stock_split' AND signal_id=? AND json_extract(data,'$.market_at')=?",
                                         (signal_id, split["at"])).fetchone()
                if not seen:
                    with store.transaction():
                        store.event("stock_split", signal_id, market_at=split["at"], ratio=split["ratio"], source=data["source"])
            if fetched:
                for price in data["history"]:
                    engine.record_price(spec["symbol"], price["at"], price["price"], source=data["source"])
                if data["quote"]:
                    quote = data["quote"]
                    engine.record_price(spec["symbol"], quote["at"], quote["price"], kind="quote", source=data["source"])
        except Exception as exc:
            _error(store, result, signal_id, "market_feed", exc)
    # Outcomes and qualification are processed before indicator research, and before trade ideas.
    result["evaluated"] += engine.evaluate()
    result["blocked_predictions"] = engine.blockers
    result["corrections"] = [dict(row) for row in store.db.execute("""SELECT seq,signal_id,data FROM events
      WHERE kind='outcome_invalidated' AND seq>? ORDER BY seq""", (starting_sequence,))]
    for correction in result["corrections"]:
        correction["data"] = json.loads(correction["data"])
    delivery_waiting = _delivery_work(store, result)
    new_delivery = any(row["id"] not in previous_deliveries for row in result["alerts"] + result["uncertain_deliveries"])
    if delivery_waiting and (not continue_work or new_delivery):
        result["remaining_work"] = True
        return result
    for row in list(store.db.execute("SELECT id FROM signals ORDER BY id")):
        signal_id = row[0]
        spec = store.spec(signal_id)
        if offline or store.state(signal_id) not in {"FORWARD_TESTING", "QUALIFIED", "ALERTED"} or spec["symbol"] not in market_data or not spec.get("article"):
            continue
        if (spec.get('input_id') != 'wikimedia:pageviews' or
                spec.get('feature_formula') != {'operation': 'ratio_to_mean', 'lookback_days': 28}):
            result['research'].append({'signal_id': signal_id, 'status': 'CUSTOM_ADAPTER_REQUIRED'})
            continue
        try:
            data = market_data[spec["symbol"]]
            attention = feeds.attention(spec["article"], store.path.parent / "cache", now)
            feeds.record_attention(store, attention)
            if not forecast_enabled or store.state(signal_id) not in {"FORWARD_TESTING", "QUALIFIED", "ALERTED"}:
                continue
            trial = json.loads(store.db.execute("SELECT data FROM trials WHERE signal_id=?", (signal_id,)).fetchone()[0])
            current = store.clock()
            feature = feeds.observed_feature(store, spec["article"], as_of=current,
                                             max_age_days=settings["max_indicator_age_days"])
            if not feature or feature["value"] <= trial["rule"]["threshold"]:
                continue
            event_id = feeds.episode_id(store, spec["article"], trial["rule"]["threshold"], current)
            if not event_id:
                continue
            if store.db.execute("SELECT 1 FROM predictions WHERE signal_id=? AND (due_at>? OR event_id=?)",
                                 (signal_id, stamp(current), event_id)).fetchone():
                continue
            quote = data["quote"]
            if quote is None or (instant(current) - instant(quote["at"])).total_seconds() > settings["max_quote_age_seconds"]:
                continue
            prediction_id = engine.register(signal_id, event_id, event_available_at=feature["available_at"],
                                            quote_at=quote["at"], reference_price=quote["price"], feature_value=feature["value"],
                                            source=feature["source"] + " ; " + data["source"])
            result["registered"].append(prediction_id)
        except Exception as exc:
            _error(store, result, signal_id, "indicator_or_research", exc)
    _delivery_work(store, result)
    result["remaining_work"] = False
    result["signals"] = [dict(r) for r in store.db.execute("SELECT * FROM signals ORDER BY id")]
    result["portfolio"] = Portfolio(engine).balance()
    result["execution"] = "Recommendations only; user places every brokerage order and reports fills"
    with store.transaction():
        store.event("run_completed", research=research, offline=offline, errors=len(result["errors"]),
                    evaluated=len(result["evaluated"]), alerts_pending=len(result["alerts"]))
    return result


def _error(store, result, signal_id, stage, exc):
    error = {"signal_id": signal_id, "stage": stage, "error": type(exc).__name__ + ": " + redact(exc)}
    result["errors"].append(error)
    with store.transaction():
        store.event("run_error", **error)


def _delivery_work(store, result):
    result["alerts"] = [dict(r) for r in store.db.execute("SELECT id,signal_id,at,status FROM outbox WHERE status='pending' ORDER BY at")]
    result["uncertain_deliveries"] = [dict(r) for r in store.db.execute("SELECT id,signal_id,at,status FROM outbox WHERE status='claimed'")]
    return bool(result["alerts"] or result["uncertain_deliveries"])
