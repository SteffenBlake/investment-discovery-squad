import json
import random
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from investment_engine.configuration import configuration_template, environment_fields
from investment_engine.engine import Engine
from investment_engine.ledger import Store
from investment_engine.util import UTC, load_method_settings, stamp


def completed_installation(folder, *, profile_id="test-owner", currency="USD", timezone="UTC", lot="1"):
    folder = Path(folder).resolve()
    installation = configuration_template()
    installation.update(profile_id=profile_id, timezone=timezone, jurisdiction="Synthetic test jurisdiction",
                   risk_preferences='Synthetic risk restrictions for isolated tests',
                   base_currency=currency, max_candidates_per_day=1, round_trip_cost_bps=20,
                   brokerage={"name": "Fictional mechanism", "execution_mode": "human", "constraints": "Test only",
                              "entry_fee_fixed": "0", "entry_fee_per_unit": "0"},
                   worker={"model": None, "reasoning_effort": None},
                   spending={"additional_services_budget": "0"}, notification={"destination": "synthetic://owner"},
                   instruments=[{"symbol": "SYNTH", "currency": currency, "exchange_timezone": timezone,
                                 "exchange_calendar": "XNYS", "lot_size": lot, "price_tick": "0.01"}],
                   storage={"backend": "ladybug", "database_path": str(folder / "data" / "ledger.sqlite3"),
                            "knowledge_path": str(folder / "data" / "knowledge.lbdb"),
                            "cloud_backup": {"provider": "google_drive", "folder_id": "fictional-folder", "max_bytes": 100_000_000, "max_archive_bytes": 10_000_000},
                            "backup_directory": str(folder / "backups"), "backup_interval_hours": 24,
                            "runtime_id": "synthetic-host", "decision_accepted": True},
                   gitops={"ref": "main", "update_policy": "fast_forward"})
    for schedule in installation["schedules"].values():
        schedule.update(enabled=True, rrule="RRULE:FREQ=DAILY;BYHOUR=12;BYMINUTE=0;BYSECOND=0")
    return installation


def research_batch(batch_id='test-batch'):
    """Fictional records for isolated software tests; never real investment evidence."""
    return {'schema_version': 1, 'id': batch_id,
            'entities': [{'id': 'asset:SYNTH', 'kind': 'asset', 'label': 'Fictional holding', 'symbol': 'SYNTH'},
                         {'id': 'company:supplier', 'kind': 'company', 'label': 'Fictional supplier'}],
            'sources': [{'id': 'source:one', 'url': 'https://example.invalid/original', 'title': 'Fictional source fixture',
                         'content': 'Port congestion delays component shipments. This is synthetic software test content.'}],
            'claims': [{'id': 'claim:one', 'text': 'Port congestion threatens component supply', 'status': 'hypothesis',
                        'confidence': 0.4, 'entity_ids': ['company:supplier'], 'source_ids': ['source:one']}],
            'relationships': [{'id': 'relation:one', 'from': 'company:supplier', 'to': 'asset:SYNTH',
                               'kind': 'SUPPLIES', 'claim_id': 'claim:one'}]}


def native_environment(installation):
    """Serialize personal fields only; fixed architecture has no environment switches."""
    result = {}
    for name, (path, kind) in environment_fields().items():
        value = installation
        for part in path:
            value = value[part]
        result[name] = value if kind == 'string' and isinstance(value, str) else json.dumps(value)
    return result


def demo_settings():
    """Explicitly fictional test defaults; never used for production onboarding."""
    return {**load_method_settings(), "profile_id": "synthetic", "timezone": "UTC", "base_currency": "USD",
            "max_candidates_per_day": 1, "round_trip_cost_bps": 20,
            "brokerage": {"name": "Synthetic test mechanism", "execution_mode": "human", "constraints": "Fictional",
                          "entry_fee_fixed": "0", "entry_fee_per_unit": "0"},
            "research_universe": [], "instruments": [{"symbol": "SYNTH", "currency": "USD",
              "exchange_timezone": "UTC", "exchange_calendar": "XNYS",
              "lot_size": "1", "price_tick": "0.01"}]}


class DemoClock:
    def __init__(self, value=None):
        self.value = value or datetime(2025, 1, 1, 15, tzinfo=UTC)

    def __call__(self):
        return self.value

    def advance(self, **kwargs):
        self.value += timedelta(**kwargs)


def historical_fixture(start=None):
    randomizer = random.Random(7361)
    start = start or datetime(2018, 1, 1, tzinfo=UTC)
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
            "family_id": "synthetic-attention", "input_id": "wikimedia:pageviews",
            "feature_formula": {"operation": "ratio_to_mean", "lookback_days": 28},
            "limitations": ["Synthetic acceptance test; never a trading recommendation"]}


def prepare_test_fixture(engine, signal_id, dataset):
    split = int(len(dataset['rows']) * 0.6)
    development = {**dataset, 'rows': dataset['rows'][:split]}
    holdout = {**dataset, 'rows': dataset['rows'][split:]}
    engine.prepare_test(signal_id, development,
                        [{key: row[key] for key in ('event_id', 'entry_at', 'exit_at')} for row in holdout['rows']],
                        holdout_unseen=True)
    return holdout


def formal_test(engine, signal_id, dataset):
    if not engine.store.db.execute('SELECT 1 FROM test_plans WHERE signal_id=?', (signal_id,)).fetchone():
        holdout = prepare_test_fixture(engine, signal_id, dataset)
    else:
        holdout = {**dataset, 'rows': dataset['rows'][int(len(dataset['rows']) * 0.6):]}
    return engine.backtest(signal_id, holdout)


def acceptance(settings=None):
    settings = settings or demo_settings()
    with tempfile.TemporaryDirectory(prefix='squad-acceptance-') as folder:
        clock = DemoClock()
        path = Path(folder) / 'acceptance.sqlite3'
        store = Store(path, mode='synthetic', clock=clock)
        engine = Engine(store, settings)
        spec = spec_fixture()
        engine.discover(spec)
        assert formal_test(engine, spec['id'], historical_fixture())['passed']
        assert store.state(spec['id']) == 'QUALIFIED'
        for index, success in enumerate((True, True, False, True)):
            engine.register(spec['id'], 'episode-' + str(index), event_available_at=clock() - timedelta(minutes=1),
                            quote_at=clock(), reference_price=10, source='synthetic://fixture', feature_value=1)
            clock.advance(days=1)
            engine.record_price('SYNTH', clock(), 10.2 if success else 9.8, source='synthetic://outcome')
            engine.evaluate()
            clock.advance(minutes=1)
        alert = store.db.execute('SELECT id FROM outbox').fetchone()[0]
        claimed = engine.claim(alert)
        assert claimed['payload']['forward_predictions']['failures'] == 1
        assert engine.claim(alert) is None
        engine.acknowledge(alert, claimed['token'], 'synthetic://receipt')
        engine.acknowledge(alert, claimed['token'], 'synthetic://receipt')
        store.close()
        store = Store(path, mode='synthetic', clock=clock)
        engine = Engine(store, settings)
        engine.evaluate()
        assert engine.claim(alert) is None
        result = {'passed': True, 'full_record': engine.record(spec['id']),
                  'persisted_state_after_restart': store.state(spec['id']),
                  'alert_count_after_repeat_and_restart': store.db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0]}
        store.close()
        return result
