# Agent rules

1. No overchecking. Verify only concrete uncertainty or required checks.
2. Always load + apply [compress-output](.agents/skills/compress-output/SKILL.md).

## Project workflow

- Shared policy/method: REQUIREMENTS.md and settings.json. User-specific inputs use individual native SQUAD_* variables only. No profile-file/JSON-blob compatibility route. Credentials only in runtime secrets; never Git. No inferred budget, location, broker, currency, plan or model.
- New setup/storage choice: squad-onboard. Operation: squad-monitor, squad-research, squad-trades. Installation/update/drift: squad-reconcile. Canonical skills live in .agents/skills/squad-*; native plugin copies are generated, never edited separately.
- Run `sh scripts/check.sh`. After skill edits run `python3 scripts/build_plugin.py`; CI rejects copy drift. Runtime: pinned LadybugDB plus stdlib; no paid API/embedding dependencies. Run setup-runtime after installing dependencies.
- Database creation/adoption requires explicit reviewed storage configuration. Preserve existing ledgers, complete prediction records and delivery ambiguity. No brokerage execution. Required deployment: one central Dot cloud owner, LadybugDB knowledge graph + separate SQLite prediction/fill ledger outside every checkout. Delegated workers return batches; never independent live copies. Use docs/STORAGE.md for complete Drive upload/download/restore verification; local snapshots alone are insufficient.
- Native tasks call skills with private environment/runtime bindings. Use deployment plan/check/record for desired state and actual platform receipts. Never invent scheduler APIs, loaded versions, task IDs, runtime proofs or delivery receipts.
- Dirty/untracked revisions cannot be recorded as deployed. Update only the approved Git ref, fast-forward only. Never commit profiles, live data, source caches or account receipts.
