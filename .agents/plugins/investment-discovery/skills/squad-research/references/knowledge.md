# Research batch schema and retrieval

## Online content → structured evidence

The researching LLM reads source pages, identifies entities and dated claims, and writes JSON. The database-owning runtime validates references/types/checksums, stores originals and creates graph links. Delegated researchers return batches to that runtime rather than keeping local databases.

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

Replace placeholders with sourced evidence. Retain originals; distinguish observation from speculation. `synthetic=true` batches are rejected.

Fields:

- Stable unique IDs, immutable content. Exact batch retries are idempotent; changed content under an existing ID fails atomically. Add new IDs for revisions/corrections, linking contradictory claims instead of overwriting them.
- Entity kinds: asset, company, sector, event, region, indicator, commodity, other. Symbols match actual holdings/instruments when applicable.
- Source: HTTP(S) URL without embedded credentials, title and original extracted text (up to five million characters). Optional content_sha256 must match. published_at is the publisher's claim; null means unknown. Database-owning runtime assigns first_captured_at at ingestion. Neither field alone proves historical first availability. Keep original archive/revision timing evidence before numerical validation.
- Claim status: hypothesis, observed, supported, disputed, invalidated. Confidence is a researcher estimate in [0,1], **not** measured predictive accuracy. Each claim references at least one entity and source. Optional validity dates retain expired evidence for assessment.
- Relationship: from/to entity IDs, kind, and evidence claim_id. Referenced existing/incoming IDs must exist. Claims may reference contradicts IDs in either direction; retrieval includes counterclaims.
- At most 500 records per category/batch, 100 references per claim. No credentials in JSON. Keep private batch files outside Git; portfolio input temporary per request.

```sh
python .agents/skills/squad-onboard/scripts/main.py knowledge ingest --file /private/research/batch.json
python .agents/skills/squad-onboard/scripts/main.py knowledge search --query 'port congestion' --limit 10
python .agents/skills/squad-onboard/scripts/main.py knowledge show --type Source --id source:actual-id
python .agents/skills/squad-onboard/scripts/main.py backup-due
```

Search uses indexed BM25 claim text. `knowledge context --symbols SYMBOL --hops 2` follows bounded relationships and includes edge IDs, actual from/to direction, kind, supporting claims, sources and contradictions. Inspect truncation/missing symbols; retrieve exact IDs or broaden bounds when needed. Context uses graph revision rather than exporting history. [Numerical inputs](../../squad-onboard/references/commands.md#research); [portfolio procedure](../../squad-trades/references/portfolio.md).
