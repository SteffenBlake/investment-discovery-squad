"""Human-reported fills only. Ideas never imply approval, submission or execution."""

import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation, ROUND_UP, ROUND_DOWN
from zoneinfo import ZoneInfo

from .util import canonical, instant, stamp
from .configuration import instrument


def amount(value):
    try:
        value = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("Invalid monetary amount") from exc
    if not value.is_finite() or value < 0:
        raise ValueError("Amount must be finite and nonnegative")
    return value


class Portfolio:
    def __init__(self, engine):
        self.engine = engine
        self.store, self.settings = engine.store, engine.settings

    def balance(self):
        cash = amount(self.settings["starting_cash"])
        holdings = {}
        for row in self.store.db.execute("SELECT data FROM fills ORDER BY rowid"):
            f = json.loads(row[0])
            quantity, price, fee = amount(f["quantity"]), amount(f["price"]), amount(f["fee"])
            if f["side"] == "buy":
                cash -= quantity * price + fee
                holdings[f["symbol"]] = holdings.get(f["symbol"], 0) + quantity
            else:
                cash += quantity * price - fee
                holdings[f["symbol"]] = holdings.get(f["symbol"], 0) - quantity
        quantum = Decimal(1).scaleb(-self.settings["money_decimals"])
        return {"cash": str(cash.quantize(quantum)), "currency": self.settings["base_currency"],
                "holdings": {k: str(v) for k, v in holdings.items() if v},
                "note": "User-reported ledger; confirm settled buying power and pending broker orders before placing another order"}

    def fill(self, fill_id, symbol, side, quantity, price, fee, filled_at):
        market = instrument(self.settings, symbol)
        quantity = amount(quantity)
        if quantity % amount(market["lot_size"]):
            raise ValueError("Fractional quantity violates this instrument's configured lot size")
        price, fee = amount(price), amount(fee)
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
            balance = self.balance()
            if side == "buy" and quantity * price + fee > amount(balance["cash"]):
                raise ValueError("Insufficient recorded cash; reconcile ledger first")
            if side == "sell" and quantity > amount(balance["holdings"].get(symbol, 0)):
                raise ValueError("Cannot sell more units than user reported holding")
            self.store.db.execute("INSERT INTO fills VALUES(?,?,?)", (fill_id, stamp(self.store.clock()), canonical(data)))
            self.store.event("human_fill_recorded", fill_id=fill_id, **data)
        return True

    def idea(self, prediction_id):
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
        # A forecast registered days ago is not a fresh entry. New ideas expire quickly.
        if (now - instant(row["at"])).total_seconds() > self.settings["max_quote_age_seconds"]:
            raise ValueError("Entry opportunity stale; do not chase an old prediction")
        if (now - instant(prediction["reference_at"])).total_seconds() > self.settings["max_quote_age_seconds"]:
            raise ValueError("Reference quote stale; obtain a current tradable quote")
        price = amount(prediction["reference_price"])
        market = instrument(self.settings, spec["symbol"])
        tick = amount(market["price_tick"])
        lot = amount(market["lot_size"])
        limit = ((price * Decimal("1.001")) / tick).to_integral_value(rounding=ROUND_UP) * tick
        with self.store.transaction():
            existing = self.store.db.execute("SELECT data FROM ideas WHERE id=?", (prediction_id,)).fetchone()
            if existing:
                return json.loads(existing[0])
            zone = ZoneInfo(self.settings["timezone"])
            today = now.astimezone(zone).date()
            ideas_today = sum(instant(r[0]).astimezone(zone).date() == today
                              for r in self.store.db.execute("SELECT at FROM ideas"))
            if ideas_today >= self.settings["max_trade_ideas_per_day"]:
                raise ValueError("Daily trade-idea cap reached")
            # Reserve notional for outstanding unexpired ideas so simultaneous ideas
            # cannot collectively spend the same cash. Fills supersede ideas only after expiry.
            reserved = sum((amount(json.loads(r[0])["notional"]) for r in
                            self.store.db.execute("SELECT data FROM ideas")
                            if instant(json.loads(r[0])["expires_at"]) > now), Decimal(0))
            balance = self.balance()
            spendable = max(Decimal(0), amount(balance["cash"]) - reserved)
            units = (spendable / limit / lot).to_integral_value(rounding=ROUND_DOWN) * lot
            if units <= 0:
                raise ValueError("Cannot afford the configured minimum lot with unreserved recorded cash")
            idea = {"id": prediction_id, "signal_id": signal_id, "symbol": spec["symbol"], "side": "buy",
                    "quantity": str(units), "currency": self.settings["base_currency"],
                    "suggested_limit": str(limit), "notional": str(units * limit),
                    "quote_at": prediction["reference_at"],
                    "expires_at": stamp(min(now + timedelta(minutes=15),
                                             instant(prediction["reference_at"]) + timedelta(seconds=self.settings["max_quote_age_seconds"]),
                                             instant(row["due_at"]))),
                    "forecast_due_at": row["due_at"], "target_return": prediction["target_return"],
                    "status": "recommendation_only", "exit_plan": "Review and manually close at the forecast horizon; no automatic exit",
                    "record": self.engine.record(signal_id), "source": prediction["source"],
                    "checks_for_human": ["Confirm live broker bid/ask and available settled buying power",
                                         "Skip if spread, price, or account restrictions invalidate assumptions",
                                         "Report actual fill ID, time, units, price and fees; approval alone is not a fill"]}
            self.store.db.execute("INSERT INTO ideas VALUES(?,?,?)", (prediction_id, stamp(now), canonical(idea)))
            self.store.event("trade_idea", **idea)
        return idea
