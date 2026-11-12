"""Complete qualification message for Dot's supported chat/notification surface."""

from zoneinfo import ZoneInfo

from .util import instant


def alert_message(payload, timezone="UTC"):
    zone = ZoneInfo(timezone)

    def local(timestamp):
        return instant(timestamp).astimezone(zone).isoformat(timespec="seconds")

    historical = payload["historical_evidence"]
    forward = payload["forward_predictions"]
    low, high = forward["hit_rate_wilson_95"]
    lines = [
        "HIGH PRIORITY — signal qualified" + (" [SYNTHETIC TEST]" if payload["synthetic"] else ""),
        f"Signal: {payload['name']} ({payload['symbol']})",
        f"Discovered signal: {payload['discovered_signal']}",
        f"Hypothesized mechanism: {payload['hypothesized_mechanism']}",
        f"Predictive horizon: {payload['predictive_horizon_days']} calendar days to the first eligible market close.",
        f"Historical evidence: {historical['test_samples']} disjoint holdout windows; {historical['test_events']} triggered events; "
        f"mean net price return {historical['mean_net_return']:.2%}, baseline {historical['baseline_mean_net_return']:.2%}; "
        f"p={historical['p_value']:.6g}, lifetime-adjusted threshold={historical['alpha']:.6g}.",
        f"Historical source: {historical['source']}",
        f"Forward predictions: {forward['successes']}-of-{forward['evaluated']} evaluated "
        f"({forward['failures']} failed; {forward['pending']} pending; {forward['registered']} registered).",
        f"Descriptive 95% Wilson hit-rate interval: {low:.1%}–{high:.1%}; assumes independent outcomes.",
        "", f"Prediction times: {timezone} (UTC offsets shown).",
        "", "| Registered | Event | Direction / target | Due | Evaluated / endpoint | Outcome | Net return |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for prediction in forward["predictions"]:
        outcome = "pending" if prediction["success"] is None else "success" if prediction["success"] else "failure"
        ret = f"{prediction['outcome']['net_return']:.2%}" if prediction["outcome"] else "pending"
        event = prediction["event_id"].replace("|", "\\|").replace("\n", " ")
        evaluated = (local(prediction["evaluated_at"]) + " / " + local(prediction["outcome"]["price_at"])) if prediction["outcome"] else "pending"
        lines.append(f"| {local(prediction['registered_at'])} | {event} | {prediction['direction']} / {prediction['target_return']:.2%} net | {local(prediction['due_at'])} | {evaluated} | {outcome} | {ret} |")
    lines += ["", f"Current status: {payload['state']}. {payload['current_status']['opportunity']}.",
              "Confidence and limitations:"]
    for limitation in dict.fromkeys(payload["confidence_and_limitations"] + historical["limitations"]):
        lines.append("- " + limitation)
    lines.append("Any trade is a separate recommendation for you to review and execute manually.")
    return "\n".join(lines)
