# Setup instructions for Dot

Follow this file from the installed squad-onboard skill. The user has already registered the plugin and asked you to set it up. Handle the computer work yourself; guide the user only through their personal decisions, account access and consent. A blank cloud computer is a supported starting point.

The installed skill bundles this file as `references/SETUP.md`. That copy lets you begin before a project checkout or Python package exists. After obtaining the checkout, use its matching current guide and linked project documents.

## 1. Obtain the project on your cloud computer

Use the Git repository and approved ref from the actual registered investment-discovery marketplace. Inspect native marketplace metadata/readback to resolve them; registration may be on a different computer. Do not assume its local cache is mounted on your cloud computer. Preserve a user's registered fork/ref.

On your own persistent cloud computer, reuse an existing clean matching checkout or clone that registered repository at its approved ref. Use already-authorized Git access; if a private repository needs access, guide the user through the supported account authorization. Never request credentials pasted into chat. Do not overwrite another checkout or discard edits.

The Git source supplies Python code, settings, workflows and docs. A plugin install supplies instructions; it does not itself run the engine or create storage. Read the obtained checkout's AGENTS.md and these guides:

- [ONBOARDING.md](docs/ONBOARDING.md): every required personal variable and activation step.
- [CLOUD.md](docs/CLOUD.md): actual owner environment, secrets and Google authorization.
- [STORAGE.md](docs/STORAGE.md): privacy, ownership, adoption, full backups and recovery.
- [KNOWLEDGE.md](docs/KNOWLEDGE.md): research evidence format and portfolio retrieval.

One owner holds the live data: your persistent Dot cloud computer. Delegated researchers return structured batches to that owner; separate Codex Cloud workers do not share its evolving filesystem. No personal computer or separate server is required.

## 2. Prepare the runtime yourself

From the cloud checkout, create and use its Python virtual environment:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m squad setup-runtime
.venv/bin/python -m squad onboarding
SQUAD_PYTHON="$PWD/.venv/bin/python" sh scripts/check.sh
```

Python 3.11+ and timezone data are required. If the base image lacks prerequisites, install them through supported owner-runtime controls; do not delegate terminal work to the user. setup-runtime installs/loads the pinned LadybugDB full-text extension using a temporary probe, never production state. The remaining CLI examples below use that same virtualenv interpreter.

Bind SQUAD_REPO to the actual checkout and select the actual interpreter for saved execution. Prompts describing variables do not inject them. Use the owner's real native settings/secret controls; a delegated environment's vault does not automatically populate Dot's own computer.

## 3. Collect and explain personal settings

Use existing user context before asking. Collect the required budget/currency, broker/investing mechanism, jurisdiction, instruments/lots/ticks/sessions/costs, model/resource preferences, notification destination and schedules. Confirm actual supported model selection; null means host-selected model/effort. Never infer personal values from examples. A trade ceiling is not a target.

Explain both stores before creating them:

- LadybugDB keeps searchable research: entities, claims, sources, relationships, dates, confidence and contradictory evidence.
- SQLite keeps numerical and bookkeeping history: full tests, every prediction/result/loss/pending outcome, alert receipts and actual human-reported fills.

Choose concrete private paths outside every Git checkout: distinct graph/ledger files in one data directory, and separate backup staging. Review access/privacy, original-source retention, Drive capacity/archive limits, backup interval/retention and acceptable loss window. There is no built-in archive encryption or high-availability service. Keep credentials out of ordinary configuration and all evidence.

Bind every documented individual SQUAD_* personal variable through actual native settings, including explicit null/[] values where specified. No profile-file or JSON-blob configuration route exists. Leave storage.decision_accepted false until the user reviews the concrete paths/access/recovery arrangement.

## 4. Guide Google Drive authorization

Follow CLOUD.md's one-time Google OAuth setup. Use the narrow drive.file scope and a private folder created/selected through that authorized app flow. A connected chat app is not automatically a Python access token. Guide the user through account consent while handling supported setup work yourself.

Bind SQUAD_GOOGLE_REFRESH_TOKEN, SQUAD_GOOGLE_CLIENT_ID and SQUAD_GOOGLE_CLIENT_SECRET only through native runtime secrets. Ordinary configuration contains only the authorized folder ID and explicit storage limits. Existing free Google storage is shared and limited; never purchase services without authorization. Missing personal values or authorization remain unresolved rather than invented.

## 5. Initialize or preserve the existing installation

Run storage-plan to show the concrete proposal without creating state. After the user's review, set storage.decision_accepted true through native settings and run init, then doctor. Repeating init must retain the same setup identity.

For existing evidence, follow STORAGE.md: preserve original ownership/economics and checked backups; recognized unowned ledgers require explicit adoption confirmation. Never reset, relabel or create replacement live databases because files unexpectedly disappeared. Transfer reviewed legacy personal values into native variables without loading old profile files.

Run backup cloud. Require a real upload, download, checksum check and full restore into staging before accepting durability. A local snapshot does not qualify. Initial research --preflight is limited to a ledger with no submitted forecasts; back up again after collecting evidence.

## 6. Activate and verify native tasks

Use squad-reconcile and [GITOPS.md](docs/GITOPS.md). Keep source clean and committed, preserve the approved ref and fast-forward-only updates, and verify actual loaded skill contents match the checkout. Refresh an installed plugin through supported host controls when needed.

Apply real native research, monitoring and reconciliation tasks. Reuse existing task IDs and preserve unrelated tasks. Unsupported account/runtime capabilities are concrete blockers, not permission to invent matching task state or scheduler APIs.

Independently execute a saved worker that reopens both original database paths on the configured owner and returns matching identities. Send a labelled setup notification to the selected destination and retain its actual receipt. Never use a real qualification alert as a setup test.

Record deployment only from fresh actual native task readback, matching loaded skills, the independent runtime receipt, the restore-tested cloud backup and real notification proof. A second reconciliation must require no changes. CLI tests, accepted worker runs and local files alone do not prove external delivery or account activation.

Report what was actually installed, where private state lives, confirmed backup/task/message results and any specific unresolved setup steps. The agent recommends investments; the human executes every trade and reports actual fills. No brokerage credentials or order-submission capability belongs in this installation.
