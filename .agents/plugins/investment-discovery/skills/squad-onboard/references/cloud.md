# Cloud thread, container and account access

Use one durable child task, called cloud thread by read tool; its cloud container holds checkout, runtime and private stores. “Database-owning runtime” means that container's investment runtime; “user” means person. Coordinating Dot reads/follows installed skills directly. Send container-dependent operations to saved child task and read result. [Setup](setup.md#source-and-runtime) owns repository URL, release and executable transfer; [configuration](configuration.md) owns settings; [storage](storage.md) owns database identity/recovery.

## Durable child task

1. Inspect exposed thread creation, continuation/read and saved environment configuration tools before choosing controls/arguments. User-observed capability: create durable child task with fresh cloud container, continue it and read results. Reuse suitable existing child task after verifying installation identity and container access.
2. First run without suitable task: select available saved environment configuration and create durable child task with fresh cloud container. Empty connected-environment/cloud-computer list alone does not block creation; saved configuration supplies fresh container. Dot performs creation and continues setup there. Actual missing configuration, denied creation or tool failure: report specific blocker.
3. Give task persistent title **🛡️ Investment Discovery — DO NOT DELETE** through supported title control. Save returned task/thread ID and link privately; retain reference in schedule instructions. Continue same cloud thread for later operations; reuse before creating another task. Verify original stores on return; missing/damaged stores follow [recovery](storage.md#recovery).

Install pinned dependencies from `scripts/requirements.txt` and run shared `scripts/main.py setup-runtime` with chosen Python 3.11+ interpreter. Install timezone data when needed.

Ladybug extension storage: optional `SQUAD_LADYBUG_HOME`, absolute writable directory. Bind same value to setup and later operation processes in child task's cloud container; choose persistent runtime storage. Default: system temporary directory, under `squad-runtime-<user ID>/ladybug`. Temporary storage cleanup requires rerunning `setup-runtime`. Runtime creates private directories and sets Ladybug's `home_directory` before installing/loading extensions.

Set `SQUAD_REPO` to approved checkout in child task's cloud container. Each operation's process needs required interpreter, settings, credentials and database paths. Researchers return structured batches for ingestion by database-owning runtime. Runtime lock serializes commands; live stores stay in that container.

## Runtime settings and credentials

[Official OpenAI controls](https://learn.chatgpt.com/docs/environments/cloud-environments#configure-environment-variables-and-network-secrets): **Settings → Codex Cloud → Environments → selected environment → Edit**; **Manage** beside **Environment variables** or **HTTP secrets**. Personal values: **Settings → Codex Cloud → Personal vault**; request matching keys in selected environment. Saved configuration/vault holds values; requested direct variables reach task processes, HTTP secrets supply destination-restricted placeholders. Existing task's receipt of changes requires verification.

Inspect controls available to this Dot; use only exposed, authorized settings/secret controls. If unavailable, identify exact user action in documented UI. A shell `export` reaches that shell's children only; persistent configuration remains unverified until later continuation of same child task receives required values. Missing credential control leaves backup/init and unattended workflows blocked; continue source/dependency preparation. Keep credentials in secure input/storage controls, outside chat, shell arguments and reports.

Verify later child-task process privately: required variable names present, correct checkout/interpreter, original store identities via `doctor`, authenticated `backup cloud` receipt. Report names/status/errors, keeping values private. HTTP-secret compatibility requires successful OAuth refresh and Drive request; presence alone proves only configuration. Restrict network to required feeds, dependency sources and Google endpoints.

Use [schedule procedure](../../squad-reconcile/references/deployment.md#scheduled-automations) to verify scheduled Dot reaches original databases through saved cloud thread and receives result.

## Google authorization and renewal

1. Plugin supplies refresh-token client only. Initial OAuth application, browser-consent handler and token exchange must come from an authorized application configured for user. Missing application/flow is setup blocker. Enable Drive API in that application's Google Cloud project; configure consent audience, OAuth client and registered callback.
2. Use [Google authorization-code flow](https://developers.google.com/identity/protocols/oauth2/web-server) with `https://www.googleapis.com/auth/drive.file`, `access_type=offline` and validated `state`. User grants consent in browser; application receives code at registered callback and exchanges it for tokens. Callback must be reachable from user's browser. Deliver credentials through secure controls above.
3. Request `SQUAD_GOOGLE_REFRESH_TOKEN`, `SQUAD_GOOGLE_CLIENT_ID`, `SQUAD_GOOGLE_CLIENT_SECRET` for child runtime. Client renews short-lived access tokens in memory. Create/select backup folder through same application's authorization, e.g. Drive Picker; verify actual folder access. OAuth Testing status can limit refresh tokens to seven days for this scope; review publishing/user status. Expired/revoked token requires renewed authorization; preserve pending uploads meanwhile.
4. Put authorized folder ID and reviewed project/archive byte limits in ordinary settings. `backup cloud` checks folder/quota and compares server checksum. Chat's connected Drive app supplies no automatic CLI credential.
5. Retain installation/setup identity, remote file IDs and recovery instructions using [recovery storage requirement](storage.md#full-cloud-backup). Reauthorize credentials separately after loss.

Account storage shared with other Google services; inspect actual available capacity. Respect approved service budget. [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [offline OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
