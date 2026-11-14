# Cloud owner and account access

Use persistent Dot cloud computer for checkout/runtime and private stores; [configuration](configuration.md) defines settings, [storage](storage.md) defines ownership and recovery. Plugin installation supplies files; verify actual executable runtime separately.

## Bind and verify owner

Install pinned dependencies from `scripts/requirements.txt` and run shared `scripts/main.py setup-runtime` with chosen Python 3.11+ interpreter. FTS extension cache belongs to runtime user; preserve or reinstall during recovery. Install timezone data when needed.

Bind `SQUAD_REPO` to approved checkout and actual interpreter/environment on saved task. Native settings and vault bindings must reach that process. A separate cloud worker's vault/filesystem does not populate Dot's owner. Researchers return structured batches for owner ingestion. Owner lock serializes commands; live files require local access by one owner.

Use supported native settings to inject individual configuration variables. Google credentials belong only in owner secret bindings: `SQUAD_GOOGLE_REFRESH_TOKEN`, `SQUAD_GOOGLE_CLIENT_ID`, `SQUAD_GOOGLE_CLIENT_SECRET`. Avoid printing values or copying them into prompts, arguments or evidence. Verify presence privately. Client renews short-lived access tokens in memory. Restrict network to required public feeds and Google Drive/OAuth endpoints.

Use [task procedure](../../squad-reconcile/references/deployment.md#native-tasks) to verify saved execution reaching original databases. [Dot computers](https://learn.chatgpt.com/docs/dots/computers-and-apps).

## Google authorization and renewal

1. Enable Drive API in user's Google Cloud project; configure OAuth consent/client for intended users. Use supported account authorization; credentials stay in native secrets.
2. Use narrow `https://www.googleapis.com/auth/drive.file` scope. Create/select private backup folder through same app authorization, such as Drive Picker. Folder ID alone grants no access.
3. Request offline access; bind refresh token, client ID and client secret. OAuth Testing status can limit refresh tokens to seven days for this scope; review actual publishing/user status. Reauthorize when token expires/revoked; preserve pending uploads while resolving access.
4. Put authorized folder ID and reviewed project/archive byte limits in ordinary settings. `backup cloud` checks folder/quota and compares server checksum. Chat's connected Drive app supplies no automatic CLI credential.
5. Retain installation/setup identity, remote file IDs and recovery instructions privately outside owner. Reauthorize credentials separately after loss.

Account storage shared with other Google services; inspect actual available capacity. Respect approved service budget. [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [offline OAuth](https://developers.google.com/identity/protocols/oauth2/web-server), [token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
