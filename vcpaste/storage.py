"""
Profile storage: saves VC.ru accounts locally.

Passwords are obfuscated with base64 (NOT strong encryption).
This only hides them from a casual glance in the file; anyone with
access to the machine can still recover them. Documented on purpose.
"""
import base64
import json
import os
from pathlib import Path


def _data_dir() -> Path:
    """Per-user writable folder for storing profiles."""
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    d = Path(base) / "VCPasteHelper"
    d.mkdir(parents=True, exist_ok=True)
    return d


PROFILES_FILE = _data_dir() / "profiles.json"


def _encode(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _decode(text: str) -> str:
    try:
        return base64.b64decode(text.encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def load_profiles() -> list:
    """Return list of {'email','password'} dicts."""
    if not PROFILES_FILE.exists():
        return []
    try:
        raw = json.loads(PROFILES_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for item in raw:
        email = item.get("email", "")
        pw = _decode(item.get("password", ""))
        if email:
            out.append({"email": email, "password": pw})
    return out


def save_profile(email: str, password: str) -> list:
    """Add or update a profile, keep most-recent first. Returns updated list."""
    email = (email or "").strip()
    if not email:
        return load_profiles()
    profiles = load_profiles()
    # remove any existing entry with same email
    profiles = [p for p in profiles if p["email"].lower() != email.lower()]
    # newest goes to the front
    profiles.insert(0, {"email": email, "password": password or ""})
    _write(profiles)
    return profiles


def delete_profile(email: str) -> list:
    profiles = [p for p in load_profiles()
                if p["email"].lower() != (email or "").lower()]
    _write(profiles)
    return profiles


def _write(profiles: list) -> None:
    serial = [{"email": p["email"], "password": _encode(p["password"])}
              for p in profiles]
    tmp = PROFILES_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(serial, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    tmp.replace(PROFILES_FILE)
