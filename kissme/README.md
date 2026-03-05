# KISSME Auth Layer

This folder documents the auth-lease behavior that gates TUI model access.

## Goal

- Keep local usage unlimited while connected.
- Require a machine-UID-bound base64 token every 24 hours.
- Expire the lease automatically so the model disconnects from TUI until re-authenticated.
- Verify token lease against Firebase RTDB before unlocking the CLI.

## Runtime UX

When auth is missing/expired, TUI shows:

- `KISS ME Portal: auth.eburon.ai`
- `Reason: ...`
- `Machine UID: ...`
- instruction: `/kissme` then `/auth <base64-token>`

## Token shape

Primary flow now uses:

- `machine_key_b64 = base64(machine_uid)`
- user pastes this key into CLI `input key =`
- CLI decodes and matches against local machine UID

Compatibility flow (still supported):

Base64 JSON payload:

```json
{
  "issuer": "auth.eburon.ai",
  "uid": "firebase-user-uid",
  "key_id": "firebase-lease-key",
  "did_kissme": "yes",
  "machine_key_b64": "<base64-machine-uid>",
  "kissme_secret": "KMS-xxxxxxxxxxxxxxxxxxxxxxxx",
  "machine_uid": "32-char-machine-id",
  "exp": 1760000000
}
```

Accepted expiry fields: `exp`, `expires_at`, `expires`, `valid_until`.

`did_kissme` is mandatory and must be `yes` for the CLI 24h countdown to start. If `no`, countdown stays `00:00:00`.

## Files

- `src/codemaxxx/kissme/auth.py` - token decoding, Firebase lease verification, local lease persistence, 24h enforcement.
- `src/codemaxxx/agent.py` - auth gate, `/kissme`, `/auth`, `/auth-status`, model lock when expired.
- `kissme/token.html` - single-file Firebase token issuer UI for new/returning users.

## Firebase storage

This page stores KISSME auth UID + token metadata in Realtime Database:

- `kissme_auth_users/<uid>/profile`
- `kissme_auth_users/<uid>/sessions/<session_id>`
- `kissme_auth_users/<uid>/leases/<key_id>`

CLI machine cache files:

- `~/.codemaxxx/kissme/auth_lease.json`
- `~/.codemaxxx/kissme/firebase_session.json`

Optional environment flags:

- `CODEMAXXX_KISSME_FIREBASE_VERIFY=1|0` (default: `0`)
- `CODEMAXXX_FIREBASE_DB_URL=<firebase-rtdb-url>`
- `CODEMAXXX_FIREBASE_TIMEOUT_SECONDS=<seconds>`
- `CODEMAXXX_FIREBASE_DB_AUTH_TOKEN=<firebase-db-token>` (optional fallback for JSON-token verification mode)
- `CODEMAXXX_FIREBASE_MATCH_WAIT_SECONDS=<seconds>` (default: `2`)
- `CODEMAXXX_FIREBASE_MATCH_RETRY_SECONDS=<seconds>` (default: `0.5`)
