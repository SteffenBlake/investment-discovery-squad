# Execution environment and account access

Use one owner execution environment for checkout, runtime and private stores. Coordinating Dot reads/follows installed skills directly. For environment-dependent operations, send instructions to existing coding chat and read result. [Configuration](configuration.md) defines settings; [storage](storage.md) defines ownership/recovery. Plugin installation supplies files; verify executable runtime separately.

## Bind and verify owner

Install pinned dependencies from `scripts/requirements.txt` and run shared `scripts/main.py setup-runtime` with chosen Python 3.11+ interpreter. Install timezone data when needed.

Ladybug extension storage: optional `SQUAD_LADYBUG_HOME`, absolute writable directory. Bind same value to setup and later operation processes in owner execution environment; choose persistent runtime storage. Default: system temporary directory, under `squad-runtime-<user ID>/ladybug`. Temporary storage cleanup requires rerunning `setup-runtime`. Runtime creates private directories and sets Ladybug's `home_directory` before installing/loading extensions.

Set `SQUAD_REPO` to approved checkout in owner execution environment. Each operation's process needs required interpreter, settings, secrets and database paths. Send environment-dependent work to existing coding chat. Verify access; different chats/scheduled runs may have separate files/credentials. Researchers return structured batches for owner ingestion. Owner lock serializes commands; live files require local access by one owner.

Use supported native settings to inject individual configuration variables. Google credentials belong only in owner secret bindings: `SQUAD_GOOGLE_REFRESH_TOKEN`, `SQUAD_GOOGLE_CLIENT_ID`, `SQUAD_GOOGLE_CLIENT_SECRET`. Avoid printing values or copying them into prompts, arguments or evidence. Verify presence privately. Client renews short-lived access tokens in memory. Restrict network to required public feeds and Google Drive/OAuth endpoints.

Use [task procedure](../../squad-reconcile/references/deployment.md#native-tasks) to verify scheduled Dot reaches original databases through existing coding chat and receives result. [Dot computers](https://learn.chatgpt.com/docs/dots/computers-and-apps).

## Google authorization and renewal

1. Enable Drive API in user's Google Cloud project; configure OAuth consent/client for intended users. Use supported account authorization; credentials stay in native secrets.
2. Use narrow `https://www.googleapis.com/auth/drive.file` scope. Create/select private backup folder through same app authorization, such as Drive Picker. Folder ID alone grants no access.
3. Request offline access; bind refresh token, client ID and client secret. OAuth Testing status can limit refresh tokens to seven days for this scope; review actual publishing/user status. Reauthorize when token expires/revoked; preserve pending uploads while resolving access.
4. Put authorized folder ID and reviewed project/archive byte limits in ordinary settings. `backup cloud` checks folder/quota and compares server checksum. Chat's connected Drive app supplies no automatic CLI credential.
5. Retain installation/setup identity, remote file IDs and recovery instructions using [recovery storage requirement](storage.md#full-cloud-backup). Reauthorize credentials separately after loss.

Account storage shared with other Google services; inspect actual available capacity. Respect approved service budget. [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [offline OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
