# Delivery and incidents

## Claim, deliver, acknowledge

| Outbox status | Action |
| --- | --- |
| pending | Claim and deliver complete returned message |
| claimed | Inspect destination history before resolving uncertain send |
| delivered | Keep recorded message ID/link |
| cancelled | Review corrected qualification support |

`claim --alert ID` returns token/message or null. Qualification means historical evidence worth further investigation. Send complete record, including failed, pending and invalidated future predictions, historical result, dates, mechanism, duration and limitations. Attach full record when message size requires.

After send, `ack --alert ID --token TOKEN --receipt MESSAGE_ID_OR_LINK`. Confirmed rejection before send permits `release --alert ID --token TOKEN --confirmed-not-sent EVIDENCE`. Ambiguous send stays claimed until destination history establishes outcome. Claims remain saved across restarts.

`run` returns queued delivery before slower work and releases runtime lock. If `remaining_work=true`, handle delivery then invoke same run/research command with `--continue-work`. Inspect alerts afterward. Feed failure preserves other alerts. Late invalidation cancels unsent qualification; claimed/delivered messages require history review and authorized correction.

## Incident actions

- Missing store/identity mismatch: preserve files; use [recovery](../../squad-onboard/references/storage.md#recovery).
- Changed source/configuration/automation: use [deployment](../../squad-reconcile/references/deployment.md).
- Feed failure: retain redacted error; report persistent outage.
- Stale quote: obtain current quote before registration/entry.
- Missing actual session close or late endpoint: retain pending prediction and blocker.
- Missing historical release evidence: find dated archive/original publication under [historical method](../../squad-research/references/methodology.md).
- Split/mechanism breakdown: record evidence-based invalidation/degradation; retain original results.
- Trial expired: present [performance review](validation.md#live-trial) and pause research/monitor automations through deployment.
- Fill discrepancy/exit review: use [portfolio](../../squad-trades/references/portfolio.md).

After delivery/remaining work, apply [backup](../../squad-onboard/references/storage.md#full-cloud-backup). Routine unchanged runs stay quiet. Report persistent runtime, missed-run and delivery failures. User stop/pause changes go through [scheduled automations](../../squad-reconcile/references/deployment.md#scheduled-automations).
