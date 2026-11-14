# Cloud thread, container and account access

Use one durable child task, called cloud thread by read tool; its cloud container owns checkout, runtime and private stores. Coordinating Dot reads/follows installed skills directly. Send container-dependent operations to saved cloud thread and read result. [Configuration](configuration.md) defines settings; [storage](storage.md) defines ownership/recovery. Plugin installation supplies files; verify executable runtime separately.

## Bind and verify owner

1. Discover task creation, continuation/read and saved environment configuration tools. Reuse suitable existing durable child task after verifying installation identity and container access.
2. First run without suitable task: select available saved environment configuration and create durable child task with fresh cloud container. Empty connected-environment/cloud-computer list alone does not block creation; saved configuration supplies fresh container. Dot performs creation and continues setup there. Actual missing configuration, denied creation or tool failure: report specific blocker.
3. Give task persistent title **🛡️ Investment Discovery — DO NOT DELETE** through supported title control. Save returned task/thread ID and link privately; retain reference in schedule instructions. Continue same cloud thread for later operations; reuse before creating another task. Verify original stores on return; missing/damaged stores follow [recovery](storage.md#recovery).

Install pinned dependencies from `scripts/requirements.txt` and run shared `scripts/main.py setup-runtime` with chosen Python 3.11+ interpreter. Install timezone data when needed.

Ladybug extension storage: optional `SQUAD_LADYBUG_HOME`, absolute writable directory. Bind same value to setup and later operation processes in owner cloud container; choose persistent runtime storage. Default: system temporary directory, under `squad-runtime-<user ID>/ladybug`. Temporary storage cleanup requires rerunning `setup-runtime`. Runtime creates private directories and sets Ladybug's `home_directory` before installing/loading extensions.

Set `SQUAD_REPO` to approved checkout in owner cloud container. Each operation's process needs required interpreter, settings, secrets and database paths. Send container-dependent work to saved cloud thread. Verify access; different threads/scheduled runs may have separate files/credentials. Researchers return structured batches for owner ingestion. Owner lock serializes commands; live files require local access by one owner.

Use supported native settings to inject individual configuration variables. Google credentials belong only in owner secret bindings: `SQUAD_GOOGLE_REFRESH_TOKEN`, `SQUAD_GOOGLE_CLIENT_ID`, `SQUAD_GOOGLE_CLIENT_SECRET`. Avoid printing values or copying them into prompts, arguments or evidence. Verify presence privately. Client renews short-lived access tokens in memory. Restrict network to required public feeds and Google Drive/OAuth endpoints.

Use [schedule procedure](../../squad-reconcile/references/deployment.md#native-tasks) to verify scheduled Dot reaches original databases through saved cloud thread and receives result.

## Google authorization and renewal

1. Enable Drive API in user's Google Cloud project; configure OAuth consent/client for intended users. Use supported account authorization; credentials stay in native secrets.
2. Use narrow `https://www.googleapis.com/auth/drive.file` scope. Create/select private backup folder through same app authorization, such as Drive Picker. Folder ID alone grants no access.
3. Request offline access; bind refresh token, client ID and client secret. OAuth Testing status can limit refresh tokens to seven days for this scope; review actual publishing/user status. Reauthorize when token expires/revoked; preserve pending uploads while resolving access.
4. Put authorized folder ID and reviewed project/archive byte limits in ordinary settings. `backup cloud` checks folder/quota and compares server checksum. Chat's connected Drive app supplies no automatic CLI credential.
5. Retain installation/setup identity, remote file IDs and recovery instructions using [recovery storage requirement](storage.md#full-cloud-backup). Reauthorize credentials separately after loss.

Account storage shared with other Google services; inspect actual available capacity. Respect approved service budget. [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [offline OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
