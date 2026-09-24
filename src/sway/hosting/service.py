"""Authenticated rooms, private views, and durable multiplayer transitions."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import sqlite3
import time
from dataclasses import asdict, dataclass
from typing import cast
from uuid import uuid4

from sway.bots import STRATEGIES, BotState, choose
from sway.engine import Command, GameConfig, InvalidCommand, PlayerView, advance, new_game, view_for
from sway.hosting.identity import IdentityService
from sway.hosting.storage import HostedStore
from sway.service import deserialize_game, serialize_game
from sway.storage import GameNotFound, StorageConflict, StoredGame


@dataclass(frozen=True)
class SeatView:
    seat: int
    controller: str
    display_name: str
    occupied: bool
    ready: bool


@dataclass(frozen=True)
class TableView:
    game_id: str
    host: bool
    seat: int
    status: str
    lobby_revision: int
    revision: int
    preference_version: int
    theme_id: str
    seats: tuple[SeatView, ...]
    kingdom: tuple[str, ...]
    view: PlayerView | None
    pending_player: int | None
    bot_paused: str | None


@dataclass(frozen=True)
class Invitation:
    invitation_id: str
    secret: str
    expires_at: float


@dataclass(frozen=True)
class CommandResult:
    accepted_revision: int
    table: TableView


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def _row(conn: sqlite3.Connection, sql: str, parameters: tuple[object, ...]) -> sqlite3.Row:
    row = cast(sqlite3.Row | None, conn.execute(sql, parameters).fetchone())
    if row is None:
        raise GameNotFound("Table unavailable.")
    return row


def _rows(conn: sqlite3.Connection, sql: str, parameters: tuple[object, ...]) -> list[sqlite3.Row]:
    return cast(list[sqlite3.Row], conn.execute(sql, parameters).fetchall())


def _text(row: sqlite3.Row, key: str) -> str:
    return cast(str, row[key])


def _int(row: sqlite3.Row, key: str) -> int:
    return cast(int, row[key])


class HostedService:
    """Short read/write transactions surround computation, never bot thinking."""

    def __init__(self, store: HostedStore) -> None:
        self.store = store
        self.identity = IdentityService(store)
        statements = (
            """CREATE TABLE IF NOT EXISTS hosted_rooms (
                game_id TEXT PRIMARY KEY, host_id TEXT NOT NULL REFERENCES principals(principal_id),
                status TEXT NOT NULL, lobby_revision INTEGER NOT NULL, revision INTEGER NOT NULL,
                kingdom TEXT NOT NULL, snapshot TEXT, updated_at TEXT NOT NULL,
                bot_paused TEXT)""",
            """CREATE TABLE IF NOT EXISTS hosted_seats (
                game_id TEXT NOT NULL REFERENCES hosted_rooms(game_id), seat INTEGER NOT NULL,
                controller TEXT NOT NULL, principal_id TEXT REFERENCES principals(principal_id),
                ready_revision INTEGER, PRIMARY KEY(game_id,seat), UNIQUE(game_id,principal_id))""",
            """CREATE TABLE IF NOT EXISTS hosted_invitations (
                invitation_id TEXT PRIMARY KEY, game_id TEXT NOT NULL, seat INTEGER NOT NULL,
                secret_hash TEXT NOT NULL, expires_at REAL NOT NULL, revoked INTEGER NOT NULL,
                claimed_by TEXT REFERENCES principals(principal_id),
                FOREIGN KEY(game_id,seat) REFERENCES hosted_seats(game_id,seat))""",
            """CREATE TABLE IF NOT EXISTS hosted_preferences (
                game_id TEXT NOT NULL REFERENCES hosted_rooms(game_id),
                principal_id TEXT NOT NULL REFERENCES principals(principal_id),
                theme_id TEXT NOT NULL, version INTEGER NOT NULL, PRIMARY KEY(game_id,principal_id))""",
            """CREATE TABLE IF NOT EXISTS hosted_commands (
                game_id TEXT NOT NULL REFERENCES hosted_rooms(game_id), revision INTEGER NOT NULL,
                actor TEXT NOT NULL, request_id TEXT NOT NULL, payload TEXT NOT NULL,
                events TEXT NOT NULL, PRIMARY KEY(game_id,revision), UNIQUE(game_id,actor,request_id))""",
        )
        with store.transaction(write=True) as conn:
            for statement in statements:
                conn.execute(statement)

    def _principal(self, conn: sqlite3.Connection, token: str) -> str:
        principal = self.identity.authenticate(token, conn=conn).principal_id
        if principal is None:
            raise GameNotFound("Sign in before opening a table.")
        return principal

    def _member(self, conn: sqlite3.Connection, token: str, game_id: str) -> tuple[str, sqlite3.Row, sqlite3.Row]:
        principal = self._principal(conn, token)
        seat = _row(conn, "SELECT * FROM hosted_seats WHERE game_id=? AND principal_id=?", (game_id, principal))
        room = _row(conn, "SELECT * FROM hosted_rooms WHERE game_id=?", (game_id,))
        return principal, room, seat

    @staticmethod
    def _host(principal: str, room: sqlite3.Row) -> None:
        if principal != _text(room, "host_id"):
            raise GameNotFound("Table unavailable.")

    @staticmethod
    def _lobby(room: sqlite3.Row, revision: int) -> None:
        if _text(room, "status") != "lobby" or _int(room, "lobby_revision") != revision:
            raise StorageConflict("The lobby changed. Reload before continuing.")

    @staticmethod
    def _bump(conn: sqlite3.Connection, game_id: str) -> None:
        conn.execute("UPDATE hosted_rooms SET lobby_revision=lobby_revision+1 WHERE game_id=?", (game_id,))

    @staticmethod
    def _validate(controllers: tuple[str, ...], kingdom: tuple[str, ...]) -> None:
        if not 2 <= len(controllers) <= 4 or controllers[0] != "human":
            raise ValueError("Choose two to four seats, with a human host in seat one.")
        if any(controller != "human" and controller not in STRATEGIES for controller in controllers):
            raise ValueError("Unknown controller.")
        # Rules validation is the authoritative supply contract; randomness here is disposable.
        new_game(GameConfig(len(controllers), kingdom), 0)

    def create(self, token: str, controllers: tuple[str, ...], kingdom: tuple[str, ...] = GameConfig().kingdom) -> TableView:
        self._validate(controllers, kingdom)
        game_id = uuid4().hex
        with self.store.transaction(write=True) as conn:
            principal = self._principal(conn, token)
            conn.execute("INSERT INTO hosted_rooms VALUES (?,?, 'lobby',0,0,?,NULL,?,NULL)", (game_id, principal, _json(kingdom), str(time.time())))
            for seat, controller in enumerate(controllers):
                conn.execute("INSERT INTO hosted_seats VALUES (?,?,?,?,NULL)", (game_id, seat, controller, principal if seat == 0 else None))
        return self.view(token, game_id)

    @staticmethod
    def _record(room: sqlite3.Row):
        return deserialize_game(StoredGame(_text(room,"game_id"), _int(room,"revision"), _text(room,"snapshot"), "{}", "common-ground", _text(room,"status"), _text(room,"updated_at")))

    def _view(self, conn: sqlite3.Connection, principal: str, room: sqlite3.Row, own: sqlite3.Row) -> TableView:
        game_id = _text(room,"game_id")
        seats = _rows(conn, "SELECT s.*,p.display_name FROM hosted_seats s LEFT JOIN principals p ON p.principal_id=s.principal_id WHERE game_id=? ORDER BY seat", (game_id,))
        preference = cast(sqlite3.Row | None, conn.execute("SELECT * FROM hosted_preferences WHERE game_id=? AND principal_id=?", (game_id,principal)).fetchone())
        record = self._record(room) if room["snapshot"] is not None else None
        return TableView(
            game_id, principal == _text(room,"host_id"), _int(own,"seat"), _text(room,"status"),
            _int(room,"lobby_revision"), _int(room,"revision"),
            _int(preference,"version") if preference else 0,
            _text(preference,"theme_id") if preference else "common-ground",
            tuple(SeatView(_int(seat,"seat"),_text(seat,"controller"),cast(str,seat["display_name"]) if seat["display_name"] is not None else ("Open seat" if seat["controller"] == "human" else f"Bot {_int(seat,'seat')+1}"), seat["principal_id"] is not None or seat["controller"] != "human", seat["ready_revision"] == room["lobby_revision"]) for seat in seats),
            tuple(cast(list[str],json.loads(_text(room,"kingdom")))),
            view_for(record.state,_int(own,"seat")) if record else None,
            record.state.pending.player if record and record.state.pending else None,
            cast(str | None,room["bot_paused"]),
        )

    def view(self, token: str, game_id: str) -> TableView:
        with self.store.transaction() as conn:
            principal, room, seat = self._member(conn,token,game_id)
            return self._view(conn,principal,room,seat)

    def list_tables(self, token: str) -> tuple[TableView, ...]:
        with self.store.transaction() as conn:
            principal = self._principal(conn,token)
            seats = _rows(conn,"SELECT * FROM hosted_seats WHERE principal_id=? ORDER BY game_id",(principal,))
            return tuple(self._view(conn,principal,_row(conn,"SELECT * FROM hosted_rooms WHERE game_id=?",(_text(seat,"game_id"),)),seat) for seat in seats)

    def invite(self, token: str, game_id: str, seat: int) -> Invitation:
        invitation = Invitation(uuid4().hex,secrets.token_urlsafe(32),time.time()+86400)
        with self.store.transaction(write=True) as conn:
            principal,room,_ = self._member(conn,token,game_id)
            self._host(principal,room)
            self._lobby(room,_int(room,"lobby_revision"))
            target = _row(conn,"SELECT * FROM hosted_seats WHERE game_id=? AND seat=?",(game_id,seat))
            if target["controller"] != "human" or target["principal_id"] is not None:
                raise StorageConflict("That seat is unavailable.")
            conn.execute("UPDATE hosted_invitations SET revoked=1 WHERE game_id=? AND seat=?",(game_id,seat))
            conn.execute("INSERT INTO hosted_invitations VALUES (?,?,?,?,?,0,NULL)",(invitation.invitation_id,game_id,seat,_digest(invitation.secret),invitation.expires_at))
        return invitation

    def revoke_invite(self, token: str, game_id: str, seat: int) -> None:
        with self.store.transaction(write=True) as conn:
            principal,room,_ = self._member(conn,token,game_id)
            self._host(principal,room)
            self._lobby(room,_int(room,"lobby_revision"))
            conn.execute("UPDATE hosted_invitations SET revoked=1 WHERE game_id=? AND seat=?",(game_id,seat))

    def join(self, token: str, invitation_id: str, secret: str) -> TableView:
        with self.store.transaction(write=True) as conn:
            principal = self._principal(conn,token)
            invite = _row(conn,"SELECT * FROM hosted_invitations WHERE invitation_id=?",(invitation_id,))
            if not secrets.compare_digest(_text(invite,"secret_hash"),_digest(secret)):
                raise GameNotFound("Invitation unavailable.")
            game_id = _text(invite,"game_id")
            if invite["claimed_by"] == principal:
                self._member(conn,token,game_id)
            else:
                room = _row(conn,"SELECT * FROM hosted_rooms WHERE game_id=?",(game_id,))
                if invite["revoked"] or cast(float,invite["expires_at"]) <= time.time() or invite["claimed_by"] is not None or room["status"] != "lobby":
                    raise GameNotFound("Invitation unavailable.")
                existing = conn.execute("SELECT 1 FROM hosted_seats WHERE game_id=? AND principal_id=?",(game_id,principal)).fetchone()
                if existing:
                    raise StorageConflict("You already occupy a seat at this table.")
                changed = conn.execute("UPDATE hosted_seats SET principal_id=? WHERE game_id=? AND seat=? AND principal_id IS NULL AND controller='human'",(principal,game_id,_int(invite,"seat")))
                if changed.rowcount != 1:
                    raise GameNotFound("Invitation unavailable.")
                conn.execute("UPDATE hosted_invitations SET claimed_by=? WHERE invitation_id=?",(principal,invitation_id))
                self._bump(conn,game_id)
        return self.view(token,game_id)

    def ready(self, token: str, game_id: str, expected_lobby_revision: int, ready: bool = True) -> TableView:
        with self.store.transaction(write=True) as conn:
            principal,room,_ = self._member(conn,token,game_id)
            self._lobby(room,expected_lobby_revision)
            conn.execute("UPDATE hosted_seats SET ready_revision=? WHERE game_id=? AND principal_id=?",(expected_lobby_revision if ready else None,game_id,principal))
        return self.view(token,game_id)

    def configure(self, token: str, game_id: str, expected_lobby_revision: int, controllers: tuple[str,...], kingdom: tuple[str,...]) -> TableView:
        self._validate(controllers,kingdom)
        with self.store.transaction(write=True) as conn:
            principal,room,_ = self._member(conn,token,game_id)
            self._host(principal,room)
            self._lobby(room,expected_lobby_revision)
            seats = _rows(conn,"SELECT * FROM hosted_seats WHERE game_id=? ORDER BY seat",(game_id,))
            for seat in seats:
                index = _int(seat,"seat")
                if seat["principal_id"] is not None and (index >= len(controllers) or controllers[index] != "human"):
                    raise StorageConflict("Remove the member before changing their seat.")
            conn.execute("DELETE FROM hosted_invitations WHERE game_id=?",(game_id,))
            conn.execute("DELETE FROM hosted_seats WHERE game_id=? AND seat>=?",(game_id,len(controllers)))
            for index,controller in enumerate(controllers):
                conn.execute("INSERT INTO hosted_seats VALUES (?,?,?,NULL,NULL) ON CONFLICT(game_id,seat) DO UPDATE SET controller=excluded.controller",(game_id,index,controller))
            conn.execute("UPDATE hosted_rooms SET kingdom=? WHERE game_id=?",(_json(kingdom),game_id))
            self._bump(conn,game_id)
        return self.view(token,game_id)

    def remove(self, token: str, game_id: str, seat: int, expected_lobby_revision: int) -> TableView:
        with self.store.transaction(write=True) as conn:
            principal,room,_ = self._member(conn,token,game_id)
            self._host(principal,room)
            self._lobby(room,expected_lobby_revision)
            if seat == 0:
                raise ValueError("The host cannot leave their seat.")
            target = _row(conn,"SELECT * FROM hosted_seats WHERE game_id=? AND seat=?",(game_id,seat))
            conn.execute("DELETE FROM hosted_preferences WHERE game_id=? AND principal_id=?",(game_id,cast(str | None,target["principal_id"])))
            conn.execute("UPDATE hosted_seats SET principal_id=NULL,ready_revision=NULL WHERE game_id=? AND seat=?",(game_id,seat))
            conn.execute("UPDATE hosted_invitations SET revoked=1,claimed_by=NULL WHERE game_id=? AND seat=?",(game_id,seat))
            self._bump(conn,game_id)
        return self.view(token,game_id)

    def start(self, token: str, game_id: str, expected_lobby_revision: int) -> TableView:
        with self.store.transaction() as conn:
            principal,room,_ = self._member(conn,token,game_id)
            self._host(principal,room)
            self._lobby(room,expected_lobby_revision)
            seats = _rows(conn,"SELECT s.*,p.display_name FROM hosted_seats s LEFT JOIN principals p ON s.principal_id=p.principal_id WHERE game_id=? ORDER BY seat",(game_id,))
            if any(seat["controller"] == "human" and (seat["principal_id"] is None or seat["ready_revision"] != expected_lobby_revision) for seat in seats):
                raise StorageConflict("Every human must join and ready this lobby.")
        humans = frozenset(_int(seat,"seat") for seat in seats if seat["controller"] == "human")
        names = tuple(cast(str,seat["display_name"]) if seat["display_name"] is not None else f"Bot {_int(seat,'seat')+1}" for seat in seats)
        seed = secrets.randbits(64)
        state = new_game(GameConfig(len(seats),tuple(cast(list[str],json.loads(_text(room,"kingdom")))),names),seed)
        bots = tuple(BotState(_text(seat,"controller"),seed ^ (_int(seat,"seat") * 0x9E3779B97F4A7C15)) for seat in seats if seat["controller"] != "human")
        snapshot = serialize_game(state,bots,humans)
        with self.store.transaction(write=True) as conn:
            principal,current,_ = self._member(conn,token,game_id)
            self._host(principal,current)
            self._lobby(current,expected_lobby_revision)
            unready = conn.execute("SELECT 1 FROM hosted_seats WHERE game_id=? AND controller='human' AND (principal_id IS NULL OR ready_revision IS NULL OR ready_revision!=?)",(game_id,expected_lobby_revision)).fetchone()
            if unready:
                raise StorageConflict("Every human must ready this lobby.")
            conn.execute("UPDATE hosted_rooms SET status='active',snapshot=?,lobby_revision=lobby_revision+1 WHERE game_id=?",(snapshot,game_id))
            conn.execute("UPDATE hosted_invitations SET revoked=1 WHERE game_id=?",(game_id,))
        return self.view(token,game_id)

    def cancel(self, token: str, game_id: str) -> TableView:
        with self.store.transaction(write=True) as conn:
            principal,room,_ = self._member(conn,token,game_id)
            self._host(principal,room)
            if room["status"] not in ("lobby","active","cancelled"):
                raise StorageConflict("A finished table cannot be cancelled.")
            if room["status"] != "cancelled":
                conn.execute("UPDATE hosted_rooms SET status='cancelled',lobby_revision=lobby_revision+1 WHERE game_id=?",(game_id,))
        return self.view(token,game_id)

    @staticmethod
    def _receipt(conn: sqlite3.Connection, game_id: str, principal: str, request_id: str, payload: str) -> int | None:
        receipt = cast(sqlite3.Row | None,conn.execute("SELECT payload,revision FROM hosted_commands WHERE game_id=? AND actor=? AND request_id=?",(game_id,principal,request_id)).fetchone())
        if receipt is None:
            return None
        if _text(receipt,"payload") != payload:
            raise StorageConflict("Request identifier reused for a different choice.")
        return _int(receipt,"revision")

    @staticmethod
    def _commit(conn: sqlite3.Connection, room: sqlite3.Row, expected_revision: int, actor: str, request_id: str, payload: str, snapshot: str, events: str, finished: bool) -> int:
        if room["status"] != "active" or _int(room,"revision") != expected_revision:
            raise StorageConflict("The table changed. Reload before continuing.")
        revision = expected_revision+1
        game_id = _text(room,"game_id")
        conn.execute("INSERT INTO hosted_commands VALUES (?,?,?,?,?,?)",(game_id,revision,actor,request_id,payload,events))
        conn.execute("UPDATE hosted_rooms SET revision=?,snapshot=?,status=?,updated_at=? WHERE game_id=?",(revision,snapshot,"finished" if finished else "active",str(time.time()),game_id))
        return revision

    def submit(self, token: str, game_id: str, request_id: str, command: Command) -> CommandResult:
        if re.fullmatch(r"[A-Za-z0-9_-]{1,128}",request_id) is None:
            raise ValueError("Invalid request identifier.")
        payload = _json(asdict(command))
        with self.store.transaction() as conn:
            principal,room,seat = self._member(conn,token,game_id)
            receipt = self._receipt(conn,game_id,principal,request_id,payload)
            if receipt is not None:
                return CommandResult(receipt,self._view(conn,principal,room,seat))
            if room["status"] != "active" or _int(room,"revision") != command.expected_revision:
                raise StorageConflict("The table changed. Reload before continuing.")
            record = self._record(room)
            if record.state.pending is None or record.state.pending.player != _int(seat,"seat"):
                raise InvalidCommand("It is not your decision.")
        transition = advance(record.state,command)
        snapshot = serialize_game(transition.state,record.bots,record.human_seats)
        with self.store.transaction(write=True) as conn:
            principal,current,own = self._member(conn,token,game_id)
            receipt = self._receipt(conn,game_id,principal,request_id,payload)
            if receipt is None:
                if _int(own,"seat") != _int(seat,"seat"):
                    raise StorageConflict("Seat membership changed.")
                receipt = self._commit(conn,current,command.expected_revision,principal,request_id,payload,snapshot,_json([asdict(event) for event in transition.events]),transition.state.phase == "finished")
        return CommandResult(receipt,self.view(token,game_id))

    def set_theme(self, token: str, game_id: str, theme_id: str, expected_version: int) -> TableView:
        if re.fullmatch(r"[a-z][a-z0-9_-]{0,63}",theme_id) is None:
            raise ValueError("Invalid theme identifier.")
        with self.store.transaction(write=True) as conn:
            principal,_,_ = self._member(conn,token,game_id)
            previous = cast(sqlite3.Row | None,conn.execute("SELECT version FROM hosted_preferences WHERE game_id=? AND principal_id=?",(game_id,principal)).fetchone())
            if (0 if previous is None else _int(previous,"version")) != expected_version:
                raise StorageConflict("Your theme preference changed.")
            conn.execute("INSERT INTO hosted_preferences VALUES (?,?,?,?) ON CONFLICT(game_id,principal_id) DO UPDATE SET theme_id=excluded.theme_id,version=excluded.version",(game_id,principal,theme_id,expected_version+1))
        return self.view(token,game_id)

    def retry_bots(self, token: str, game_id: str) -> TableView:
        with self.store.transaction(write=True) as conn:
            _,room,_ = self._member(conn,token,game_id)
            if room["status"] != "active":
                raise StorageConflict("This table is not active.")
            conn.execute("UPDATE hosted_rooms SET bot_paused=NULL,lobby_revision=lobby_revision+1 WHERE game_id=?",(game_id,))
        return self.view(token,game_id)

    def pending_bot_games(self, limit: int = 100) -> tuple[str,...]:
        if not 1 <= limit <= 1000:
            raise ValueError("Invalid scan limit.")
        with self.store.transaction() as conn:
            # Cursor-free bounded scans prioritize oldest progress, avoiding a busy first page.
            rooms = _rows(conn,"SELECT * FROM hosted_rooms WHERE status='active' AND bot_paused IS NULL ORDER BY updated_at LIMIT ?",(limit,))
            return tuple(_text(room,"game_id") for room in rooms if self._bot_pending(room))

    def _bot_pending(self, room: sqlite3.Row) -> bool:
        record = self._record(room)
        return bool(record.state.pending and record.state.pending.player not in record.human_seats)

    def step_bots(self, game_id: str, max_steps: int = 8, budget_seconds: float = .1) -> bool:
        if not 1 <= max_steps <= 8 or not 0 < budget_seconds <= .1:
            raise ValueError("Bot jobs allow at most eight decisions and 100ms.")
        deadline = time.monotonic()+budget_seconds
        for _ in range(max_steps):
            with self.store.transaction() as conn:
                room = _row(conn,"SELECT * FROM hosted_rooms WHERE game_id=?",(game_id,))
                if room["status"] != "active" or room["bot_paused"] is not None or not self._bot_pending(room):
                    return False
                record = self._record(room)
            decision = record.state.pending
            assert decision is not None
            index = record.bot_seats.index(decision.player)
            try:
                choice = choose(view_for(record.state,decision.player),decision,record.bots[index])
                transition = advance(record.state,choice.command)
                bots = list(record.bots)
                bots[index] = choice.state
                snapshot = serialize_game(transition.state,tuple(bots),record.human_seats)
            except Exception:
                with self.store.transaction(write=True) as conn:
                    conn.execute("UPDATE hosted_rooms SET bot_paused='decision_failed',lobby_revision=lobby_revision+1 WHERE game_id=? AND status='active' AND revision=?",(game_id,record.revision))
                return False
            with self.store.transaction(write=True) as conn:
                current = _row(conn,"SELECT * FROM hosted_rooms WHERE game_id=?",(game_id,))
                if current["status"] != "active" or current["bot_paused"] is not None:
                    return False
                if _int(current,"revision") != record.revision:
                    return True
                self._commit(conn,current,record.revision,f"bot:{decision.player}",decision.id,_json(asdict(choice.command)),snapshot,_json([asdict(event) for event in transition.events]),transition.state.phase == "finished")
            if time.monotonic() >= deadline:
                break
        with self.store.transaction() as conn:
            room = _row(conn,"SELECT * FROM hosted_rooms WHERE game_id=?",(game_id,))
            return room["status"] == "active" and room["bot_paused"] is None and self._bot_pending(room)
