"""CodeMaxxx — Silent machine UID fingerprint (read-only to user)."""

import hashlib
import platform
import subprocess
import os
import uuid


def _run(cmd: str) -> str:
    try:
        return subprocess.check_output(cmd, shell=True, text=True, timeout=5).strip()
    except Exception:
        return ""


def get_machine_uid() -> str:
    """Generate a deterministic machine UID from hardware identifiers.
    
    This is silent, read-only from the user's perspective.
    Built from: platform node + macOS hardware UUID or Linux machine-id + CPU brand.
    """
    parts = []

    # hostname
    parts.append(platform.node())

    # macOS: IOPlatformUUID
    if platform.system() == "Darwin":
        hw_uuid = _run(
            "ioreg -rd1 -c IOPlatformExpertDevice | awk '/IOPlatformUUID/ {print $3}' | tr -d '\"'"
        )
        if hw_uuid:
            parts.append(hw_uuid)

    # Linux: /etc/machine-id
    elif platform.system() == "Linux":
        try:
            with open("/etc/machine-id", "r") as f:
                parts.append(f.read().strip())
        except FileNotFoundError:
            pass

    # CPU brand
    cpu = platform.processor() or _run("sysctl -n machdep.cpu.brand_string 2>/dev/null")
    if cpu:
        parts.append(cpu)

    # MAC address fallback
    mac = hex(uuid.getnode())
    parts.append(mac)

    fingerprint = "|".join(parts)
    return hashlib.sha256(fingerprint.encode()).hexdigest()[:32]
