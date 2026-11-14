# Current portfolio and next actions

Each advice request starts from user's current holdings and available cash. Normalize pasted information into temporary private JSON:

```text
{cash: decimal amount, currency: three-letter code,
 holdings: {SYMBOL: quantity}, as_of: offset timestamp}
```

Supplied cash means available money. Use it directly for affordability. User restrictions and broker terms guide advice through [configuration](../../squad-onboard/references/configuration.md).

Apply squad-monitor's due evaluation/delivery work; review corrections. Retrieve evidence:

```sh
python .agents/skills/squad-onboard/scripts/main.py knowledge context --portfolio /private/current.json --query 'current risks' --limit 15 --hops 2
```

Command reads supplied account for this request and returns research entities, directed relationships, dated claims, original sources, contradictions and prediction results. [Research retrieval](../../squad-research/references/knowledge.md) owns evidence fields and search bounds.

Explain what to do next: buy, hold, sell or keep cash, with reasons and uncertainty. For fresh qualified bullish forecast:

```sh
python .agents/skills/squad-onboard/scripts/main.py idea --prediction ACTUAL_ID --portfolio /private/current.json
```

Python calculates affordable lot quantity from supplied cash, price limit and configured entry fees. Explain price, quantity, total cost, evidence, horizon and review conditions. Multiple full-budget suggestions represent alternatives. Joint recommendations must fit supplied cash together. User executes orders; next request supplies current account again. Remove temporary input file after request.
