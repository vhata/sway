"""Private synthetic recovery namespace. This Worker deliberately has no HTTP handler."""

import hashlib
import json
import re
from dataclasses import asdict

from recovery_runtime import Runtime
from workers import DurableObject, WorkerEntrypoint

from sway.bots import BotState, choose
from sway.engine import Command
from sway.hosting.identity import AuthenticationError
from sway.hosting.runtime import WebConfig

TABLES = (
    "hosting_schema",
    "principals",
    "sessions",
    "recovery_credentials",
    "hosted_rooms",
    "hosted_seats",
    "hosted_invitations",
    "hosted_preferences",
    "hosted_commands",
    "request_limits",
)


class RecoveryDrill(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.runtime = Runtime(ctx, WebConfig("https://recovery.invalid"))

    async def seed(self):
        identity, service = self.runtime.identity, self.runtime.service
        assert self.ctx.storage.sql.exec("SELECT COUNT(*) AS n FROM principals").one()["n"] == 0
        users = []
        for name in ("Synthetic host", "Synthetic guest"):
            anonymous = await self.runtime.execute(identity.anonymous_session)
            users.append(
                await self.runtime.execute(identity.create_principal, anonymous.token, name)
            )
        tokens = [user.session.token for user in users]
        table = await self.runtime.execute(service.create, tokens[0], ("human", "human"))
        invitation = await self.runtime.execute(service.invite, tokens[0], table.game_id, 1)
        table = await self.runtime.execute(
            service.join, tokens[1], invitation.invitation_id, invitation.secret
        )
        for token in tokens:
            table = await self.runtime.execute(
                service.ready, token, table.game_id, table.lobby_revision
            )
        table = await self.runtime.execute(
            service.start, tokens[0], table.game_id, table.lobby_revision
        )
        actor, command = self.decision(table.game_id, tokens)
        await self.runtime.execute(
            service.submit, tokens[actor], table.game_id, "baseline", command
        )
        self.ctx.storage.kv.put("marker", "baseline")
        return {
            "game_id": table.game_id,
            "tokens": tokens,
            "recovery": users[0].recovery_code,
            "actor": actor,
            "command": {**asdict(command), "selections": list(command.selections)},
        }

    def decision(self, game_id, tokens):
        service = self.runtime.service
        table = service.view(tokens[0], game_id)
        actor = table.pending_player
        active = service.view(tokens[actor], game_id)
        assert active.view is not None and active.view.pending is not None
        return actor, choose(
            active.view, active.view.pending, BotState("engine", active.revision)
        ).command

    async def mutate(self, proof):
        service, identity = self.runtime.service, self.runtime.identity
        actor, command = self.decision(proof["game_id"], proof["tokens"])
        await self.runtime.execute(
            service.submit, proof["tokens"][actor], proof["game_id"], "after-bookmark", command
        )
        anonymous = await self.runtime.execute(identity.anonymous_session)
        recovered = await self.runtime.execute(identity.recover, anonymous.token, proof["recovery"])
        await self.runtime.execute(service.cancel, recovered.session.token, proof["game_id"])
        self.ctx.storage.kv.put("marker", "changed")
        return recovered.session.token

    async def inspect(self, proof, new_token=""):
        def authenticated(token):
            try:
                self.runtime.identity.authenticate(token)
                return True
            except AuthenticationError:
                return False

        sql = self.ctx.storage.sql
        rows = {
            name: sql.exec(f'SELECT * FROM "{name}" ORDER BY rowid').toArray() for name in TABLES
        }
        digest = hashlib.sha256(
            json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        room = sql.exec(
            "SELECT revision,status FROM hosted_rooms WHERE game_id=?", proof["game_id"]
        ).one()
        receipts = sql.exec(
            "SELECT request_id FROM hosted_commands WHERE game_id=? ORDER BY revision",
            proof["game_id"],
        ).toArray()
        return {
            "digest": digest,
            "revision": room["revision"],
            "status": room["status"],
            "receipts": [row["request_id"] for row in receipts],
            "old_session_valid": authenticated(proof["tokens"][0]),
            "new_session_valid": authenticated(new_token),
            "marker": self.ctx.storage.kv.get("marker"),
        }

    async def bookmark(self):
        await self.ctx.storage.sync()
        return await self.ctx.storage.getCurrentBookmark()

    async def prepare_restore(self, bookmark):
        return await self.ctx.storage.onNextSessionRestoreBookmark(bookmark)

    async def restart(self):
        self.ctx.abort("Synthetic recovery drill restart")

    async def replay(self, proof):
        saved = proof["command"]
        command = Command(
            saved["decision_id"], saved["expected_revision"], tuple(saved["selections"])
        )
        result = await self.runtime.execute(
            self.runtime.service.submit,
            proof["tokens"][proof["actor"]],
            proof["game_id"],
            "baseline",
            command,
        )
        return result.accepted_revision


class Default(WorkerEntrypoint):
    def _object(self, run_id):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Expected a unique drill run identifier")
        return self.env.RECOVERY.getByName("synthetic-" + run_id)

    async def seed(self, run_id):
        return await self._object(run_id).seed()

    async def mutate(self, run_id, proof):
        return await self._object(run_id).mutate(proof)

    async def inspect(self, run_id, proof, new_token=""):
        return await self._object(run_id).inspect(proof, new_token)

    async def bookmark(self, run_id):
        return await self._object(run_id).bookmark()

    async def prepare_restore(self, run_id, bookmark):
        return await self._object(run_id).prepare_restore(bookmark)

    async def restart(self, run_id):
        return await self._object(run_id).restart()

    async def replay(self, run_id, proof):
        return await self._object(run_id).replay(proof)
