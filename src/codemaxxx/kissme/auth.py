"""KISSME auth gate: SSH-bound 24h lease for TUI access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Optional

AUTH_TOKEN_URL = os.environ.get("CODEMAXXX_AUTH_TOKEN_URL", "https://auth.eburon.ai")
AUTH_PORTAL_URL = os.environ.get("CODEMAXXX_AUTH_PORTAL_URL", "auth.eburon.ai")
AUTH_TTL_SECONDS = max(
    300,
    int(os.environ.get("CODEMAXXX_AUTH_TTL_SECONDS", str(24 * 60 * 60))),
)
AUTH_STORE_DIR = Path(
    os.path.expanduser(os.environ.get("CODEMAXXX_AUTH_DIR", "~/.codemaxxx/kissme"))
)
AUTH_LEASE_FILE = AUTH_STORE_DIR / "auth_lease.json"
SSH_PUB_ENV = os.environ.get("CODEMAXXX_AUTH_SSH_PUB", "").strip()
SSH_PUB_CANDIDATES = (
    "~/.ssh/id_ed25519.pub",
    "~/.ssh/id_rsa.pub",
    "~/.ssh/id_ecdsa.pub",
    "~/.ssh/id_dsa.pub",
)


@dataclass(frozen=True)
class AuthStatus:
    authenticated: bool
    reason: str
    token_url: str
    portal_url: str
    expires_at: Optional[datetime]
    seconds_left: int
    ssh_key_path: str
    ssh_fingerprint: str

    @property
    def expires_at_iso(self) -> str:
        if not self.expires_at:
            return ""
        return self.expires_at.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_expiry(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    raw = str(value).strip()
    if not raw:
        return None
    if raw.isdigit():
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except Exception:
            return None
    return _parse_iso(raw)


def _first_present(payload: dict, keys: tuple[str, ...]) -> str:
    for key in keys:
        value = payload.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def discover_ssh_public_key() -> tuple[str, str]:
    candidates: list[str] = []
    if SSH_PUB_ENV:
        candidates.append(SSH_PUB_ENV)
    candidates.extend(SSH_PUB_CANDIDATES)

    for candidate in candidates:
        path = Path(os.path.expanduser(candidate))
        if not path.exists() or not path.is_file():
            continue
        try:
            content = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if not content:
            continue
        return str(path), content

    return "", ""


def ssh_fingerprint(pub_key: str) -> str:
    """Return OpenSSH-style SHA256 fingerprint."""
    key = (pub_key or "").strip()
    if not key:
        return ""

    parts = key.split()
    if len(parts) >= 2:
        b64 = parts[1].strip()
        pad = "=" * (-len(b64) % 4)
        try:
            raw = base64.b64decode(b64 + pad, validate=False)
            digest = hashlib.sha256(raw).digest()
            text = base64.b64encode(digest).decode("ascii").rstrip("=")
            return f"SHA256:{text}"
        except Exception:
            pass

    digest = hashlib.sha256(key.encode("utf-8")).digest()
    text = base64.b64encode(digest).decode("ascii").rstrip("=")
    return f"SHA256:{text}"


def _load_lease() -> dict:
    if not AUTH_LEASE_FILE.exists():
        return {}
    try:
        payload = json.loads(AUTH_LEASE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_lease(payload: dict) -> bool:
    try:
        AUTH_STORE_DIR.mkdir(parents=True, exist_ok=True)
        AUTH_LEASE_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _decode_base64_json(token: str) -> tuple[bool, dict | str]:
    raw = (token or "").strip()
    if not raw:
        return False, "Token is empty."

    if raw.lower().startswith("bearer "):
        raw = raw.split(None, 1)[1].strip()

    # JWT-like token support: decode payload segment.
    if raw.count(".") == 2:
        raw = raw.split(".")[1].strip()

    candidates = [raw, raw.replace("-", "+").replace("_", "/")]
    for candidate in candidates:
        pad = "=" * (-len(candidate) % 4)
        try:
            decoded = base64.b64decode(candidate + pad, validate=False).decode("utf-8")
        except Exception:
            continue
        try:
            payload = json.loads(decoded)
        except Exception:
            continue
        if isinstance(payload, dict):
            return True, payload

    return False, "Token is not valid base64 JSON."


def get_auth_status(machine_uid: str) -> AuthStatus:
    now = _utc_now()
    key_path, key_text = discover_ssh_public_key()
    if not key_path or not key_text:
        return AuthStatus(
            authenticated=False,
            reason="No SSH public key found. Create one in ~/.ssh and request a token.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
            ssh_key_path="",
            ssh_fingerprint="",
        )

    fingerprint = ssh_fingerprint(key_text)
    lease = _load_lease()
    if not lease:
        return AuthStatus(
            authenticated=False,
            reason="No active auth lease found.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
            ssh_key_path=key_path,
            ssh_fingerprint=fingerprint,
        )

    lease_machine = str(lease.get("machine_uid", "")).strip()
    if lease_machine and lease_machine != machine_uid:
        return AuthStatus(
            authenticated=False,
            reason="Auth lease machine mismatch.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
            ssh_key_path=key_path,
            ssh_fingerprint=fingerprint,
        )

    lease_fingerprint = str(lease.get("ssh_fingerprint", "")).strip()
    if lease_fingerprint and lease_fingerprint != fingerprint:
        return AuthStatus(
            authenticated=False,
            reason="SSH fingerprint mismatch. Request a new token for this machine key.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
            ssh_key_path=key_path,
            ssh_fingerprint=fingerprint,
        )

    expires_at = _parse_expiry(lease.get("expires_at") or lease.get("exp"))
    if not expires_at:
        return AuthStatus(
            authenticated=False,
            reason="Auth lease is invalid (missing expiry).",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
            ssh_key_path=key_path,
            ssh_fingerprint=fingerprint,
        )

    seconds_left = int((expires_at - now).total_seconds())
    if seconds_left <= 0:
        return AuthStatus(
            authenticated=False,
            reason="Auth lease expired. Re-authentication required.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=expires_at,
            seconds_left=0,
            ssh_key_path=key_path,
            ssh_fingerprint=fingerprint,
        )

    return AuthStatus(
        authenticated=True,
        reason="ok",
        token_url=AUTH_TOKEN_URL,
        portal_url=AUTH_PORTAL_URL,
        expires_at=expires_at,
        seconds_left=seconds_left,
        ssh_key_path=key_path,
        ssh_fingerprint=fingerprint,
    )


def activate_base64_token(token: str, machine_uid: str) -> tuple[bool, str, AuthStatus]:
    key_path, key_text = discover_ssh_public_key()
    if not key_path or not key_text:
        status = get_auth_status(machine_uid)
        return False, "SSH public key missing. Create one first (for example ~/.ssh/id_ed25519.pub).", status

    fingerprint = ssh_fingerprint(key_text)
    ok, decoded = _decode_base64_json(token)
    if not ok:
        status = get_auth_status(machine_uid)
        return False, str(decoded), status

    payload = decoded
    now = _utc_now()

    token_machine = _first_present(payload, ("machine_uid", "machine", "uid"))
    if token_machine and token_machine != machine_uid:
        status = get_auth_status(machine_uid)
        return False, "Token machine does not match this machine.", status

    token_uid = _first_present(payload, ("uid", "user_uid", "firebase_uid"))
    if not token_uid:
        status = get_auth_status(machine_uid)
        return False, "Token missing user UID.", status

    token_fp = _first_present(payload, ("ssh_fingerprint", "ssh_fp", "fingerprint"))
    if token_fp and token_fp != fingerprint:
        status = get_auth_status(machine_uid)
        return False, "Token SSH fingerprint mismatch for this machine key.", status

    token_secret = _first_present(payload, ("kissme_secret", "secret_code", "secret"))
    if len(token_secret) < 8:
        status = get_auth_status(machine_uid)
        return False, "Token missing valid KISSME secret code.", status

    expires_at = _parse_expiry(
        payload.get("exp")
        or payload.get("expires_at")
        or payload.get("expires")
        or payload.get("valid_until")
    )
    if not expires_at:
        expires_at = now + timedelta(seconds=AUTH_TTL_SECONDS)

    max_exp = now + timedelta(seconds=AUTH_TTL_SECONDS)
    if expires_at > max_exp:
        expires_at = max_exp
    if expires_at <= now:
        status = get_auth_status(machine_uid)
        return False, "Token already expired.", status

    lease_payload = {
        "issuer": _first_present(payload, ("issuer", "iss")) or "auth.eburon.ai",
        "uid": token_uid,
        "machine_uid": machine_uid,
        "ssh_fingerprint": fingerprint,
        "kissme_secret": token_secret,
        "ssh_key_path": key_path,
        "issued_at": _to_iso(now),
        "expires_at": _to_iso(expires_at),
        "token_preview": (token or "").strip()[-10:],
    }
    if not _save_lease(lease_payload):
        status = get_auth_status(machine_uid)
        return False, f"Could not persist auth lease at {AUTH_LEASE_FILE}.", status

    status = get_auth_status(machine_uid)
    minutes = max(1, int(status.seconds_left // 60))
    return True, f"Authenticated. Lease valid for {minutes} minutes.", status
