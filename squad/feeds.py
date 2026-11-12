"""Keyless public feeds. Yahoo is an unofficial adapter; failures block, never invent data."""

import json
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .util import UTC, canonical, digest, finite, instant, now_utc, stamp

USER_AGENT = "investment-discovery-squad/0.2 (low-volume research)"


def fetch_json(url, cache_dir, now, *, ttl_seconds=3600):
    folder = Path(cache_dir)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (digest(url) + ".json")
    if path.exists():
        cached = json.loads(path.read_text())
        if 0 <= (instant(now) - instant(cached["fetched_at"])).total_seconds() < ttl_seconds:
            return cached
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(10 * 1024 * 1024 + 1)
        if len(raw) > 10 * 1024 * 1024:
            raise ValueError("Feed response exceeded 10 MiB")
    payload = {"source": url, "fetched_at": stamp(now_utc()), "body": json.loads(raw)}
    archive_hash = digest({"source": url, "body": payload["body"]})
    payload["archive_hash"] = archive_hash
    archive_dir = folder / "archive"
    archive_dir.mkdir(exist_ok=True)
    archive_path = archive_dir / (archive_hash + ".json")
    try:
        with archive_path.open("x", encoding="utf-8") as stream:
            stream.write(canonical(payload))
    except FileExistsError:
        pass  # An identical response is already preserved; keep its first capture.
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder, prefix=".feed-", suffix=".tmp", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(canonical(payload))
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def market(symbol, cache_dir, now, instrument):
    url = "https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.parse.quote(symbol, safe="") + "?range=10y&interval=1d&events=div%2Csplits"
    result = fetch_json(url, cache_dir, now, ttl_seconds=1800)
    chart = result["body"]["chart"]
    if chart.get("error") or not chart.get("result"):
        raise ValueError(f"Market provider returned no data for {symbol}")
    data = chart["result"][0]
    meta = data["meta"]
    if meta.get("currency") != instrument["currency"] or meta.get("symbol", "").upper() != symbol.upper():
        raise ValueError("Wrong market symbol or currency")
    closes = data["indicators"]["quote"][0]["close"]
    history = []
    for timestamp, price in zip(data.get("timestamp", []), closes):
        if price is None:
            continue
        zone = ZoneInfo(instrument["exchange_timezone"])
        hour, minute = map(int, instrument["close_time"].split(":"))
        session_date = datetime.fromtimestamp(timestamp, UTC).astimezone(zone).date()
        # Use the configured normal close conservatively on early-close sessions.
        close_at = datetime.combine(session_date, time(hour, minute), zone).astimezone(UTC)
        if close_at + timedelta(minutes=15) <= instant(now):
            history.append({"at": stamp(close_at), "price": finite(price, positive=True)})
    quote = None
    if meta.get("regularMarketTime") and meta.get("regularMarketPrice"):
        quote = {"at": stamp(datetime.fromtimestamp(meta["regularMarketTime"], UTC)),
                 "price": finite(meta["regularMarketPrice"], positive=True)}
    splits = [{"at": stamp(datetime.fromtimestamp(v["date"], UTC)), "ratio": v.get("splitRatio")}
              for v in data.get("events", {}).get("splits", {}).values()]
    return {"symbol": symbol, "currency": instrument["currency"], "source": url, "fetched_at": result["fetched_at"],
            "history": history, "quote": quote, "splits": splits}


def attention(article, cache_dir, now):
    end = (instant(now).date() - timedelta(days=1)).strftime("%Y%m%d00")
    url = ("https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
           "en.wikipedia.org/all-access/user/" + urllib.parse.quote(article, safe="") + f"/daily/2016010100/{end}")
    result = fetch_json(url, cache_dir, now, ttl_seconds=86400)
    rows = []
    for item in result["body"].get("items", []):
        date = datetime.strptime(item["timestamp"][:8], "%Y%m%d").replace(tzinfo=UTC)
        rows.append({"at": stamp(date + timedelta(days=1)), "value": finite(item["views"]),
                     "captured_at": result["fetched_at"]})
    if not rows:
        raise ValueError("No Wikimedia observations")
    return {"source": url, "key": "wikipedia:" + article, "rows": rows}


def record_attention(store, data):
    with store.transaction():
        for row in data["rows"]:
            old = store.db.execute("SELECT data FROM indicators WHERE source=? AND event_at=?",
                                   (data["key"], row["at"])).fetchone()
            if old:
                # Preserve the first observed value. Never rewrite known history from a later revision.
                continue
            store.db.execute("INSERT INTO indicators VALUES(?,?,?,?)",
                             (data["key"], row["at"], row["captured_at"], canonical({"value": row["value"], "url": data["source"]})))


def observed_feature(store, article, *, as_of, max_age_days=7):
    rows = list(store.db.execute("""SELECT * FROM indicators WHERE source=? AND captured_at<=?
      AND event_at<=? ORDER BY event_at DESC LIMIT 29""", ("wikipedia:" + article, stamp(as_of), stamp(as_of))))
    if len(rows) < 29:
        return None
    # Require daily consecutive history; gaps cannot silently become a different lookback.
    for newer, older in zip(rows, rows[1:]):
        if instant(newer["event_at"]) - instant(older["event_at"]) != timedelta(days=1):
            return None
    if instant(as_of) - instant(rows[0]["event_at"]) > timedelta(days=max_age_days):
        return None
    previous = [json.loads(r["data"])["value"] for r in rows[1:]]
    average = sum(previous) / len(previous)
    if average <= 0:
        return None
    latest = json.loads(rows[0]["data"])
    return {"value": latest["value"] / average,
            "event_at": rows[0]["event_at"], "available_at": max(r["captured_at"] for r in rows),
            "source": latest["url"], "event_id": "wikipedia:" + article + ":" + rows[0]["event_at"]}


def observed_dataset(store, spec, market_data, settings):
    """Only use first-seen observations actually captured before each historical entry."""
    history = market_data["history"]
    rows, index = [], 0
    while index < len(history):
        entry = history[index]
        feature = observed_feature(store, spec["article"], as_of=entry["at"],
                                   max_age_days=settings["max_indicator_age_days"])
        due = instant(entry["at"]) + timedelta(days=spec["horizon_days"])
        end_index = next((j for j in range(index + 1, len(history)) if instant(history[j]["at"]) >= due), None)
        if end_index is None:
            break
        end = history[end_index]
        split_crossed = any(instant(entry["at"]) < instant(s["at"]) <= instant(end["at"])
                            for s in market_data.get("splits", []))
        if feature and not split_crossed and instant(feature["available_at"]) < instant(entry["at"]):
            rows.append({"event_id": entry["at"], "available_at": feature["available_at"],
                         "entry_at": entry["at"], "exit_at": end["at"], "feature": feature["value"],
                         "entry_price": entry["price"], "exit_price": end["price"]})
        index = end_index + 1
    return {"source": market_data["source"] + " and Wikimedia first-seen snapshots",
            "availability_verified": True,
            "availability_evidence": "SQLite immutable indicator snapshots: captured_at precedes every entry_at",
            "synthetic": False, "rows": rows,
            "limitations": ["Yahoo price feed is unofficial and may revise historical data",
                            "Unadjusted price-return outcome excludes cash dividends; known split-crossing windows omitted",
                            "First-seen observation archive begins at installation, not at historical feed start",
                            "28-day attention ratio; daily indicator with no intraday resolution"]}


def episode_id(store, article, threshold, as_of):
    rows = list(store.db.execute("""SELECT * FROM indicators WHERE source=? AND captured_at<=?
      AND event_at<=? ORDER BY event_at DESC LIMIT 180""", ("wikipedia:" + article, stamp(as_of), stamp(as_of))))
    start = None
    for index in range(len(rows) - 28):
        window = rows[index:index + 29]
        if any(instant(a["event_at"]) - instant(b["event_at"]) != timedelta(days=1)
               for a, b in zip(window, window[1:])):
            break
        baseline = sum(json.loads(r["data"])["value"] for r in window[1:]) / 28
        if baseline <= 0 or json.loads(window[0]["data"])["value"] / baseline <= threshold:
            break
        start = window[0]["event_at"]
    # If every observed window remains above threshold, the episode's true beginning
    # is unknown. Avoid making a new identity at the rolling window's boundary.
    if start is None or len(rows) >= 180 and start == rows[-29]["event_at"]:
        return None
    return "wikipedia:" + article + ":episode:" + start
