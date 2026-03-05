"""KISSME auth gate: machine-bound 24h lease for TUI access."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import json
import os
import time
from pathlib import Path
from typing import Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlencode

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
FIREBASE_SESSION_FILE = AUTH_STORE_DIR / "firebase_session.json"
FIREBASE_DB_URL = (
    os.environ.get(
        "CODEMAXXX_FIREBASE_DB_URL",
        "https://impactful-ring-469323-e5-default-rtdb.europe-west1.firebasedatabase.app",
    )
    .strip()
    .rstrip("/")
)
FIREBASE_TIMEOUT_SECONDS = max(
    1.0,
    float(os.environ.get("CODEMAXXX_FIREBASE_TIMEOUT_SECONDS", "6")),
)
FIREBASE_DB_AUTH_TOKEN = os.environ.get("CODEMAXXX_FIREBASE_DB_AUTH_TOKEN", "").strip()
FIREBASE_MATCH_WAIT_SECONDS = max(
    0.0,
    float(os.environ.get("CODEMAXXX_FIREBASE_MATCH_WAIT_SECONDS", "2")),
)
FIREBASE_MATCH_RETRY_SECONDS = max(
    0.2,
    float(os.environ.get("CODEMAXXX_FIREBASE_MATCH_RETRY_SECONDS", "0.5")),
)
ALLOW_FIREBASE_NETWORK_FALLBACK = os.environ.get("CODEMAXXX_FIREBASE_NETWORK_FALLBACK", "1").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
FIREBASE_NETWORK_FALLBACK_SECONDS = max(
    300,
    int(os.environ.get("CODEMAXXX_FIREBASE_NETWORK_FALLBACK_SECONDS", str(AUTH_TTL_SECONDS))),
)


@dataclass(frozen=True)
class AuthStatus:
    authenticated: bool
    reason: str
    token_url: str
    portal_url: str
    expires_at: Optional[datetime]
    seconds_left: int

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


def _normalize_yes_no(value) -> str:
    text = str(value or "").strip().lower()
    if text in ("yes", "y", "true", "1"):
        return "yes"
    if text in ("no", "n", "false", "0"):
        return "no"
    return ""


def _is_firebase_network_error(message: str) -> bool:
    text = (message or "").strip().lower()
    if not text:
        return False
    markers = (
        "nodename nor servname",
        "temporary failure in name resolution",
        "name or service not known",
        "network is unreachable",
        "connection refused",
        "timed out",
        "timeout",
        "failed to establish",
        "[errno 8]",
        "urlopen error",
        "dns",
    )
    return any(marker in text for marker in markers)


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


def _save_firebase_session(payload: dict) -> bool:
    try:
        AUTH_STORE_DIR.mkdir(parents=True, exist_ok=True)
        FIREBASE_SESSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return True
    except Exception:
        return False


def _firebase_get_json(path: str, auth_token: str = "") -> tuple[bool, dict | None | str]:
    if not FIREBASE_DB_URL:
        return False, "Firebase DB URL is not configured."
    rel = (path or "").strip().lstrip("/")
    if not rel:
        return False, "Firebase DB path is empty."
    if not rel.endswith(".json"):
        rel += ".json"
    url = f"{FIREBASE_DB_URL}/{rel}"
    token = (auth_token or "").strip() or FIREBASE_DB_AUTH_TOKEN
    if token:
        url = f"{url}?{urlencode({'auth': token})}"
    req = urllib_request.Request(url=url, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=FIREBASE_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except urllib_error.HTTPError as err:
        if err.code == 404:
            return True, None
        if err.code in (401, 403):
            if token:
                return False, (
                    f"Firebase lease lookup unauthorized (HTTP {err.code}). "
                    "Firebase auth token may be expired; reconnect in browser and issue a fresh token."
                )
            return False, (
                f"Firebase lease lookup unauthorized (HTTP {err.code}). "
                "Provide firebase_id_token in auth payload or set CODEMAXXX_FIREBASE_DB_AUTH_TOKEN."
            )
        return False, f"Firebase lease lookup failed (HTTP {err.code})."
    except Exception as err:
        return False, f"Firebase lease lookup failed: {err}"

    try:
        payload = json.loads(raw or "null")
    except Exception:
        return False, "Firebase lease lookup returned invalid JSON."

    if payload is None:
        return True, None
    if not isinstance(payload, dict):
        return False, "Firebase lease lookup returned invalid payload shape."
    return True, payload


def _verify_with_firebase(
    payload: dict,
    machine_uid: str,
    token_uid: str,
    token_secret: str,
) -> tuple[bool, str, dict]:
    """Verify token lease record against Firebase RTDB."""
    key_id = _first_present(payload, ("key_id", "kid", "lease_id"))
    if not key_id:
        return False, "Token missing key_id required for Firebase verification.", {}

    token_answer = _normalize_yes_no(payload.get("did_kissme") or payload.get("didHeKissme") or payload.get("kissme"))
    if token_answer != "yes":
        return False, "did_he_kissme must be yes to activate 24h lease.", {}

    firebase_auth_token = _first_present(
        payload,
        ("firebase_id_token", "firebase_token", "id_token", "firebaseIdToken"),
    )
    if not firebase_auth_token and not FIREBASE_DB_AUTH_TOKEN:
        return False, "Token missing firebase_id_token for Firebase lease verification.", {}

    lease_path = f"kissme_auth_users/{token_uid}/leases/{key_id}"
    deadline = time.monotonic() + FIREBASE_MATCH_WAIT_SECONDS
    lease: dict | None = None
    last_error = "Token lease not found in Firebase."

    while True:
        ok, record_or_error = _firebase_get_json(
            lease_path,
            auth_token=firebase_auth_token,
        )
        if ok and isinstance(record_or_error, dict):
            lease = record_or_error
            break

        if not ok:
            last_error = str(record_or_error)
        else:
            last_error = "Token lease not found in Firebase."

        if time.monotonic() >= deadline:
            token_type = _first_present(payload, ("token_type", "type", "kind")).lower()
            if (
                ALLOW_FIREBASE_NETWORK_FALLBACK
                and _is_firebase_network_error(last_error)
                and token_type == "firebase_signed"
                and len(firebase_auth_token) >= 80
            ):
                return True, "firebase_network_fallback", {
                    "firebase_key_id": key_id,
                    "firebase_verified_at": _to_iso(_utc_now()),
                    "did_kissme": "yes",
                    "firebase_verify_mode": "network_fallback",
                }
            return False, last_error, {}

        remaining = max(0.0, deadline - time.monotonic())
        time.sleep(min(FIREBASE_MATCH_RETRY_SECONDS, remaining))

    if not lease:
        return False, "Token lease not found in Firebase.", {}

    lease_uid = _first_present(lease, ("uid", "user_uid", "firebase_uid"))
    if lease_uid and lease_uid != token_uid:
        return False, "Firebase lease UID mismatch.", {}

    lease_machine = _first_present(lease, ("machine_uid", "machine", "uid_machine"))
    if lease_machine != machine_uid:
        return False, "Firebase lease machine mismatch.", {}

    lease_secret = _first_present(lease, ("kissme_secret", "secret_code", "secret"))
    if len(lease_secret) < 8 or lease_secret != token_secret:
        return False, "Firebase lease secret mismatch.", {}

    lease_answer = _normalize_yes_no(lease.get("did_kissme") or lease.get("didHeKissme") or lease.get("kissme"))
    if lease_answer != "yes":
        return False, "Firebase says did_he_kissme=no. Countdown stays 00:00:00.", {}
    if token_answer != lease_answer:
        return False, "Token did_kissme mismatch with Firebase lease.", {}

    lease_exp = _parse_expiry(lease.get("exp") or lease.get("expires_at") or lease.get("expiresAtIso"))
    if not lease_exp:
        return False, "Firebase lease is missing expiry.", {}

    token_exp = _parse_expiry(
        payload.get("exp")
        or payload.get("expires_at")
        or payload.get("expires")
        or payload.get("valid_until")
    )
    if token_exp and abs((lease_exp - token_exp).total_seconds()) > 300:
        return False, "Token expiry does not match Firebase lease.", {}

    return True, "ok", {"firebase_key_id": key_id, "firebase_verified_at": _to_iso(_utc_now()), "did_kissme": "yes"}


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

        decoded_text = decoded.strip().lower()
        is_legacy_machine_key = (
            len(decoded_text) == 32 and all(ch in "0123456789abcdef" for ch in decoded_text)
        )
        if is_legacy_machine_key:
            return (
                False,
                "Legacy machine key detected. This CLI now requires a signed KISSME token from the portal.",
            )

        try:
            payload = json.loads(decoded)
        except Exception:
            continue
        if isinstance(payload, dict):
            return True, payload

    return False, "Token is not valid base64 JSON payload."


def get_auth_status(machine_uid: str) -> AuthStatus:
    now = _utc_now()
    lease = _load_lease()
    if not lease:
        return AuthStatus(
            authenticated=False,
            reason="No active auth lease found.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
        )

    lease_machine = str(lease.get("machine_uid", "")).strip()
    if lease_machine and lease_machine != machine_uid:
        return AuthStatus(
            authenticated=False,
            reason="No active auth lease for this machine. Re-authentication required.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
        )

    lease_answer = _normalize_yes_no(lease.get("did_kissme") or lease.get("didHeKissme") or lease.get("kissme"))
    if lease_answer != "yes":
        return AuthStatus(
            authenticated=False,
            reason="did_he_kissme is not yes. Re-authentication required.",
            token_url=AUTH_TOKEN_URL,
            portal_url=AUTH_PORTAL_URL,
            expires_at=None,
            seconds_left=0,
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
        )

    return AuthStatus(
        authenticated=True,
        reason="ok",
        token_url=AUTH_TOKEN_URL,
        portal_url=AUTH_PORTAL_URL,
        expires_at=expires_at,
        seconds_left=seconds_left,
    )


def activate_base64_token(token: str, machine_uid: str) -> tuple[bool, str, AuthStatus]:
    ok, decoded = _decode_base64_json(token)
    if not ok:
        status = get_auth_status(machine_uid)
        return False, str(decoded), status

    payload = decoded
    now = _utc_now()

    token_machine = _first_present(payload, ("machine_uid", "machine", "uid_machine"))
    if not token_machine:
        status = get_auth_status(machine_uid)
        return False, "Token missing machine UID.", status
    if token_machine != machine_uid:
        status = get_auth_status(machine_uid)
        return False, "Token machine does not match this machine.", status

    token_uid = _first_present(payload, ("uid", "user_uid", "firebase_uid"))
    token_secret = _first_present(payload, ("kissme_secret", "secret_code", "secret"))
    token_answer = _normalize_yes_no(payload.get("did_kissme") or payload.get("didHeKissme") or payload.get("kissme"))
    if token_answer != "yes":
        status = get_auth_status(machine_uid)
        return False, "did_he_kissme must be yes.", status

    if not token_uid:
        status = get_auth_status(machine_uid)
        return False, "Token missing user UID.", status

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
        status = get_auth_status(machine_uid)
        return False, "Token missing expiry.", status

    max_exp = now + timedelta(seconds=AUTH_TTL_SECONDS)
    if expires_at > max_exp:
        expires_at = max_exp
    if expires_at <= now:
        status = get_auth_status(machine_uid)
        return False, "Token already expired.", status

    verified, verify_msg, verify_meta = _verify_with_firebase(payload, machine_uid, token_uid, token_secret)
    if not verified:
        status = get_auth_status(machine_uid)
        return False, verify_msg, status
    verify_mode = str(verify_meta.get("firebase_verify_mode", "")).strip().lower()
    if verify_mode == "network_fallback":
        max_fallback_exp = now + timedelta(seconds=FIREBASE_NETWORK_FALLBACK_SECONDS)
        if expires_at > max_fallback_exp:
            expires_at = max_fallback_exp

    lease_payload = {
        "issuer": _first_present(payload, ("issuer", "iss")) or "auth.eburon.ai",
        "uid": token_uid,
        "machine_uid": machine_uid,
        "kissme_secret": token_secret,
        "did_kissme": "yes",
        "issued_at": _to_iso(now),
        "expires_at": _to_iso(expires_at),
        "token_preview": (token or "").strip()[-10:],
    }
    lease_payload.update(verify_meta)
    if not _save_lease(lease_payload):
        status = get_auth_status(machine_uid)
        return False, f"Could not persist auth lease at {AUTH_LEASE_FILE}.", status

    _save_firebase_session(
        {
            "uid": token_uid,
            "machine_uid": machine_uid,
            "issuer": lease_payload["issuer"],
            "firebase_db_url": FIREBASE_DB_URL,
            "firebase_key_id": lease_payload.get("firebase_key_id", ""),
            "firebase_verified_at": lease_payload.get("firebase_verified_at", ""),
            "did_kissme": lease_payload.get("did_kissme", ""),
            "expires_at": lease_payload["expires_at"],
            "updated_at": _to_iso(_utc_now()),
        }
    )

    status = get_auth_status(machine_uid)
    minutes = max(1, int(status.seconds_left // 60))
    if verify_mode == "network_fallback":
        return True, f"Authenticated (signed token fallback). Lease valid for {minutes} minutes.", status
    return True, f"Authenticated (Firebase verified). Lease valid for {minutes} minutes.", status
