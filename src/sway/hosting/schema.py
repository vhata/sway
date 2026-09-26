"""Versioned hosted records common to every persistence implementation."""

from sway.hosting.state import SqlSession
from sway.storage import SaveFormatError


def initialize_identity(session: SqlSession) -> None:
    session.execute(
        "CREATE TABLE IF NOT EXISTS hosting_schema (component TEXT PRIMARY KEY, version INTEGER NOT NULL)"
    )
    row = session.execute("SELECT version FROM hosting_schema WHERE component='identity'").one()
    if row is not None:
        if row["version"] != 1:
            raise SaveFormatError("Unsupported hosted identity schema version.")
        return
    for statement in _IDENTITY_SCHEMA:
        session.execute(statement)


_IDENTITY_SCHEMA = (
    "INSERT INTO hosting_schema VALUES ('identity', 1)",
    """CREATE TABLE principals (
        principal_id TEXT PRIMARY KEY,
        display_name TEXT NOT NULL,
        created_at REAL NOT NULL
    )""",
    """CREATE TABLE sessions (
        session_id TEXT PRIMARY KEY,
        token_hash TEXT NOT NULL UNIQUE,
        principal_id TEXT REFERENCES principals(principal_id),
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL
    )""",
    "CREATE INDEX sessions_principal ON sessions(principal_id)",
    """CREATE TABLE recovery_credentials (
        principal_id TEXT PRIMARY KEY REFERENCES principals(principal_id),
        code_hash TEXT NOT NULL UNIQUE
    )""",
)
