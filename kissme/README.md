# KISSME Auth Layer

This folder documents the auth-lease behavior that gates TUI model access.

## Goal

- Keep local usage unlimited while connected.
- Require an SSH-bound base64 token every 24 hours.
- Expire the lease automatically so the model disconnects from TUI until re-authenticated.

## Runtime UX

When auth is missing/expired, TUI shows:

- `Authenticate: https://auth.eburon.ai/token`
- `Reason: ...`
- `SSH fingerprint: ...`
- instruction: `/auth <base64-token>`

## Token shape (base64 JSON payload)

```json
{
  "issuer": "auth.eburon.ai",
  "machine_uid": "32-char-machine-id",
  "ssh_fingerprint": "SHA256:...",
  "exp": 1760000000
}
```

Accepted expiry fields: `exp`, `expires_at`, `expires`, `valid_until`.

## Files

- `src/codemaxxx/kissme/auth.py` - token decoding, lease persistence, 24h enforcement.
- `src/codemaxxx/agent.py` - auth gate, `/auth`, `/auth-status`, model lock when expired.

