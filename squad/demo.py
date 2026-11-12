"""Synthetic-only acceptance fixture; no fabricated predictions enter production."""

import random
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from .engine import Engine
from .store import Store
from .util import UTC, stamp
from .util import config


def demo_settings():
    """Explicitly fictional test defaults; never used for production onboarding."""
    return {**config(), "profile_id": "synthetic", "timezone": "UTC", "base_currency": "USD",
            "starting_cash": "1000.00", "money_decimals": 2, "max_trade_ideas_per_day": 4,
            "max_candidates_per_day": 1, "round_trip_cost_bps": 20,
            "brokerage": {"name": "Synthetic test mechanism", "execution_mode": "human", "constraints": "Fictional"},
            "research_universe": [], "instruments": [{"symbol": "SYNTH", "currency": "USD",
              "exchange_timezone": "UTC", "close_time": "16:00", "weekdays": [0,1,2,3,4],
              "lot_size": "1", "price_tick": "0.01"}]}


class DemoClock:
    def __init__(self, value=None):
        self.value = value or datetime(2025, 1, 1, 15, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, **kwargs):
        self.value += timedelta(**kwargs)


def historical_fixture():
    randomizer = random.Random(7361)
    start = datetime(2018, 1, 1, tzinfo=UTC)
    rows = []
    for i in range(900):
        entry = start + timedelta(days=2 * i)
        feature = randomizer.random()
        ret = (0.04 if feature > 0.8 else -0.005) + randomizer.uniform(-0.001, 0.001)
        rows.append({"event_id": f"synthetic-history-{i}", "available_at": stamp(entry - timedelta(hours=1)),
                     "entry_at": stamp(entry), "exit_at": stamp(entry + timedelta(days=1)),
                     "feature": feature, "entry_price": 100, "exit_price": 100 * (1 + ret)})
    return {"synthetic": True, "source": "Synthetic deterministic acceptance fixture; not market evidence",
            "availability_verified": True, "availability_evidence": "Generated causal chronology with explicit timestamps",
            "limitations": ["Fabricated data validate software behavior only"], "rows": rows}


def spec_fixture(signal_id="synthetic-acceptance-v1"):
    return {"id": signal_id, "name": "SYNTHETIC acceptance signal", "phenomenon": "Synthetic attention spikes",
            "mechanism": "Deterministic generated relationship, not a discovered investment edge",
            "symbol": "SYNTH", "horizon_days": 1, "target_return": 0.005,
            "limitations": ["Synthetic acceptance test; never a trading recommendation"]}


def acceptance(settings=None, destination=None):
    settings = settings or demo_settings()
    if destination is None:
        with tempfile.TemporaryDirectory(prefix="squad-acceptance-") as folder:
            return _acceptance(settings, Path(folder))
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    if (destination / "acceptance.sqlite3").exists():
        raise ValueError("Use a new demo directory; never overwrite an evidence ledger")
    return _acceptance(settings, destination)


def _acceptance(settings, folder):
    clock = DemoClock()
    db = folder / "acceptance.sqlite3"
    store = Store(db, mode="synthetic", clock=clock)
    engine = Engine(store, settings)
    spec = spec_fixture()
    engine.discover(spec)
    backtest = engine.backtest(spec["id"], historical_fixture())
    assert backtest["passed"], backtest["reasons"]
    checkpoints = []
    # The additional failed forecast matures before the third successful forecast.
    # This permits a truthful 3-of-4 record in the first immediate alert.
    ids = []
    for index, success in enumerate((True, True, False, True)):
        due = clock() + timedelta(days=1)
        ids.append(engine.register(spec["id"], f"independent-episode-{index + 1}",
                                   event_available_at=clock() - timedelta(minutes=1),
                                   due_at=due, quote_at=clock(), reference_price=10,
                                   source="synthetic://fixture"))
        engine.evaluate()
        assert store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 0
        clock.advance(days=1)
        engine.record_price(spec["symbol"], due, 10.2 if success else 9.8, source="synthetic://outcome")
        if index < 3:
            engine.evaluate()
            checkpoints.append({"evaluated_successes": engine.record(spec["id"])["successes"], "alert_count": 0})
        clock.advance(minutes=1)
    before = store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    assert before == 0
    engine.evaluate()
    row = store.db.execute("SELECT * FROM outbox").fetchone()
    assert row is not None and row["at"] == stamp(clock())
    record = engine.record(spec["id"])
    assert (record["successes"], record["failures"], record["evaluated"]) == (3, 1, 4)
    assert store.state(spec["id"]) == "QUALIFIED"
    claimed = engine.claim(row["id"])
    assert claimed["payload"]["forward_predictions"]["failures"] == 1
    assert engine.claim(row["id"]) is None
    receipt = "synthetic://delivery-receipt/1"
    engine.acknowledge(row["id"], claimed["token"], receipt)
    engine.acknowledge(row["id"], claimed["token"], receipt)
    store.export(folder / "knowledge.json")
    store.close()
    store = Store(db, mode="synthetic", clock=clock)
    engine = Engine(store, settings)
    engine.evaluate()
    assert engine.claim(row["id"]) is None
    assert store.state(spec["id"]) == "ALERTED"
    assert store.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0] == 1
    result = {"passed": True, "synthetic": True, "purpose": "Software acceptance, not real investment evidence",
              "historical_backtest_passed": backtest["passed"],
              "checkpoints": checkpoints,
              "no_alert_before_third_success_evaluated": before == 0,
              "alert_queued_on_qualifying_execution": row["at"],
              "full_record": engine.record(spec["id"]),
              "persisted_state_after_restart": store.state(spec["id"]),
              "persisted_delivery_receipt": store.db.execute("SELECT receipt FROM outbox").fetchone()[0],
              "alert_count_after_repeat_and_restart": 1,
              "notification_transport": "Synthetic receipt; real Dot delivery requires activation and smoke test"}
    store.close()
    return result
