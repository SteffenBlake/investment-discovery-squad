"""One frozen test on untouched later history; every planned attempt spends alpha."""

import math
from statistics import mean

from .util import canonical, digest, finite, instant, stamp, wilson


def history_requirements(settings, holdout_rows, trial_number):
    alpha = settings['family_alpha'] / (trial_number * (trial_number + 1))
    required = max(settings['min_test_samples'], math.ceil(1 / alpha))
    return {'trial_number': trial_number, 'holdout_rows': holdout_rows, 'alpha': alpha,
            'minimum_attainable_p': 1 / holdout_rows if holdout_rows else None,
            'required_holdout_rows': required, 'correction_feasible': holdout_rows >= required}


def normalized_rows(dataset, spec, now):
    if not isinstance(dataset, dict):
        raise ValueError('Dataset must be an object')
    canonical(dataset)
    if not isinstance(dataset.get('source'), str) or not dataset['source'].strip():
        raise ValueError('Dataset needs source provenance')
    if not isinstance(dataset.get('limitations'), list) or not dataset['limitations'] or any(not isinstance(item, str) or not item.strip() for item in dataset['limitations']):
        raise ValueError('Dataset needs nonempty text limitations')
    if not isinstance(dataset.get('rows'), list) or any(not isinstance(row, dict) for row in dataset['rows']):
        raise ValueError('Dataset rows must be a list of objects')
    previous_exit, events, result = None, set(), []
    for row in dataset['rows']:
        if any(not isinstance(row.get(key), str) for key in ('available_at', 'entry_at', 'exit_at')):
            raise ValueError('Row timestamps must be strings with UTC offsets')
        available, entry, end = (instant(row[key]) for key in ('available_at', 'entry_at', 'exit_at'))
        if not available < entry < end <= instant(now):
            raise ValueError('Look-ahead/future outcome: require available_at < entry_at < exit_at <= now')
        if previous_exit and entry <= previous_exit:
            raise ValueError('Historical windows must be chronological and disjoint')
        if row['event_id'] in events:
            raise ValueError('Repeated historical event')
        if not spec['horizon_days'] <= (end - entry).total_seconds() / 86400 <= spec['horizon_days'] + 7:
            raise ValueError('Historical horizon differs from registered rule')
        previous_exit = end
        events.add(row['event_id'])
        result.append({**row, 'feature': finite(row['feature']),
                       'return': finite(row['exit_price'], positive=True) / finite(row['entry_price'], positive=True) - 1})
    return result


def prepare_plan(development, spec, windows, settings, number, now):
    rows = normalized_rows(development, spec, now)
    if len(rows) < settings['min_train_samples']:
        raise ValueError('Insufficient development history')
    if development.get('availability_verified') is not True or not development.get('availability_evidence'):
        raise ValueError('Development data needs original availability evidence')
    features = sorted(row['feature'] for row in rows)
    threshold = features[math.ceil(0.8 * len(features)) - 1]
    triggered = [row['return'] for row in rows if row['feature'] > threshold]
    if not triggered:
        raise ValueError('Development history needs events above fixed 80th percentile')
    history = history_requirements(settings, len(windows), number)
    if not history['correction_feasible']:
        raise ValueError('Plan needs at least ' + str(history['required_holdout_rows']) + ' untouched test windows')
    previous_exit = instant(rows[-1]['exit_at'])
    event_ids = set()
    for window in windows:
        if set(window) != {'event_id', 'entry_at', 'exit_at'}:
            raise ValueError('Freeze only event_id, entry_at and exit_at for each test window')
        entry, end = instant(window['entry_at']), instant(window['exit_at'])
        if not previous_exit < entry < end or window['event_id'] in event_ids:
            raise ValueError('Test windows must follow development history and remain disjoint')
        if not spec['horizon_days'] <= (end - entry).total_seconds() / 86400 <= spec['horizon_days'] + 7:
            raise ValueError('Test-window horizon differs from registered rule')
        previous_exit = end
        event_ids.add(window['event_id'])
    return {'trial_number': number, 'alpha': history['alpha'], 'history_requirements': history,
            'development_hash': digest(development), 'development_samples': len(rows),
            'development_last_exit': rows[-1]['exit_at'], 'test_windows': windows,
            'rule': {'threshold': threshold, 'direction': 'up' if mean(triggered) >= mean(row['return'] for row in rows) else 'down', 'quantile': 0.8},
            'round_trip_cost_bps': settings['round_trip_cost_bps'], 'min_test_events': settings['min_test_events'],
            'test': 'one-sided circular-shift alignment', 'exclusions': 'none; every frozen window required',
            'limitations': development['limitations']}


def test_rows(dataset, spec, plan, now):
    rows = normalized_rows(dataset, spec, now)
    windows = [{key: row[key] for key in ('event_id', 'entry_at', 'exit_at')} for row in rows]
    if windows != plan['test_windows']:
        raise ValueError('Test data must match every frozen window exactly, in order')
    if dataset.get('availability_verified') is not True or not dataset.get('availability_evidence'):
        raise ValueError('Original historical availability evidence required')
    return rows


def validate(dataset, spec, plan, now, *, rows=None):
    rows = test_rows(dataset, spec, plan, now) if rows is None else rows
    windows = plan['test_windows']
    sign = 1 if plan['rule']['direction'] == 'up' else -1
    returns = [sign * row['return'] - plan['round_trip_cost_bps'] / 10000 for row in rows]
    mask = [row['feature'] > plan['rule']['threshold'] for row in rows]
    chosen = [value for value, selected in zip(returns, mask) if selected]
    observed, baseline = mean(chosen) if chosen else 0.0, mean(returns)
    if chosen:
        null = [mean(returns[(index + shift) % len(rows)] for index, selected in enumerate(mask) if selected)
                for shift in range(len(rows))]
        p_value = sum(value >= observed - 1e-12 for value in null) / len(null)
    else:
        p_value = 1.0
    reasons = []
    if len(chosen) < plan['min_test_events']:
        reasons.append('Too few triggered test events')
    if observed <= 0 or observed <= baseline:
        reasons.append('Net return must exceed cash and ordinary same-direction return')
    if p_value > plan['alpha']:
        reasons.append('Failed correction for registered hypotheses')
    successes = sum(value >= spec['target_return'] for value in chosen)
    return {'passed': not reasons, 'reasons': reasons, 'dataset_hash': digest(dataset), 'source': dataset['source'],
            'synthetic': bool(dataset.get('synthetic')), 'availability_verified': True,
            'availability_evidence': dataset.get('availability_evidence'), 'rule': plan['rule'],
            'train_samples': plan['development_samples'], 'test_samples': len(rows), 'test_events': len(chosen),
            'train_last_exit': plan['development_last_exit'], 'test_first_entry': rows[0]['entry_at'],
            'test_last_exit': rows[-1]['exit_at'], 'mean_net_return': observed, 'baseline_mean_net_return': baseline,
            'baseline': 'Same-direction returns across every frozen test window, plus cash',
            'improvement': observed - baseline, 'round_trip_cost_bps': plan['round_trip_cost_bps'],
            'p_value': p_value, 'alpha': plan['alpha'], 'trial_number': plan['trial_number'],
            'history_requirements': plan['history_requirements'],
            'correction': 'Lifetime alpha spending: family_alpha / (k * (k + 1)); planned attempts consume k',
            'successes': successes, 'hit_rate': successes / len(chosen) if chosen else None,
            'hit_rate_wilson_95': wilson(successes, len(chosen)), 'evaluated_at': stamp(now),
            'limitations': list(dict.fromkeys(plan['limitations'] + dataset['limitations'] + [
                'Circular-shift test assumes approximate stationarity and exchangeable alignment under null',
                'Historical evidence supports further investigation; future performance remains uncertain',
                'Wilson interval assumes independent Bernoulli outcomes'])),
            'holdout_events': [{**window, 'net_return': value} for window, value, selected in zip(windows, returns, mask) if selected]}
