"""Conservative chronological validation; never accepts a supplied 'passed' flag."""

import math
from statistics import mean

from .util import digest, finite, instant, stamp, wilson


def validate(dataset, spec, settings, trial_number, now):
    rows = dataset.get("rows", [])
    if not dataset.get("source") or not dataset.get("limitations"):
        raise ValueError("Dataset needs source provenance and limitations")
    if len(rows) < settings["min_train_samples"] + settings["min_test_samples"]:
        raise ValueError("Insufficient chronological history")
    previous_exit = None
    event_ids = set()
    normalized = []
    for row in rows:
        available, entry, end = (instant(row[k]) for k in ("available_at", "entry_at", "exit_at"))
        if not available < entry < end <= instant(now):
            raise ValueError("Look-ahead/future outcome: require available_at < entry_at < exit_at <= now")
        if previous_exit and entry <= previous_exit:
            raise ValueError("Historical windows must be chronological, disjoint, and purged")
        if row["event_id"] in event_ids:
            raise ValueError("Repeated underlying historical event")
        duration = (end - entry).total_seconds() / 86400
        if not spec["horizon_days"] <= duration <= spec["horizon_days"] + 7:
            raise ValueError("Historical horizon differs from the registered rule")
        previous_exit = end
        event_ids.add(row["event_id"])
        price = finite(row["entry_price"], positive=True)
        ret = finite(row["exit_price"], positive=True) / price - 1
        normalized.append({**row, "feature": finite(row["feature"]), "return": ret})
    split = int(len(rows) * 0.6)
    train, test = normalized[:split], normalized[split:]
    if len(train) < settings["min_train_samples"] or len(test) < settings["min_test_samples"]:
        raise ValueError("Insufficient train/holdout samples")
    # Every candidate uses the same predeclared rule. No holdout parameter tuning.
    features = sorted(r["feature"] for r in train)
    threshold = features[math.ceil(0.8 * len(features)) - 1]
    train_events = [r for r in train if r["feature"] > threshold]
    if not train_events:
        raise ValueError("No training events above the fixed 80th percentile")
    difference = mean(r["return"] for r in train_events) - mean(r["return"] for r in train)
    direction = "up" if difference >= 0 else "down"
    sign = 1 if direction == "up" else -1
    costs = settings["round_trip_cost_bps"] / 10000
    returns = [sign * r["return"] - costs for r in test]
    mask = [r["feature"] > threshold for r in test]
    chosen = [ret for ret, selected in zip(returns, mask) if selected]
    observed = mean(chosen) if chosen else 0.0
    baseline = mean(returns)
    # Circular shifts preserve clustering/order within each time series. Under the
    # stationary no-alignment null each offset is equally likely. Report that assumption.
    if chosen:
        null_means = [mean(returns[(i + shift) % len(test)] for i, selected in enumerate(mask) if selected)
                      for shift in range(len(test))]
        p_value = sum(x >= observed - 1e-12 for x in null_means) / len(null_means)
    else:
        p_value = 1.0
    # Alpha spending across every attempted candidate, including rejects and revisions.
    # Sum alpha/(k*(k+1)) over all k is alpha. No resetting on a new day/family.
    alpha = settings["family_alpha"] / (trial_number * (trial_number + 1))
    verified = dataset.get("availability_verified") is True and bool(dataset.get("availability_evidence"))
    reasons = []
    if not verified:
        reasons.append("Historical first-availability evidence unverified; exploratory only")
    if len(chosen) < settings["min_test_events"]:
        reasons.append("Too few independent holdout events")
    if observed <= 0 or observed <= baseline:
        reasons.append("No net improvement over cash and unconditional same-direction baseline")
    if p_value > alpha:
        reasons.append("Failed correction for all registered hypotheses")
    successes = sum(r >= spec["target_return"] for r in chosen)
    return {
        "passed": not reasons, "reasons": reasons, "dataset_hash": digest(dataset),
        "source": dataset["source"], "synthetic": bool(dataset.get("synthetic")),
        "availability_verified": verified,
        "availability_evidence": dataset.get("availability_evidence"),
        "rule": {"threshold": threshold, "direction": direction, "quantile": 0.8},
        "train_samples": len(train), "test_samples": len(test), "test_events": len(chosen),
        "train_last_exit": train[-1]["exit_at"], "test_first_entry": test[0]["entry_at"],
        "test_last_exit": test[-1]["exit_at"],
        "mean_net_return": observed, "baseline_mean_net_return": baseline,
        "baseline": "Unconditional same-direction position over the same disjoint holdout windows, plus cash",
        "improvement": observed - baseline, "round_trip_cost_bps": settings["round_trip_cost_bps"],
        "p_value": p_value, "alpha": alpha, "trial_number": trial_number,
        "correction": "Lifetime alpha spending: family_alpha / (k * (k + 1)); rejects consume k",
        "successes": successes, "hit_rate": successes / len(chosen) if chosen else None,
        "hit_rate_wilson_95": wilson(successes, len(chosen)),
        "evaluated_at": stamp(now),
        "limitations": list(dataset["limitations"]) + [
            "Circular-shift test assumes approximate stationarity and no predictive alignment under the null",
            "A fixed chronological holdout does not establish performance in future market regimes",
            "Wilson interval assumes independent Bernoulli outcomes; residual dependence widens uncertainty",
            "Research universe is selected, not a survivorship-free sample of all possible indicators",
        ],
        "holdout_events": [{"event_id": r["event_id"], "entry_at": r["entry_at"],
                            "exit_at": r["exit_at"], "net_return": sign * r["return"] - costs}
                           for r, selected in zip(test, mask) if selected],
    }
