# Knowledge, persistence and recovery

## Two stores, one owner

| Component | Concrete contents |
| --- | --- |
| LadybugDB 0.22.3, `storage.knowledge_path` | Entities, source originals/provenance, claims, relationships, contradictions, validity dates, immutable ingestion batches and BM25 full-text index |
| SQLite schema 1, `storage.database_path` | Formal specs, full historical inputs/results, every forecast/outcome/loss, numerical qualification, notification outbox/receipts, human fills and non-secret configuration/deployment revisions |
| `knowledge-sources/`, `cache/` beside the databases | Content-addressed research originals and existing adapter response archives |
| Private Google Drive folder | Versioned complete recovery ZIPs, independent of Dot's working files |

SQLite is retained for transactional numerical/accounting history; it is not the research knowledge graph. LadybugDB supplies native property-graph traversal, Cypher and indexed text search. Retrieval uses BM25 plus graph traversal, with no embedding service. [LadybugDB](https://github.com/LadybugDB/ladybug), [full-text search](https://docs.ladybugdb.com/extensions/full-text-search/).

Required owner: Dot's persistent cloud computer. Graph and ledger are distinct files in one private data directory outside **every** Git checkout/worktree; backup staging is a separate directory outside live data. Dot's snapshots are not an independently verified backup promise, and deleting a Dot can delete its data/snapshots. [Official security/retention](https://learn.chatgpt.com/docs/enterprise/dots-security).

The central CLI serializes access. Native databases are not multi-host network services. New files are mode 0600; new data directories mode 0700. Existing directory permissions must be reviewed. There is no application-level database/archive encryption; OS/cloud access controls and private Drive permissions define access. Do not make the folder public. If stronger encryption is required, choose/review a supported implementation before init.

## Reviewed setup

`storage-plan` renders actual graph/ledger paths, owner, Drive folder, byte limits, backup interval and retention without creating anything. `storage.decision_accepted` stays false until the user accepts that concrete arrangement. `init` then binds both stores to one random setup_identity and profile_id. Repeating init preserves that identity. Missing state during ordinary operation is an error, never implicit creation.

Move reviewed personal values from earlier configuration into the documented individual native variables; runtime evidence files are preserved. Old profile-file/JSON-blob settings are rejected and never loaded. Existing owned SQLite ledgers retain all original evidence/economics. After reviewing configuration and preserving a checked old backup, `init` can add a new empty graph beside an existing owned ledger; it does not automatically turn old numeric records into graph claims. A knowledge migration must retain provenance and use explicit ingest batches.

Recognized unowned legacy production ledgers require `adopt --confirm-currency CODE --confirm-starting-cash VALUE`; the command checks compatibility and creates a verified pre-adoption SQLite backup before metadata changes. Then initialize the matching graph explicitly and make a complete cloud backup. Unknown schemas, conflicting owners or economics fail closed. Never relabel another installation or restore synthetic test data as production.

## Complete backup

```sh
python -m squad backup cloud
python -m squad backup list
python -m squad backup verify --file-id ACTUAL_FILE_ID --expected-identity ORIGINAL_SETUP_ID
```

`backup cloud` / `backup-due` run under the owner lock:

1. SQLite online backup captures committed WAL contents and checks integrity.
2. Ladybug `EXPORT DATABASE` emits portable schema, data and full-text index definitions. Full source/cache files are copied. The manifest records application/library/schema versions, ownership, evidence sequence, graph revision/counts and every file's size/SHA-256.
3. A new private ZIP is uploaded through resumable Drive upload after folder, archive, project and account quota checks. No previous version is overwritten.
4. The actual remote bytes are downloaded. Checksums, ownership, schema and frozen economics are checked; the graph is imported into a fresh staging database and its records, graph links, capture times and search verified. Only then is `cloud_backup_verified` recorded.

The archive contains non-secret configuration revisions in the ledger. It excludes credentials, Git source and runtime plugin caches; no external profile file exists in this workflow. Reconstruct/review configuration from those revisions or your private settings manager; reauthorize credentials separately. Reinstall code/runtime from the recorded Git/library versions.

A pending-upload receipt survives upload/response failures. Retry reconciles the same checksum/version instead of blindly adding duplicates. Completing an older pending archive triggers a fresh backup if evidence changed. Failed verification never counts as success. The last verified receipt does not prove future Drive retention; periodically run `backup verify` against actual remote versions.

`backup-due` backs up when evidence changes, destination changes or the interval expires. Scheduling limits actual recovery-point frequency; archive upload is not synchronous with every write. Skills handle alerts first, then backup. Set cadence for acceptable data loss; no zero-loss guarantee. No auto-pruning: after expiry, manually review/delete old local/Drive archives only after confirming a current restore-tested version. Full evidence is never pruned. Quota exhaustion stops new backups and is reported; no paid upgrade occurs.

The diagnostic command `backup snapshot --output NEW_ABSOLUTE_PATH` produces a complete offline archive for inspection. Production always requires `backup cloud`; the old SQLite-only CLI compatibility route is removed. Internal pre-adoption SQLite snapshots preserve old evidence before changes. JSON `export` is an inspection tool, not full recovery authority.

## Restore after owner loss

Pause relevant native tasks and preserve any surviving/partial state. Reinstall the pinned runtime and bind reviewed configuration/secrets on a new owner; preserve profile ID and frozen economic/method values. Get the original setup identity/file ID from private Drive metadata/receipts. Point graph and ledger at a **new empty private directory**, with staging elsewhere:

```sh
python -m squad backup restore --file-id ACTUAL_FILE_ID --expected-identity ORIGINAL_SETUP_ID
python -m squad doctor
```

Restore downloads and fully validates in staging before installing. Existing targets are never overwritten. An interrupted installation leaves a marker blocking ordinary commands; preserve that partial target and retry into another empty directory. Do not remove the marker to pretend recovery completed.

Successful recovery retains the original identity, full forecast history and ambiguous delivery claims, then invalidates deployment. Reconcile actual messages sent after the backup before ack/release; do not blindly resend. Rebind the actual owner/runtime, produce a new verified cloud archive and use squad-reconcile to obtain new task/probe/delivery receipts before resuming financial work. [Portable graph export/import](https://docs.ladybugdb.com/migrate/), [Drive uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads).
