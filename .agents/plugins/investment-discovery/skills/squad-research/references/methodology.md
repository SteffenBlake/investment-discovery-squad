# One-shot historical testing

Explore existing history first. Earlier development period teaches hypothesis; untouched later period tests it. Example: develop using 2010–2020, reserve unseen 2021+ outcomes. Retain original information-release dates and revision evidence so simulated predictions use information available then.

## Freeze before opening test outcomes

1. Register immutable signal spec: mechanism, investment, target, duration, `family_id`, canonical `input_id`, structured `feature_formula` and limitations. Input ID identifies underlying measurement, such as `wikimedia:pageviews`; formula's `operation` identifies calculation, such as `ratio_to_mean`. Parameters belong in same object.
2. Gather development rows and test-window dates. Development rows require `available_at < entry_at < exit_at <= now`, unique events, chronological disjoint windows and saved duration. Freeze every test window's event ID, entry and exit before viewing its outcomes. First test entry follows development period.
3. Run `prepare-test` with development dataset, exact test windows and `holdout_unseen=true`. Agent must establish this declaration honestly from research history. Plan saves complete development data, rule, costs, sample count, exclusions, test method, probability threshold and lifetime attempt number. Plan immutable; abandoned plans still consume attempt number.
4. Development data fixes upper 80th-percentile feature threshold and up/down direction from triggered-minus-ordinary return. Shared minimums: 100 development rows, 100 test rows, 20 triggered test events. Circular-shift test's minimum attainable probability is 1/test-row-count. Gather sufficient untouched history before preparing plan.
5. Run `backtest` once using exactly frozen windows. Test signed price returns after configured costs. Triggered average must exceed zero and ordinary same-direction average across all test windows. One-sided circular-shift probability must satisfy `p <= family_alpha / (k*(k+1))`; k counts every lifetime planned attempt across all families, including failed and abandoned attempts. Existing pre-plan trials also retain their count.
6. Passed test means QUALIFIED: evidence worth further investigation. Emit complete qualification alert through [delivery](../../squad-monitor/references/operations.md#claim-deliver-acknowledge). Failed test permanently rejects hypothesis. Record submitted results and failures; move to another idea.

**Ban p-fishing, p-hacking, cherry-picking, inspecting test results early, selective exclusions, changing frozen rules and retrying failed hypotheses.** Development outcomes and test outcomes stay separate. Renaming an idea, changing dates, threshold, duration, investment, or lookback alone grants no retry.

## Related new premise

Related candidate retains original `family_id`. New attempt requires both different canonical measured `input_id` and different formula `operation`. Numerical parameter edits alone preserve operation. Compare against every previously planned candidate in family. Measurement IDs and operation names retain canonical meanings; changing labels cannot manufacture novelty. Code checks saved IDs/operations; researching agent establishes truthful source identity.

Related retry uses untouched test windows later than family's earlier test periods. Every investment's consumed test price windows remain unavailable for later tests. Shared lifetime correction spans all families.

Example: Wikipedia attention ratio failed. Bigger spike or another lookback stays rejected. Shipping-delay change relative to inventory may become new premise using shipping measurement and different operation; same economic theme retains family ID.

## Interpretation

Circular shifts assume approximate stationarity and exchangeable alignment under null. Separate windows reduce overlap; residual dependence and selected research universe limit conclusions. Original-release evidence establishes timing. Price returns omit dividends and actual fill effects. Wilson interval describes independent Bernoulli outcomes. Agent must report these limits alongside evidence.

After historical qualification, [live trial](../../squad-monitor/references/validation.md#live-trial) measures future usefulness for at most 30 days before performance review.
