import json
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from . import feeds
from .configuration import instrument
from .portfolio import Portfolio
from .util import canonical, instant, stamp


def due_close(now, horizon_days, market):
    zone = ZoneInfo(market["exchange_timezone"])
    hour, minute = map(int, market["close_time"].split(":"))
    minimum = instant(now) + timedelta(days=horizon_days)
    date = minimum.astimezone(zone).date()
    while True:
        result = datetime.combine(date, time(hour, minute), zone)
        if date.weekday() in market["weekdays"] and result >= minimum:
            return result
        date += timedelta(days=1)


def run(engine, *, research=False, offline=False, forecast_enabled=True):
    store, settings = engine.store, engine.settings
    now = store.clock()
    result = {"at": stamp(now), "mode": store.mode, "errors": [], "evaluated": engine.evaluate(),
              "registered": [], "ideas": [], "research": []}
    if research:
        today = instant(now).astimezone(ZoneInfo(settings["timezone"])).date()
        created_today = sum(instant(r[0]).astimezone(ZoneInfo(settings["timezone"])).date() == today
                            for r in store.db.execute("SELECT at FROM specs"))
        for spec in settings["research_universe"]:
            if created_today >= settings["max_candidates_per_day"]:
                break
            if not store.db.execute("SELECT 1 FROM specs WHERE id=?", (spec["id"],)).fetchone():
                engine.discover(spec)
                created_today += 1
    market_data = {}
    for row in list(store.db.execute("SELECT id FROM signals ORDER BY id")):
        signal_id = row[0]
        spec = store.spec(signal_id)
        if offline:
            continue
        try:
            data = market_data.get(spec["symbol"])
            if data is None:
                data = feeds.market(spec["symbol"], store.path.parent / "cache", now, instrument(settings, spec["symbol"]))
                market_data[spec["symbol"]] = data
                for price in data["history"]:
                    engine.record_price(spec["symbol"], price["at"], price["price"], source=data["source"])
                if data["quote"]:
                    quote = data["quote"]
                    engine.record_price(spec["symbol"], quote["at"], quote["price"], kind="quote", source=data["source"])
            for split in data.get("splits", []):
                seen = store.db.execute("SELECT 1 FROM events WHERE kind='stock_split' AND signal_id=? AND json_extract(data,'$.market_at')=?",
                                         (signal_id, split["at"])).fetchone()
                if not seen:
                    with store.transaction():
                        store.event("stock_split", signal_id, market_at=split["at"], ratio=split["ratio"], source=data["source"])
        except Exception as exc:
            _error(store, result, signal_id, "market_feed", exc)
    # Outcomes and qualification are processed before indicator research, and before trade ideas.
    result["evaluated"] += engine.evaluate()
    for row in list(store.db.execute("SELECT id FROM signals ORDER BY id")):
        signal_id = row[0]
        spec = store.spec(signal_id)
        if offline or spec["symbol"] not in market_data or not spec.get("article"):
            continue
        try:
            data = market_data[spec["symbol"]]
            attention = feeds.attention(spec["article"], store.path.parent / "cache", now)
            feeds.record_attention(store, attention)
            if research and store.state(signal_id) == "DISCOVERED":
                dataset = feeds.observed_dataset(store, spec, data, settings)
                n = len(dataset["rows"])
                split = int(n * 0.6)
                if split >= settings["min_train_samples"] and n - split >= settings["min_test_samples"]:
                    outcome = engine.backtest(signal_id, dataset)
                    result["research"].append({"signal_id": signal_id, "validation": outcome})
                else:
                    note = {"signal_id": signal_id, "status": "COLLECTING_POINT_IN_TIME_HISTORY",
                            "usable_windows": n, "reason": "Retrospective API values lack proven first-publication timestamps; collecting immutable observations"}
                    result["research"].append(note)
                    with store.transaction():
                        store.event("historical_blocked", signal_id, usable_windows=n, reason=note["reason"])
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
                                            due_at=due_close(current, spec["horizon_days"], instrument(settings, spec["symbol"])), quote_at=quote["at"],
                                            reference_price=quote["price"], source=feature["source"] + " ; " + data["source"])
            result["registered"].append(prediction_id)
            if store.state(signal_id) in {"QUALIFIED", "ALERTED"} and trial["rule"]["direction"] == "up":
                try:
                    result["ideas"].append(Portfolio(engine).idea(prediction_id))
                except ValueError as exc:
                    result.setdefault("skipped_ideas", []).append({"prediction_id": prediction_id, "reason": str(exc)})
        except Exception as exc:
            _error(store, result, signal_id, "indicator_or_research", exc)
    result["alerts"] = [dict(r) for r in store.db.execute("SELECT id,signal_id,at,status FROM outbox WHERE status='pending' ORDER BY at")]
    result["uncertain_deliveries"] = [dict(r) for r in store.db.execute("SELECT id,signal_id,at,status FROM outbox WHERE status='claimed'")]
    result["signals"] = [dict(r) for r in store.db.execute("SELECT * FROM signals ORDER BY id")]
    result["portfolio"] = Portfolio(engine).balance()
    result["execution"] = "Recommendations only; user places every brokerage order and reports fills"
    with store.transaction():
        store.event("run_completed", research=research, offline=offline, errors=len(result["errors"]),
                    evaluated=len(result["evaluated"]), alerts_pending=len(result["alerts"]))
    store.export(store.path.parent / "knowledge.json")
    return result


def _error(store, result, signal_id, stage, exc):
    error = {"signal_id": signal_id, "stage": stage, "error": type(exc).__name__ + ": " + str(exc)}
    result["errors"].append(error)
    with store.transaction():
        store.event("run_error", **error)
