"""Read current supplied portfolio; calculate affordable purchases."""

import json
import re
from datetime import timedelta
from decimal import Decimal, ROUND_UP, ROUND_DOWN

from .util import instant, stamp
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

    def idea(self, prediction_id, portfolio):
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
        spendable = max(Decimal(0), money(snapshot["cash"]) - fixed_fee)
        units = (spendable / (limit + unit_fee) / lot).to_integral_value(rounding=ROUND_DOWN) * lot
        if units <= 0:
            raise ValueError("Cannot afford the configured minimum lot and entry fees with supplied available cash")
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
                                     "Skip if spread, price, pending orders or account restrictions invalidate assumptions"]}
        return idea
