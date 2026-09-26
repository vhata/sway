"""Guest identity with opaque sessions and single-use rotating recovery codes."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import cast
from uuid import uuid4

from sway.hosting.state import SqlSession, StateStore

SESSION_SECONDS = 30 * 24 * 60 * 60
ANONYMOUS_SECONDS = 30 * 60


class AuthenticationError(Exception):
    """A credential is invalid, expired or revoked."""


@dataclass(frozen=True)
class Session:
    session_id: str
    principal_id: str | None
    expires_at: float
    csrf_token: str = field(repr=False)


@dataclass(frozen=True)
class SessionCredentials:
    token: str = field(repr=False)
    session: Session


@dataclass(frozen=True)
class IdentityCredentials:
    session: SessionCredentials
    recovery_code: str = field(repr=False)


def hash_secret(secret: str) -> str:
    """Hash a high-entropy credential before persistence."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def _csrf(token: str) -> str:
    return hmac.new(token.encode("utf-8"), b"sway-session-csrf-v1", hashlib.sha256).hexdigest()


class IdentityService:
    def __init__(self, store: StateStore) -> None:
        self.store = store

    def authenticate(self, token: str, *, conn: SqlSession | None = None) -> Session:
        if not token or len(token) > 128:
            raise AuthenticationError("Session is invalid or expired.")

        def _read(connection: SqlSession) -> Session:
            row = connection.execute(
                "SELECT session_id, principal_id, expires_at FROM sessions WHERE token_hash = ?",
                (hash_secret(token),),
            ).one()
            if row is None or cast(float, row["expires_at"]) <= self.store.clock():
                raise AuthenticationError("Session is invalid or expired.")
            return Session(
                cast(str, row["session_id"]),
                cast(str | None, row["principal_id"]),
                cast(float, row["expires_at"]),
                _csrf(token),
            )

        return _read(conn) if conn is not None else self.store.read(_read)

    def check_csrf(self, token: str, csrf: str, *, conn: SqlSession | None = None) -> Session:
        session = self.authenticate(token, conn=conn)
        if not hmac.compare_digest(session.csrf_token.encode("utf-8"), csrf.encode("utf-8")):
            raise AuthenticationError("Invalid CSRF token.")
        return session

    def anonymous_session(self) -> SessionCredentials:
        def _write(conn: SqlSession) -> SessionCredentials:
            return self._issue(conn, None)

        return self.store.write(_write)

    def create_principal(
        self,
        anonymous_token: str,
        display_name: str,
        *,
        conn: SqlSession | None = None,
    ) -> IdentityCredentials:
        name = display_name.strip()
        if not name or len(name) > 80 or any(ord(char) < 32 for char in name):
            raise ValueError("Display name must contain 1 to 80 printable characters.")

        def _write(connection: SqlSession) -> IdentityCredentials:
            anonymous = self._anonymous(connection, anonymous_token)
            principal_id = uuid4().hex
            connection.execute(
                "INSERT INTO principals VALUES (?, ?, ?)",
                (principal_id, name, self.store.clock()),
            )
            connection.execute("DELETE FROM sessions WHERE session_id = ?", (anonymous.session_id,))
            return self._credentials(connection, principal_id)

        return _write(conn) if conn is not None else self.store.write(_write)

    def recover(
        self,
        anonymous_token: str,
        recovery_code: str,
        *,
        conn: SqlSession | None = None,
    ) -> IdentityCredentials:
        def _write(connection: SqlSession) -> IdentityCredentials:
            anonymous = self._anonymous(connection, anonymous_token)
            if not recovery_code or len(recovery_code) > 128:
                raise AuthenticationError("Recovery code is invalid.")
            row = connection.execute(
                "SELECT principal_id FROM recovery_credentials WHERE code_hash = ?",
                (hash_secret(recovery_code),),
            ).one()
            if row is None:
                raise AuthenticationError("Recovery code is invalid.")
            principal_id = cast(str, row["principal_id"])
            connection.execute("DELETE FROM sessions WHERE principal_id = ?", (principal_id,))
            connection.execute("DELETE FROM sessions WHERE session_id = ?", (anonymous.session_id,))
            return self._credentials(connection, principal_id)

        return _write(conn) if conn is not None else self.store.write(_write)

    def revoke_session(self, token: str) -> None:
        def _write(conn: SqlSession) -> None:
            conn.execute("DELETE FROM sessions WHERE token_hash = ?", (hash_secret(token),))

        self.store.write(_write)

    def revoke_all(self, token: str) -> None:
        def _write(conn: SqlSession) -> None:
            session = self.authenticate(token, conn=conn)
            if session.principal_id is None:
                conn.execute("DELETE FROM sessions WHERE session_id = ?", (session.session_id,))
            else:
                conn.execute("DELETE FROM sessions WHERE principal_id = ?", (session.principal_id,))

        self.store.write(_write)

    def _anonymous(self, conn: SqlSession, token: str) -> Session:
        session = self.authenticate(token, conn=conn)
        if session.principal_id is not None:
            raise AuthenticationError("A fresh anonymous session is required.")
        return session

    def _credentials(self, conn: SqlSession, principal_id: str) -> IdentityCredentials:
        recovery_code = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO recovery_credentials VALUES (?, ?) "
            "ON CONFLICT(principal_id) DO UPDATE SET code_hash = excluded.code_hash",
            (principal_id, hash_secret(recovery_code)),
        )
        return IdentityCredentials(self._issue(conn, principal_id), recovery_code)

    def _issue(self, conn: SqlSession, principal_id: str | None) -> SessionCredentials:
        token = secrets.token_urlsafe(32)
        now = self.store.clock()
        session = Session(
            uuid4().hex,
            principal_id,
            now + (ANONYMOUS_SECONDS if principal_id is None else SESSION_SECONDS),
            _csrf(token),
        )
        conn.execute(
            "INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
            (session.session_id, hash_secret(token), principal_id, now, session.expires_at),
        )
        return SessionCredentials(token, session)
