"""Thirty-day live observation periods and recorded performance reviews."""

import json
import math
from datetime import timedelta

from .configuration import reject_secrets
from .util import instant, stamp


def trial_status(engine):
    row = engine.store.db.execute("""SELECT at,kind,data FROM events
      WHERE kind IN ('live_trial_started','live_trial_reviewed') ORDER BY seq DESC LIMIT 1""").fetchone()
    if row is None:
        return {'status': 'not_started', 'initial_maximum_days': 30}
    data = json.loads(row['data'])
    if data.get('decision') == 'stop':
        return {**data['report'], 'status': 'stopped', 'reviewed_at': row['at'], 'reason': data['reason']}
    status = 'active' if instant(engine.store.clock()) < instant(data['ends_at']) else 'review_required'
    started = data.get('started_at', row['at'])
    first_row = engine.store.db.execute("SELECT at,data FROM events WHERE kind='live_trial_started' ORDER BY seq LIMIT 1").fetchone()
    first = json.loads(first_row['data']).get('started_at', first_row['at'])
    signals = []
    for signal in engine.store.db.execute('SELECT id FROM signals ORDER BY id'):
        record = engine.record(signal[0])
        predictions = [p for p in record['predictions'] if instant(p['registered_at']) >= instant(started)]
        if not predictions:
            continue
        valid = [p for p in predictions if p['outcome_valid']]
        original = predictions[0]
        symbol = engine.store.spec(signal[0])['symbol']
        endpoint = engine.store.db.execute("""SELECT data,market_at FROM prices WHERE symbol=? AND kind='close'
          AND market_at>=? AND market_at<=? ORDER BY market_at DESC LIMIT 1""",
          (symbol, original['reference_at'], min(stamp(engine.store.clock()), data.get('ends_at', stamp(engine.store.clock()))))).fetchone()
        signals.append({'signal_id': signal[0], 'symbol': symbol, 'registered': len(predictions),
                        'completed': len(valid), 'successes': sum(p['success'] for p in valid),
                        'failures': sum(not p['success'] for p in valid),
                        'pending': sum(p['outcome'] is None for p in predictions),
                        'invalidated': sum(p['outcome'] is not None and not p['outcome_valid'] for p in predictions),
                        'forecast_net_returns': [p['outcome']['net_return'] for p in valid],
                        'forecast_compounded_net_return': math.prod(1 + p['outcome']['net_return'] for p in valid) - 1 if valid else None,
                        'buy_and_hold_net_return': json.loads(endpoint['data'])['price'] / original['reference_price'] - 1 - original['cost_bps'] / 10000 if endpoint else None,
                        'predictions': predictions})
    fills = [dict(r) for r in engine.store.db.execute('SELECT id,at,data FROM fills WHERE at>=? ORDER BY at', (started,))]
    return {'status': status, 'first_started_at': first, 'period_started_at': started,
            'ends_at': data.get('ends_at'), 'signals': signals, 'reported_fills': fills,
            'measurement': 'Forecast returns after configured costs; actual reported trades listed separately',
            'review': 'Review all outcomes, pending results and comparison before deciding whether to continue'}


def review_trial(engine, *, decision, reason, user_approval, days=30):
    reject_secrets({'reason': reason, 'user_approval': user_approval})
    if decision not in {'continue', 'stop'} or not reason.strip() or not user_approval.strip():
        raise ValueError('Review needs continue/stop, performance reason and actual user approval evidence')
    if type(days) is not int or not 1 <= days <= 30:
        raise ValueError('Reviewed continuation lasts 1 to 30 days')
    report = trial_status(engine)
    if report['status'] == 'not_started':
        raise ValueError('Start live observations before reviewing their performance')
    started = instant(engine.store.clock())
    with engine.store.transaction():
        engine.store.event('live_trial_reviewed', decision=decision, reason=reason, user_approval=user_approval,
                           started_at=stamp(started), ends_at=stamp(started + timedelta(days=days)), report=report)
    return trial_status(engine)
