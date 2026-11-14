# Actual portfolio and research context

The user supplies current available uninvested cash, currency, holdings, timestamp and pending orders. Normalize that information into a private JSON file:

```text
{cash: decimal amount, currency: three-letter code,
 holdings: {SYMBOL: quantity}, as_of: offset timestamp,
 pending_orders: user-supplied details if any}
```

Perform squad-monitor's due evaluation and delivery work before assessing advice. Review research corrections, then retrieve context:

```sh
python .agents/skills/squad-onboard/scripts/main.py knowledge context --portfolio /private/today.json --query 'current risks' --limit 15 --hops 2
```

The command saves the supplied portfolio snapshot and returns matching research entities, directed relationships, dated claims, original source URLs, contradictions and numerical prediction results. Missing symbols and truncation flags identify coverage gaps. [Research retrieval](../../squad-research/references/knowledge.md) defines evidence fields and search bounds.

Supplied cash means money available to invest; user has already accounted for pending-order commitments. Assess holdings and cash together. Holding cash remains valid when evidence supports it. Actual supplied cash and holdings control sizing. New snapshots capture account changes such as transfers, dividends and stock splits. Reported fills retain execution history. Original initialization settings remain available for saved-history ownership and recovery.

For a fresh qualified bullish prediction:

```sh
python .agents/skills/squad-onboard/scripts/main.py idea --prediction ACTUAL_ID --portfolio /private/today.json
```

Python chooses an affordable lot quantity using actual supplied cash, configured fixed/per-unit entry fees and outstanding purchase suggestions. Explain quantity, price limit, estimated fee, total required cash, evidence, horizon and review conditions. Confirm broker quotes, fee estimate, settled cash, pending orders and restrictions before entry. Identical retries with the same portfolio return the saved suggestion; changed portfolios require reviewing the existing suggestion.

## Fills and exit follow-up

Record actual reported executions using [trade commands](../../squad-onboard/references/commands.md#trades). Partial fills use distinct IDs; exact retries preserve one record. Obtain an updated actual portfolio snapshot for subsequent sizing.

For an authorized exit reminder, discover actual saved-task and message-history tools. Reuse an existing matching reminder; inspect saved state after uncertain creation before retrying. Read saved due time, timezone and destination back; retain actual returned task/message IDs. Review at forecast horizon or invalidation and record actual reported exits. Report unavailable reminder capabilities and give the review time. The human executes trades.
