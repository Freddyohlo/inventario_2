"""Password hashing and signed-cookie sessions.

Deliberately dependency-light: PBKDF2-HMAC from the standard library for
passwords and itsdangerous for signing the session cookie. This is a demo-grade
auth layer, not an internet-facing one; see the README for what to change before
exposing it.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from typing import Any

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

PBKDF2_ITERATIONS = 200_000
SESSION_MAX_AGE = 60 * 60 * 12

ROLE_ADMIN = "admin"
ROLE_SELLER = "vendedor"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def create_user(conn: sqlite3.Connection, *, username: str, password: str, role: str) -> int:
    if role not in {ROLE_ADMIN, ROLE_SELLER}:
        raise ValueError("Rol invalido")
    cur = conn.execute(
        "INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)",
        (username.strip(), hash_password(password), role),
    )
    conn.commit()
    return int(cur.lastrowid)


def authenticate(conn: sqlite3.Connection, username: str, password: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username.strip(),)).fetchone()
    if row is None:
        return None
    if not verify_password(password, row["password_hash"]):
        return None
    return {"id": row["id"], "username": row["username"], "role": row["role"]}


class SessionManager:
    """Signs and reads the session payload placed in a cookie."""

    COOKIE = "inventario_session"

    def __init__(self, secret: str | None = None) -> None:
        self._serializer = URLSafeTimedSerializer(secret or os.environ.get("SECRET_KEY", "dev-insecure-key"))

    def sign(self, user: dict[str, Any]) -> str:
        return self._serializer.dumps({"uid": user["id"], "role": user["role"]})

    def read(self, token: str) -> dict[str, Any] | None:
        try:
            return self._serializer.loads(token, max_age=SESSION_MAX_AGE)
        except (BadSignature, SignatureExpired):
            return None
