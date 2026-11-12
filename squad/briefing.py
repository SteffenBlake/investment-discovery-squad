"""Bounded evidence packet for LLM portfolio decisions; never place orders or fabricate fills."""

import json
import re

from .configuration import money, reject_secrets
from .knowledge import Knowledge
from .portfolio import Portfolio
from .util import instant, stamp, wilson


def portfolio_context(engine, portfolio=None, *, symbols=None, query=None, limit=15, hops=2):
    recorded = Portfolio(engine).balance()
    supplied = portfolio is not None
    portfolio = portfolio or {'cash': recorded['cash'], 'currency': recorded['currency'], 'holdings': recorded['holdings']}
    reject_secrets(portfolio)
    holdings = portfolio.get('holdings')
    if isinstance(holdings, list):
        if len({r['symbol'] for r in holdings}) != len(holdings):
            raise ValueError('Duplicate symbols in supplied holdings')
        holdings = {r['symbol']: r['quantity'] for r in holdings}
    if not isinstance(holdings, dict) or len(holdings) > 100:
        raise ValueError('Portfolio holdings must be a symbol-to-quantity object or a list, at most 100 positions')
    for symbol, quantity in holdings.items():
        if not isinstance(symbol, str) or not symbol.strip():
            raise ValueError('Portfolio symbol required')
        money(quantity)
    if 'cash' in portfolio:
        money(portfolio['cash'])
    if not re.fullmatch('[A-Z]{3}', portfolio.get('currency', '')):
        raise ValueError('Portfolio currency required')
    if portfolio.get('as_of') and instant(portfolio['as_of']) > instant(engine.store.clock()):
        raise ValueError('Portfolio snapshot cannot be from the future')
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
        stats = engine.store.db.execute('''SELECT count(p.id), count(o.prediction_id), COALESCE(sum(o.success),0)
          FROM predictions p LEFT JOIN outcomes o ON o.prediction_id=p.id WHERE p.signal_id=?''', (spec['id'],)).fetchone()
        registered, evaluated, successes = stats
        trial = engine.store.db.execute('SELECT data FROM trials WHERE signal_id=?', (spec['id'],)).fetchone()
        history = json.loads(trial[0]) if trial else None
        keys = ('passed', 'p_value', 'alpha', 'test_samples', 'test_events', 'mean_net_return', 'baseline_mean_net_return',
                'source', 'reasons', 'rule', 'availability_verified', 'test_last_exit', 'round_trip_cost_bps', 'limitations')
        active = list(engine.store.db.execute('SELECT id,due_at FROM predictions WHERE signal_id=? AND due_at>? ORDER BY due_at LIMIT 101',
                                             (spec['id'], stamp(engine.store.clock()))))
        summaries.append({'signal_id': spec['id'], 'symbol': spec['symbol'], 'state': engine.store.state(spec['id']),
                          'definition': {key: spec[key] for key in ('name', 'phenomenon', 'mechanism', 'horizon_days', 'target_return', 'limitations')},
                          'historical': {k: history[k] for k in keys if k in history} if history else None,
                          'forward': {'registered': registered, 'evaluated': evaluated, 'successes': successes,
                                      'failures': evaluated-successes, 'pending': registered-evaluated,
                                      'hit_rate_wilson_95': wilson(successes, evaluated)},
                          'active_forecasts': [dict(r) for r in active[:100]], 'active_forecasts_truncated': len(active) > 100,
                          'complete_record_command': 'report --signal ' + spec['id']})
    same_holdings = {s: money(q) for s, q in holdings.items() if money(q)} == {s: money(q) for s, q in recorded['holdings'].items() if money(q)}
    same_cash = 'cash' in portfolio and money(portfolio['cash']) == money(recorded['cash']) and portfolio['currency'] == recorded['currency']
    return {'at': stamp(engine.store.clock()), 'portfolio_supplied_by_user': supplied, 'portfolio': portfolio,
            'recorded_ledger': recorded, 'reconciliation_required': supplied and not (same_holdings and same_cash),
            'knowledge': knowledge, 'signals': summaries, 'signals_truncated': len(specs) > 50,
            'instruction': 'LLM recommends buy/hold/sell/avoid using current portfolio, dated evidence and contradictions; research claims do not authorize entry. Reconcile ledger before cash-sensitive trade ideas. No brokerage execution or implied fills.'}
