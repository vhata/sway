"""The same domain/storage assertions run on SQLite and a real Durable Object.

This module is copied into the test Worker only; it is never a production route.
"""

import json
from dataclasses import asdict
from uuid import uuid4

from sway.bots import BotState, choose
from sway.hosting.identity import AuthenticationError, IdentityService
from sway.hosting.schema import initialize_identity
from sway.hosting.service import HostedService
from sway.storage import GameNotFound, StorageConflict


def expect(error, operation):
    try:
        operation()
    except error:
        return
    raise AssertionError(f"Expected {error.__name__}")


def run(store):
    store.write(initialize_identity)
    identity = IdentityService(store)
    service = HostedService(store)
    marker = str(uuid4())

    def rollback(sql):
        inserted = sql.execute("INSERT INTO principals VALUES (?, 'rollback', 0)", (marker,))
        assert inserted.rows_written == 1
        assert sql.execute("SELECT * FROM principals").rows_written == 0
        raise ValueError("rollback")

    expect(ValueError, lambda: store.write(rollback))
    assert (
        store.read(
            lambda sql: sql.execute(
                "SELECT * FROM principals WHERE principal_id=?", (marker,)
            ).one()
        )
        is None
    )

    # Both backends must enforce the schema's identity ownership references.
    try:
        store.write(
            lambda sql: sql.execute(
                "INSERT INTO sessions VALUES (?, ?, ?, 0, 1)", (marker, marker, marker)
            )
        )
    except Exception:
        pass
    else:
        raise AssertionError("Foreign key accepted a missing principal")
    assert (
        store.read(
            lambda sql: sql.execute("SELECT * FROM sessions WHERE session_id=?", (marker,)).one()
        )
        is None
    )

    def account(name):
        anonymous = identity.anonymous_session()
        credentials = identity.create_principal(anonymous.token, name)
        expect(AuthenticationError, lambda: identity.authenticate(anonymous.token))
        return credentials

    alice, bob, outsider = account("Alice"), account("Bob"), account("Outsider")
    table = service.create(alice.session.token, ("human", "human"))
    invite = service.invite(alice.session.token, table.game_id, 1)
    anonymous = identity.anonymous_session()
    before = store.read(lambda sql: sql.execute("SELECT COUNT(*) AS n FROM principals").one()["n"])
    expect(
        GameNotFound,
        lambda: service.join_guest(anonymous.token, invite.invitation_id, "wrong", "Uncommitted"),
    )
    assert (
        store.read(lambda sql: sql.execute("SELECT COUNT(*) AS n FROM principals").one()["n"])
        == before
    )
    assert identity.authenticate(anonymous.token).principal_id is None
    table = service.join(bob.session.token, invite.invitation_id, invite.secret)
    expect(
        GameNotFound,
        lambda: service.join(outsider.session.token, invite.invitation_id, invite.secret),
    )
    expect(GameNotFound, lambda: service.view(outsider.session.token, table.game_id))
    table = service.ready(alice.session.token, table.game_id, table.lobby_revision)
    table = service.ready(bob.session.token, table.game_id, table.lobby_revision)
    table = service.start(alice.session.token, table.game_id, table.lobby_revision)
    accounts = (alice, bob)
    actor = accounts[table.pending_player].session.token
    active = service.view(actor, table.game_id)
    assert active.view is not None and active.view.pending is not None
    other = service.view(accounts[1 - table.pending_player].session.token, table.game_id)
    assert other.view.pending is None
    assert "seed" not in json.dumps(asdict(other))
    command = choose(active.view, active.view.pending, BotState("engine", 1)).command
    first = service.submit(actor, table.game_id, "receipt", command)
    retry = service.submit(actor, table.game_id, "receipt", command)
    assert retry.table.revision == first.table.revision
    expect(StorageConflict, lambda: service.submit(actor, table.game_id, "different", command))

    recovered = identity.recover(identity.anonymous_session().token, alice.recovery_code)
    expect(AuthenticationError, lambda: identity.authenticate(alice.session.token))
    expect(
        AuthenticationError,
        lambda: identity.recover(identity.anonymous_session().token, alice.recovery_code),
    )
    assert service.view(recovered.session.token, table.game_id).seat == 0
    return [
        "SQL rollback",
        "session rotation",
        "guest rollback",
        "single-use invitations",
        "membership isolation",
        "hidden pending views",
        "duplicate receipts",
        "stale revisions",
        "single-use recovery",
    ]
