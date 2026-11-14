"""Research context for supplied current portfolio."""

import json

from .knowledge import Knowledge
from .portfolio import Portfolio
from .util import stamp


def portfolio_context(engine, portfolio=None, *, symbols=None, query=None, limit=15, hops=2):
    supplied = portfolio is not None
    portfolio = Portfolio(engine).normalize_snapshot(portfolio) if supplied else None
    holdings = portfolio['holdings'] if supplied else {}
    selected = list(dict.fromkeys(symbols or holdings.keys() or [i['symbol'] for i in engine.settings['instruments']]))
    with Knowledge(engine.settings, engine.store.identity) as graph:
        knowledge = graph.context(selected, query=query, limit=limit, hops=hops)
    related_symbols = set(selected) | {r['symbol'] for r in knowledge['related_entities'] if r and r.get('symbol')}
    placeholders = ','.join('?' for _ in related_symbols)
    specs = [json.loads(row['data']) for row in engine.store.db.execute(
        f"SELECT data FROM specs WHERE json_extract(data,'$.symbol') IN ({placeholders}) ORDER BY at DESC LIMIT 51",
        tuple(sorted(related_symbols)))]
    summaries = []
    for spec in specs[:50]:
        stats = engine.record(spec['id'])
        trial = engine.store.db.execute('SELECT data FROM trials WHERE signal_id=?', (spec['id'],)).fetchone()
        history = json.loads(trial[0]) if trial else None
        keys = ('passed', 'p_value', 'alpha', 'test_samples', 'test_events', 'mean_net_return', 'baseline_mean_net_return',
                'source', 'reasons', 'rule', 'availability_verified', 'test_last_exit', 'round_trip_cost_bps', 'limitations')
        active = list(engine.store.db.execute('SELECT id,due_at FROM predictions WHERE signal_id=? AND due_at>? ORDER BY due_at LIMIT 101',
                                             (spec['id'], stamp(engine.store.clock()))))
        summaries.append({'signal_id': spec['id'], 'symbol': spec['symbol'], 'state': engine.store.state(spec['id']),
                          'definition': {key: spec[key] for key in ('name', 'phenomenon', 'mechanism', 'horizon_days', 'target_return', 'limitations')},
                          'historical': {k: history[k] for k in keys if k in history} if history else None,
                          'forward': {key: value for key, value in stats.items() if key != 'predictions'},
                          'active_forecasts': [dict(r) for r in active[:100]], 'active_forecasts_truncated': len(active) > 100,
                          'complete_record_command': 'report --signal ' + spec['id']})
    return {'at': stamp(engine.store.clock()), 'portfolio_supplied_by_user': supplied, 'portfolio': portfolio,
            'knowledge': knowledge, 'signals': summaries, 'signals_truncated': len(specs) > 50,
            'instruction': 'Recommend buy/hold/sell/cash using the supplied actual portfolio, dated evidence, contradictions and numerical qualification. Obtain an actual portfolio snapshot before purchase sizing.'}
