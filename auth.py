"""
auth.py — Login / Signup / Session Management
===============================================
Lightweight auth system using Flask sessions + password hashing.
No database needed — credentials stored in data/auth.json.

For a production deployment you'd swap this for:
  - PostgreSQL + SQLAlchemy, OR
  - Firebase Auth, OR
  - Auth0 / Clerk

But for a local/demo product this is solid and self-contained.

Routes registered in app.py:
    POST /auth/signup   { username, password, display_name }
    POST /auth/login    { username, password }
    POST /auth/logout
    GET  /auth/me       → current logged-in user
"""

import json, hashlib, os, time, secrets
from pathlib import Path
from flask import request, jsonify, session

DATA_DIR   = Path(__file__).parent / "data"
AUTH_FILE  = DATA_DIR / "auth.json"
DATA_DIR.mkdir(exist_ok=True)


def _load_users() -> dict:
    if AUTH_FILE.exists():
        return json.loads(AUTH_FILE.read_text())
    return {}


def _save_users(users: dict):
    AUTH_FILE.write_text(json.dumps(users, indent=2))


def _hash_pw(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


# ── Public functions ──────────────────────────────────────────────────────

def signup(username: str, password: str, display_name: str = "") -> dict:
    """
    Create a new account.
    Returns {"ok": True, "user_id": ...} or {"ok": False, "error": ...}
    """
    username = username.strip().lower()
    if not username or len(username) < 2:
        return {"ok": False, "error": "Username must be at least 2 characters"}
    if not password or len(password) < 6:
        return {"ok": False, "error": "Password must be at least 6 characters"}

    users = _load_users()
    if username in users:
        return {"ok": False, "error": "Username already taken"}

    salt   = secrets.token_hex(16)
    hashed = _hash_pw(password, salt)
    users[username] = {
        "username":     username,
        "display_name": display_name or username.capitalize(),
        "salt":         salt,
        "password":     hashed,
        "created_at":   time.time(),
    }
    _save_users(users)
    return {"ok": True, "user_id": username, "display_name": users[username]["display_name"]}


def login(username: str, password: str) -> dict:
    """
    Verify credentials.
    Returns {"ok": True, "user_id": ...} or {"ok": False, "error": ...}
    """
    username = username.strip().lower()
    users    = _load_users()
    user     = users.get(username)
    if not user:
        return {"ok": False, "error": "User not found"}

    hashed = _hash_pw(password, user["salt"])
    if hashed != user["password"]:
        return {"ok": False, "error": "Incorrect password"}

    return {
        "ok":           True,
        "user_id":      username,
        "display_name": user["display_name"],
        "created_at":   user["created_at"],
    }


def get_user(username: str) -> dict | None:
    return _load_users().get(username.lower())


def list_users() -> list:
    return [
        {"username": u["username"], "display_name": u["display_name"],
         "created_at": u["created_at"]}
        for u in _load_users().values()
    ]


def change_display_name(username: str, new_name: str) -> bool:
    users = _load_users()
    if username not in users:
        return False
    users[username]["display_name"] = new_name
    _save_users(users)
    return True
