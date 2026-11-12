# Cloud execution and secure access

## One central owner

Use Dot's own persistent cloud computer as the sole owner: checkout, installed Python/Ladybug runtime, one private data directory, and separate backup staging. No SSH, public database port, personal-computer connection or server purchase is required for this arrangement. Dot uses its native computer/code tools to run the CLI and read files. A plugin alone does not provision this runtime.

This project has no connected-personal-computer or headless-server deployment route and exposes no remote-access daemon.

Codex Cloud environments have per-task isolated filesystems. Selecting the same environment does not create a shared live database. Delegated researchers return structured JSON batches to the central Dot, which ingests them on its own owner runtime. They must not initialize substitute databases. A central command lock serializes CLI operations and fails clearly on contention; do not open independent writable Ladybug instances or mount live database files over a network filesystem.

If a selected scheduled surface cannot invoke the central owner, configure a supported actual handoff/owner execution route or keep it inactive. Do not claim a cross-runtime connection that has not been demonstrated. The independent saved-task probe must reopen both original paths and return matching identities. [Dot computers](https://learn.chatgpt.com/docs/dots/computers-and-apps), [Codex Cloud environments](https://learn.chatgpt.com/docs/environments/cloud-environments).

## Runtime preparation

Clone the approved Git source on the owner. Create a virtualenv, run `python -m pip install -e .`, then `python -m squad setup-runtime`. That command installs/loads the matching Ladybug full-text extension in the runtime user's writable extension cache, using only a temporary probe graph. It never initializes production state. Preserve that cache or reinstall during runtime recovery. Install timezone data if the image lacks it.

Set SQUAD_REPO to the actual checkout when invoking outside it; select the virtualenv interpreter through the task's real execution environment. Thin task prompts describe required bindings but do not magically set shell variables. Use actual environment/runtime controls or explicit structured command arguments.

## Configuration and secrets

Bind individual configuration variables and required credentials through the actual owner runtime's supported native settings/secret controls. Personal vault settings in delegated environments stay scoped there. Inject non-secret `SQUAD_*` configuration only into the owner and workers that need it. Inject Google OAuth credentials only into the owner running backups. Avoid echoing environment contents or putting credentials in prompts, arguments, receipts or evidence.

Native Codex Cloud settings belong to the environments/tasks selected in that product. They do not automatically populate Dot's own computer. Bind values through the actual owner's supported controls and verify presence without printing secrets. The CLI accepts only the documented individual native configuration variables; no JSON profile file or JSON-blob configuration is loaded. [Native variables, vault and network secrets](https://learn.chatgpt.com/docs/environments/cloud-environments).

Required credential bindings: SQUAD_GOOGLE_REFRESH_TOKEN + SQUAD_GOOGLE_CLIENT_ID + SQUAD_GOOGLE_CLIENT_SECRET. The client obtains and renews short-lived access tokens in memory; there is no separately supplied access-token deployment mode. Scope network access to required public sources and Google's Drive/OAuth endpoints. Python rejects non-Google upload/redirect destinations.

## Google Drive authorization

Google Drive is an independent, user-owned backup destination. An existing OpenAI plan does not grant it storage. Google accounts have up to 15 GB free shared across Drive, Gmail and Photos; available space can be smaller. This implementation uses standard Drive API operations, explicit account/project byte limits and archives capped at 1 GiB. It never buys storage. [Google storage](https://support.google.com/drive/answer/2375123), [Drive API limits](https://developers.google.com/workspace/drive/api/guides/limits).

One-time authorization:

1. In the user's Google Cloud project, enable Google Drive API and configure its OAuth consent/client for the intended personal use. No brokerage credentials are involved. Keep the backup folder private.
2. Prefer the narrow `https://www.googleapis.com/auth/drive.file` scope. Create/select the backup folder through that same authorized app flow (for example Drive Picker), so the app has access to it. Merely pasting an arbitrary existing folder ID does not grant access. Do not request broad Drive access just to work around an inaccessible folder.
3. Authorize offline access through Google's documented OAuth flow. Store the client ID, client secret and refresh token in native runtime secrets. All three OAuth bindings are required for renewable backups. OAuth apps left in Testing may receive seven-day refresh tokens for this scope; configure the app's intended publishing/user status rather than assuming indefinite credentials.
4. Put only the authorized folder ID and explicit capacity limits in non-secret configuration. `backup cloud` checks folder access/quota, uploads, downloads and restores. A connected Google Drive app in chat is not automatically a bearer token for this CLI.
5. Retain recovery instructions, profile ID, setup identity and cloud file receipts privately outside the owner. Credentials stay in the secret manager and are reauthorized separately after loss.

No OAuth consent, account API enablement, native task or folder is fabricated by repository code. [Drive scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth), [web-server OAuth/offline access](https://developers.google.com/identity/protocols/oauth2/web-server), [refresh-token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
