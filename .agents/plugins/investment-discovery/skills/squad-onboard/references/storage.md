# Storage, backup and recovery

[Onboarding checklist](../SKILL.md) owns proposal/consent. Runtime and original stores live on **This Dot’s cloud computer**.

| Location | Contents |
| --- | --- |
| Ladybug `storage.knowledge_path` | Research entities, sources, claims, relationships/search |
| SQLite `storage.database_path` | Frozen plans/tests, forecasts/results, events/receipts |
| `knowledge-sources/`, `cache/` beside stores | Original source text/feed responses |
| `storage.backup_directory` | Private pending ZIP/connector handoff files, separate from live files |
| Connected private Drive folder | One complete backup file, updated in place; Drive versions hold earlier contents |

Distinct live database files share private directory outside checkout. New directories 0700; ledger/source/JSON/ZIP files 0600. Review existing access. Archives contain private research records. Computer state may be lost; accepted upload confirms Drive acceptance. Separate deliberate restore validates recovery contents.

## Inventory and initialization

Dot verifies connection/folder through [connector](cloud.md#connected-drive), then lists target folder. Combine listing with folder-filtered paginated search; follow every returned page token. Deduplicate IDs; inspect metadata for missing sizes. Include known pending/accepted IDs. Search miss alone cannot establish absence. Saturated/partial listing or missing pages leaves inventory incomplete; resolve through supported tools before initialization/upload.

Save private normalized JSON from actual tool results:

```json
{"folder_id":"ACTUAL_FOLDER_ID","complete":true,"files":[{"id":"ACTUAL_FILE_ID","name":"ACTUAL_NAME","size":"123"}]}
```

`complete=true` requires successful complete collection. Dedicated empty folder has `files:[]`. Folder ID must match configuration. `init --inventory FILE` refuses existing `.backup.zip` archives before creating empty stores. Partial local installation requires recovery; both existing matching stores retain original identity. Failed/missing/incomplete inventory blocks creation.

`storage-plan` reports files, folder, limits and consent. Recognized legacy ledger adoption uses `adopt --confirm-currency CODE`: checked local snapshot and verified original economics before identity binding. Conflicting schema/economics requires reviewed migration.

## Connected backup procedure

1. Run `backup-due`. `action=inventory`: collect inventory above; run `backup cloud --inventory FILE`. Python snapshots SQLite, exports Ladybug and includes sources/cache. Manifest holds original installation identity, versions, evidence positions, local hashes and sizes. Pending operation and ZIP persist before upload.
2. Returned `tool` and `arguments` specify connector call: first upload uses `upload_file`; later backups use `update_file` with same `fileId`. Run `backup started` immediately before connector call. Preserve actual returned receipt. Archive name contains identity/hash so interrupted update can be recognized; file ID stays fixed.
3. Save private receipt JSON: `{"file_id":"ACTUAL_ID","folder_id":"ACTUAL_FOLDER","name":"EXACT_PENDING_NAME","size":123,"receipt":{...actual returned receipt/metadata...}}`. Size optional if omitted by tool. Run `backup accept --file RECEIPT_JSON`. Python records acceptance and removes completed local ZIP/pending marker. Same file ID required for update acceptance.
4. Remove completed handoff JSON. Existing separate backup copies: keep selected current file ID; remove superseded copies after accepted update, using applicable permanent-deletion authorization.

Drive maintains earlier content versions under normal expiry rules, accepted by user. Folder budget counts current file contents after replacement plus other observed files; per-archive limit applies. Drive accounts for revision storage through its own quota. Missing size requires metadata. Report connector storage errors directly.

## Interrupted upload or update

`action=inspect_upload`: outcome uncertain. Inspect folder listing, search pages and target metadata for exact pending name/size. Matching file recovers acceptance. `backup retry --file EVIDENCE_JSON` requires observed failure before remote write: `{"failed_before_creation":true,"reason":"OBSERVED_FAILURE"}`. Field means operation failed before create/update took effect. Preserve local ZIP/pending state until resolved. Completing older pending operation may leave newer evidence due; repeat until current.

Keep original installation identity, remote file ID/name and receipt in private recovery records accessible after computer loss. Archives retain configuration history; connected account access must remain available independently.

## Recovery

Pause affected [automations](../../squad-reconcile/references/deployment.md#scheduled-automations); preserve surviving files. Reattach/recover Dot computer; reinstall archive's pinned runtime, reviewed settings and original economics. Read remote metadata, then deliberately fetch chosen ZIP with connected raw-file fetch. Materialize returned authenticated file reference on computer at private path. Recover into new empty data directory:

```sh
python .agents/skills/squad-onboard/scripts/main.py backup verify --file ACTUAL_DOWNLOADED_ZIP --expected-identity ORIGINAL_ID
python .agents/skills/squad-onboard/scripts/main.py backup restore --file ACTUAL_DOWNLOADED_ZIP --file-id ACTUAL_REMOTE_ID --expected-identity ORIGINAL_ID
python .agents/skills/squad-onboard/scripts/main.py doctor
```

Restoration records downloaded file ID as backup target for subsequent updates. Verification checks archive paths/hashes, schema, original identity/research settings and reconstructed graph. Restore copies under interruption marker and commits `restore_completed` before marker removal. Interrupted target stays blocked; retry into another empty directory. Local `backup snapshot --output PATH` supports diagnostics.

Inspect automations and message history, including sends after backup. Resolve uncertain investment-alert sends through [alert delivery](../../squad-monitor/references/operations.md#claim-deliver-acknowledge). Verify original store identity on Dot computer, reconcile automations and record new accepted backup before resuming scheduled work.
