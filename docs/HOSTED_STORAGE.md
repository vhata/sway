# Hosted storage and identity contract

`HostedStore` and `IdentityService` provide hosted identity infrastructure. They do not enable a web listener or expose existing local saves. Local `SQLiteStore` retains its existing schema and semantics.

## Database and transactions

Hosted mode uses an explicitly selected, separate database. `HostedStore` creates new files with mode `0600`, marks them with SQLite application ID `0x53575948` and container format `user_version=1`, and rejects unmarked nonempty databases, including local saves. Existing database paths must be owner-only regular files; symlinks and permissive files are rejected without changing their permissions. Component schema versions live in `hosting_schema(component, version)`; identity starts at version 1. Multiplayer owns its own component row and tables in this same database. Unknown container/identity versions fail without rewriting records.

`HostedStore(path, clock=...)` accepts an injectable clock returning Unix seconds. `transaction(write=False)` opens a connection with `sqlite3.Row`, foreign keys enabled and an explicit transaction. Reads are query-only and retain one snapshot. Writes use `BEGIN IMMEDIATE`, wait at most five seconds for SQLite locks, and commit only after the entire context succeeds. Exceptions roll back; connections close on every path. Caller code must not use `executescript`, which implicitly commits transactions, or hold a transaction while bots compute or templates render.

Identity methods accepting `conn=` participate in the caller's transaction without committing it. An invitation claim can therefore create a principal, consume a session and bind membership in one write transaction. Session authorization must be rechecked within the transaction that commits a game mutation. Any future database adapter must preserve these semantics, including process-level races and rollback contracts.

## Credentials

Only explicit mutation handlers call `create_principal` or `recover`; an anonymous session alone does not create a principal. Anonymous sessions last 30 minutes. Authenticated sessions have a fixed 30-day lifetime with no sliding extension. Every session token and recovery code contains 256 random bits; only SHA-256 hashes are persisted. The browser receives raw credentials once. Credential dataclasses hide secrets from their representations; handlers must also keep credentials out of logs, URLs and exception messages.

`anonymous_session()` returns `SessionCredentials(token, session)`. `create_principal(anonymous_token, display_name, conn=None)` consumes that anonymous session and returns `IdentityCredentials(session, recovery_code)`. `recover(anonymous_token, recovery_code, conn=None)` restores the same principal, rotates the single-use recovery code, revokes every existing session for that principal and issues a new authenticated session atomically. Concurrent recovery attempts have one winner. Neither names nor public principal IDs authenticate a person.

`authenticate(token, conn=None)` returns `Session(session_id, principal_id, expires_at, csrf_token)` or raises `AuthenticationError` for invalid, expired or revoked tokens. `principal_id=None` identifies an anonymous session; callers must require a principal where appropriate. A session's CSRF token is an HMAC derived from its bearer token with a fixed domain separator, so it can be recovered for rendered forms without storing another raw secret. `check_csrf` authenticates and compares this token in constant time. A CSRF token cannot be used as a session token. The transport must additionally enforce exact origins, safe cookies, request limits and explicit POST mutations.

`revoke_session(token)` is idempotent. `revoke_all(token)` authenticates the requester and revokes all their sessions (or just that session for an anonymous requester). There is no recovery by display name or host intervention.

## Schema changes and recovery

There is no automatic migration from local to hosted data. Future identity schema upgrades require an explicit migration with a backup before any format change; do not relax format checks to open a newer database. Service component migrations follow the same rule. Backups must include the complete database, including identity, membership, snapshots and receipts. Use SQLite's backup API for a consistent copy; copying only the main file during live writes is insufficient. Restoring an older backup also restores that backup's credential and revocation state, so stop the application and handle the restored database as sensitive authentication material.

The identity tests cover cross-process single-use recovery, independent-connection races, consistent reads, caller rollback, expiry, revocation, reopen and local/unsupported-format preservation. Hosting deployment and whole-database backup/restore validation belong to the hosting operations work.
