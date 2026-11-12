# Research handoff and fast portfolio retrieval

## Online content → structured evidence

The researching LLM reads source pages, identifies entities and dated claims, and writes JSON. Python does not infer financial meaning from arbitrary HTML. The central owner validates references/types/checksums, stores originals and creates graph links. Delegated researchers return batches to that owner rather than keeping local databases.

Batch schema 1, illustrative shape only (replace every placeholder with actual researched evidence):

```json
{
  "schema_version": 1,
  "id": "batch:unique-source-review",
  "entities": [
    {"id": "asset:SYMBOL", "kind": "asset", "label": "Actual allowed asset", "symbol": "SYMBOL"},
    {"id": "indicator:congestion", "kind": "indicator", "label": "Port congestion"}
  ],
  "sources": [
    {"id": "source:original-version", "url": "https://publisher.example/report", "title": "Actual report", "content": "Original extracted source text", "published_at": null}
  ],
  "claims": [
    {"id": "claim:dated-observation", "text": "Actual sourced observation and its limitations", "status": "hypothesis", "confidence": 0.5, "entity_ids": ["asset:SYMBOL", "indicator:congestion"], "source_ids": ["source:original-version"], "contradicts": [], "valid_from": null, "valid_to": null}
  ],
  "relationships": [
    {"id": "relation:exposure", "from": "indicator:congestion", "to": "asset:SYMBOL", "kind": "MAY_AFFECT", "claim_id": "claim:dated-observation"}
  ]
}
```

This example is not real investment evidence and must never be ingested unchanged. Automated synthetic fixtures are rejected when labelled synthetic=true. No validator can prove arbitrary prose is truthful; the researcher must retain actual sources and distinguish observation from speculation.

Fields:

- Stable unique IDs, immutable content. Exact batch retries are idempotent; changed content under an existing ID fails atomically. Add new IDs for revisions/corrections, linking contradictory claims instead of overwriting them.
- Entity kinds: asset, company, sector, event, region, indicator, commodity, other. Symbols match actual holdings/instruments when applicable.
- Source: HTTP(S) URL without embedded credentials, title and original extracted text (up to five million characters). Optional content_sha256 must match. published_at is the publisher's claim; null means unknown. The owner assigns first_captured_at at ingestion. Neither field alone proves historical first availability. Keep original archive/revision timing evidence before numerical validation.
- Claim status: hypothesis, observed, supported, disputed, invalidated. Confidence is a researcher estimate in [0,1], **not** measured predictive accuracy. Each claim references at least one entity and source. Optional validity dates retain expired evidence for assessment.
- Relationship: from/to entity IDs, kind, and evidence claim_id. Referenced existing/incoming IDs must exist. Claims may reference contradicts IDs in either direction; retrieval includes counterclaims.
- At most 500 records per category/batch, 100 references per claim. No credentials in JSON. Keep private batch/portfolio files outside Git.

```sh
python -m squad knowledge ingest --file /private/research/batch.json
python -m squad knowledge search --query 'port congestion' --limit 10
python -m squad knowledge show --type Source --id source:actual-id
python -m squad backup-due
```

## Portfolio question → compact decision context

The human asks “what should we do today?” and supplies actual cash, currency, holdings, timestamp and pending orders. The agent normalizes that snapshot into a private JSON file:

```text
{cash: decimal amount, currency: three-letter code,
 holdings: {SYMBOL: quantity}, as_of: offset timestamp,
 pending_orders: user-supplied details if any}
```

```sh
python -m squad knowledge context --portfolio /private/today.json --query 'current risks' --limit 15 --hops 2
```

One command returns:

- Supplied actual portfolio alongside separately recorded ledger holdings/cash; discrepancies explicitly flagged, with no invented fills or balance changes.
- Matching asset entities, one-to-three-hop relationships and bounded dated claims with original URLs, source excerpts, checksums, validity, confidence and contradictions.
- Optional separate BM25 text matches, so a query is not silently dropped when graph results fill the limit.
- Relevant numerical signal states, historical test summaries, all-outcome live counts/Wilson uncertainty, bounded active forecast references and commands for complete records.
- Missing symbols and truncation flags. Missing knowledge is a gap, not evidence of safety.

BM25 searches indexed claim text; graph traversal follows actual evidence-backed links. This is not semantic embedding search and does not require paid API calls. Context uses a stored revision, not a full database export/hash or a dump of all history. Results are bounded; broaden keywords/hops or retrieve exact source/claim IDs when needed. No fixed latency is promised without a real dataset/runtime benchmark.

The trading LLM weighs provenance, age, contradictions, costs and current portfolio, then explains buy/hold/sell/avoid recommendations. It may request fresh public data for material gaps. New entries remain subject to numerical qualification and portfolio limits; raw graph confidence never bypasses them. Reconcile real fills before cash-sensitive `idea` sizing. Unqualified ideas remain research; the human executes all trades.

For a testable claim, register an immutable spec through `discover`, extract reproducible timestamped numerical rows, and run `backtest`. Register genuinely new live forecasts before movement. Graph research and numerical validation complement each other; all failed tests and losses persist. [CLI formats](CLI.md), [methodology](METHODOLOGY.md).
