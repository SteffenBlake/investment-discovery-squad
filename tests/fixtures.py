import json
from pathlib import Path

from squad.configuration import configuration_template, environment_fields


def completed_profile(folder, *, profile_id="test-owner", currency="USD", cash="1000.00", timezone="UTC", lot="1"):
    folder = Path(folder).resolve()
    profile = configuration_template()
    profile.update(profile_id=profile_id, timezone=timezone, jurisdiction="Synthetic test jurisdiction",
                   base_currency=currency, starting_cash=cash, money_decimals=0 if currency == "JPY" else 2,
                   max_trade_ideas_per_day=4, max_candidates_per_day=1, round_trip_cost_bps=20,
                   brokerage={"name": "Fictional mechanism", "execution_mode": "human", "constraints": "Test only"},
                   worker={"model": None, "reasoning_effort": None},
                   spending={"additional_services_budget": "0"}, notification={"destination": "synthetic://owner"},
                   instruments=[{"symbol": "SYNTH", "currency": currency, "exchange_timezone": timezone,
                                 "close_time": "16:00", "weekdays": [0,1,2,3,4], "lot_size": lot, "price_tick": "0.01"}],
                   storage={"backend": "ladybug", "database_path": str(folder / "data" / "ledger.sqlite3"),
                            "knowledge_path": str(folder / "data" / "knowledge.lbdb"),
                            "cloud_backup": {"provider": "google_drive", "folder_id": "fictional-folder", "max_bytes": 100_000_000, "max_archive_bytes": 10_000_000},
                            "backup_directory": str(folder / "backups"), "backup_interval_hours": 24, "backup_retention_days": 14,
                            "runtime_id": "synthetic-host", "decision_accepted": True},
                   gitops={"ref": "main", "update_policy": "fast_forward"})
    for schedule in profile["schedules"].values():
        schedule.update(enabled=True, rrule="RRULE:FREQ=DAILY;BYHOUR=12;BYMINUTE=0;BYSECOND=0")
    return profile


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


def native_environment(profile):
    """Serialize personal fields only; fixed architecture has no environment switches."""
    result = {}
    for name, (path, kind) in environment_fields().items():
        value = profile
        for part in path:
            value = value[part]
        result[name] = value if kind == 'string' and isinstance(value, str) else json.dumps(value)
    return result
