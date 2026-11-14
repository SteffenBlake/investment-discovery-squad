# Storage, ownership and recovery

## One owner, two stores

| Component | Contents |
| --- | --- |
| Ladybug, storage.knowledge_path | Research entities, sources, claims, relationships and search index |
| SQLite, storage.database_path | Specs, frozen test plans, historical tests, predictions/results, corrections, delivery receipts, portfolios, fills and trial reviews |
| knowledge-sources/ and cache/ beside stores | Original source text and downloaded feed responses |
| Private Google Drive folder | Latest three successful complete backups |

Keep distinct database files in one private directory outside Git checkouts. Separate backup staging from live files. [Cloud](cloud.md) owns runtime bindings. Owner lock serializes commands. New directories use 0700; ledger/source/JSON files use 0600. Review access on existing directories. Backups include private financial records; host and Drive access controls protect them.

## Provision or adopt

`storage-plan` shows paths, Drive limits, interval, three-copy retention and owner. Set `storage.decision_accepted=true` after user accepts arrangement.

Before creating empty databases, `init` lists this installation's remote backups. Existing backup blocks creation and requires recovery. Failed authorization/listing also stops creation. Partial local installation requires recovery. Repeated init on both existing databases retains identity.

Recognized unowned legacy ledger: `adopt --confirm-currency CODE --confirm-starting-cash VALUE` verifies stored economics, takes checked local SQLite snapshot and binds ownership. Migrate missing research records deliberately before ordinary operation. Unknown schema or conflicting economics requires explicit migration.

## Full cloud backup

`backup cloud` / `backup-due`:

1. Take online SQLite snapshot, export Ladybug and copy sources/cache. Manifest records identity, versions, evidence position, file sizes and SHA-256 checksums.
2. Upload complete ZIP after folder/project/archive/account capacity checks. Budget must accommodate new upload alongside three retained copies.
3. Compare Drive-reported file size and MD5 with local archive. Commit checksum-verified receipt after match.
4. Keep current successful upload and two newest earlier successful backups. Delete older successful copies only after new checksum passes. Failed upload/checksum leaves earlier backups intact.
5. Remove completed local upload ZIP and pending record. Older ambiguous upload finishes before creating snapshot for newer evidence.

Changed evidence, source artifacts, destination or elapsed interval triggers backup. Routine run bookkeeping preserves current receipt. Ambiguous uploads retain `pending-upload.json` and ZIP for retry.

`backup verify --file-id ID --expected-identity IDENTITY` explicitly downloads and tests full recovery when requested. Routine uploads use server checksum. `backup snapshot --output PATH` creates local diagnostic archive. `export` writes numerical inspection data.

Retain original identity and remote file ID privately outside owner. Archives retain non-secret configuration revisions; rebuild settings from them and reauthorize Google separately.

## Recovery

Pause jobs using [task procedure](../../squad-reconcile/references/deployment.md#native-tasks). Preserve surviving files. Reinstall originating pinned runtime; bind reviewed settings and original economics. Recover into new empty data directory:

```sh
python .agents/skills/squad-onboard/scripts/main.py backup restore --file-id ACTUAL_ID --expected-identity ORIGINAL_ID
python .agents/skills/squad-onboard/scripts/main.py doctor
```

Restore downloads ZIP, validates checksums/schema/ownership, reconstructs graph and verifies contents in temporary storage. Copy under interruption marker; commit `restore_completed` before removing marker. Interrupted target stays blocked; retry into another empty directory.

Inspect saved jobs and destination message history, including sends after backup. [Delivery](../../squad-monitor/references/operations.md#claim-deliver-acknowledge) owns ack/release of uncertain messages. Rebind owner, reconcile jobs and create current backup before resuming approved trial.
