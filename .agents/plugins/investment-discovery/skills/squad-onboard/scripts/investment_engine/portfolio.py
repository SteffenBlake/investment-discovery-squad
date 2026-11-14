"""User-supplied portfolio snapshots, reported fills and fee-aware purchase sizing."""

import json
import re
from datetime import timedelta
from decimal import Decimal, ROUND_UP, ROUND_DOWN
from zoneinfo import ZoneInfo

from .util import canonical, digest, instant, stamp
from .configuration import instrument, money, reject_secrets


class Portfolio:
    def __init__(self, engine):
        self.engine = engine
        self.store, self.settings = engine.store, engine.settings

    def normalize_snapshot(self, portfolio):
        reject_secrets(portfolio)
        if not isinstance(portfolio, dict) or "cash" not in portfolio:
            raise ValueError("Supply actual portfolio cash, currency and holdings")
        holdings = portfolio.get("holdings")
        if isinstance(holdings, list):
            if len({row["symbol"] for row in holdings}) != len(holdings):
                raise ValueError("Duplicate symbols in supplied holdings")
            holdings = {row["symbol"]: row["quantity"] for row in holdings}
        if not isinstance(holdings, dict) or len(holdings) > 100:
            raise ValueError("Portfolio holdings must contain at most 100 symbol-to-quantity entries")
        if any(not isinstance(symbol, str) or not symbol.strip() for symbol in holdings):
            raise ValueError("Portfolio symbol required")
        if not re.fullmatch("[A-Z]{3}", portfolio.get("currency", "")):
            raise ValueError("Portfolio currency required")
        if portfolio.get("as_of") and instant(portfolio["as_of"]) > instant(self.store.clock()):
            raise ValueError("Portfolio snapshot cannot be from the future")
        return {**portfolio, "cash": str(money(portfolio["cash"])),
                "holdings": {symbol: str(money(quantity)) for symbol, quantity in holdings.items()}}

    def record_snapshot(self, portfolio):
        snapshot = self.normalize_snapshot(portfolio)
        with self.store.transaction():
            previous = self.store.db.execute(
                "SELECT data FROM events WHERE kind='portfolio_snapshot' ORDER BY seq DESC LIMIT 1").fetchone()
            if previous is None or json.loads(previous[0])["hash"] != digest(snapshot):
                self.store.event("portfolio_snapshot", hash=digest(snapshot), portfolio=snapshot)
        return snapshot

    def balance(self):
        row = self.store.db.execute(
            "SELECT at,data FROM events WHERE kind='portfolio_snapshot' ORDER BY seq DESC LIMIT 1").fetchone()
        if row is None:
            return {"available": False, "cash": None, "currency": self.settings["base_currency"], "holdings": {},
                    "note": "Supply an actual portfolio snapshot before purchase sizing"}
        return {"available": True, **json.loads(row["data"])["portfolio"], "reported_at": row["at"],
                "note": "Latest user-supplied portfolio snapshot; confirm current cash, holdings and pending orders"}

    def fill(self, fill_id, symbol, side, quantity, price, fee, filled_at):
        reject_secrets({"fill_id": fill_id, "symbol": symbol, "filled_at": filled_at})
        market = instrument(self.settings, symbol)
        quantity = money(quantity)
        if quantity % money(market["lot_size"]):
            raise ValueError("Fractional quantity violates this instrument's configured lot size")
        price, fee = money(price), money(fee)
        if not fill_id.strip() or side not in {"buy", "sell"} or quantity <= 0 or price <= 0:
            raise ValueError("Need unique fill ID, buy/sell, positive quantity and price")
        if instant(filled_at) > instant(self.store.clock()):
            raise ValueError("Future fills are not actual executions")
        data = {"symbol": symbol, "side": side, "quantity": str(quantity), "price": str(price), "fee": str(fee),
                "filled_at": stamp(filled_at), "currency": market["currency"], "reported_by": "human"}
        with self.store.transaction():
            old = self.store.db.execute("SELECT data FROM fills WHERE id=?", (fill_id,)).fetchone()
            if old:
                if old[0] != canonical(data):
                    raise ValueError("Fill ID reused with different data")
                return False
            self.store.db.execute("INSERT INTO fills VALUES(?,?,?)", (fill_id, stamp(self.store.clock()), canonical(data)))
            self.store.event("human_fill_recorded", fill_id=fill_id, **data)
        return True

    def idea(self, prediction_id, portfolio):
        from .trial import trial_status
        if trial_status(self.engine)['status'] in {'review_required', 'stopped'}:
            raise ValueError('Live trial ended; record user performance review before new purchase suggestions')
        now = instant(self.store.clock())
        row = self.store.db.execute("SELECT * FROM predictions WHERE id=?", (prediction_id,)).fetchone()
        if row is None or instant(row["due_at"]) <= now:
            raise ValueError("Trade idea requires an active, unexpired forecast")
        signal_id = row["signal_id"]
        if self.store.state(signal_id) not in {"QUALIFIED", "ALERTED"}:
            raise ValueError("Trade ideas require a qualified signal")
        prediction = json.loads(row["data"])
        spec = self.store.spec(signal_id)
        if prediction["direction"] != "up":
            raise ValueError("Bearish research is informational; no short-selling recommendation")
        if (now - instant(row["at"])).total_seconds() > self.settings["max_quote_age_seconds"]:
            raise ValueError("Entry opportunity stale; obtain a fresh prediction")
        if (now - instant(prediction["reference_at"])).total_seconds() > self.settings["max_quote_age_seconds"]:
            raise ValueError("Reference quote stale; obtain a current tradable quote")
        snapshot = self.normalize_snapshot(portfolio)
        if snapshot["currency"] != self.settings["base_currency"]:
            raise ValueError("Purchase sizing requires portfolio cash in configured base currency")
        price = money(prediction["reference_price"])
        market = instrument(self.settings, spec["symbol"])
        tick, lot = money(market["price_tick"]), money(market["lot_size"])
        limit = ((price * Decimal("1.001")) / tick).to_integral_value(rounding=ROUND_UP) * tick
        fixed_fee = money(self.settings["brokerage"]["entry_fee_fixed"])
        unit_fee = money(self.settings["brokerage"]["entry_fee_per_unit"])
        self.record_snapshot(snapshot)
        with self.store.transaction():
            existing = self.store.db.execute("SELECT data FROM ideas WHERE id=?", (prediction_id,)).fetchone()
            if existing:
                idea = json.loads(existing[0])
                if idea.get("portfolio") == snapshot:
                    return idea
                raise ValueError("Purchase idea already recorded; review it against the current portfolio before reuse")
            zone = ZoneInfo(self.settings["timezone"])
            today = now.astimezone(zone).date()
            ideas_today = sum(instant(r[0]).astimezone(zone).date() == today
                              for r in self.store.db.execute("SELECT at FROM ideas"))
            if ideas_today >= self.settings["max_trade_ideas_per_day"]:
                raise ValueError("Daily trade-idea cap reached")
            reserved = sum((money(item["notional"]) + money(item.get("estimated_entry_fee", "0"))
                            for record in self.store.db.execute("SELECT data FROM ideas")
                            if instant((item := json.loads(record[0]))["expires_at"]) > now), Decimal(0))
            spendable = max(Decimal(0), money(snapshot["cash"]) - reserved - fixed_fee)
            units = (spendable / (limit + unit_fee) / lot).to_integral_value(rounding=ROUND_DOWN) * lot
            if units <= 0:
                raise ValueError("Cannot afford the configured minimum lot and entry fees with unreserved actual cash")
            fee = fixed_fee + units * unit_fee
            idea = {"id": prediction_id, "signal_id": signal_id, "symbol": spec["symbol"], "side": "buy",
                    "quantity": str(units), "currency": self.settings["base_currency"],
                    "suggested_limit": str(limit), "notional": str(units * limit),
                    "estimated_entry_fee": str(fee), "total_cash_required": str(units * limit + fee),
                    "portfolio": snapshot, "quote_at": prediction["reference_at"],
                    "expires_at": stamp(min(now + timedelta(minutes=15),
                                             instant(prediction["reference_at"]) + timedelta(seconds=self.settings["max_quote_age_seconds"]),
                                             instant(row["due_at"]))),
                    "forecast_due_at": row["due_at"], "target_return": prediction["target_return"],
                    "status": "recommendation_only", "exit_plan": "Review and manually close at the forecast horizon",
                    "record": self.engine.record(signal_id), "source": prediction["source"],
                    "checks_for_human": ["Confirm live broker bid/ask, fee estimate and available settled buying power",
                                         "Skip if spread, price, pending orders or account restrictions invalidate assumptions",
                                         "Report actual fill ID, time, units, price and fees"]}
            self.store.db.execute("INSERT INTO ideas VALUES(?,?,?)", (prediction_id, stamp(now), canonical(idea)))
            self.store.event("trade_idea", **idea)
        return idea
