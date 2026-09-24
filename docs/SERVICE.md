# Game service and human seats

`GameService` supports explicit human controllers as a backend building block. The local browser still supports one human at seat 0 against bots. This API does not provide remote identity, invitations or multiplayer HTTP routes.

## Trusted caller contract

```python
record = service.create(
    GameConfig(player_count=4),
    seed=42,
    strategies=("engine", "attack"),
    human_seats=frozenset({1, 3}),
)
view = service.view(record.game_id, player=3)
record = service.submit(record.game_id, command, player=3)
```

The caller supplies `player` from trusted application context. A remote boundary must authenticate membership before selecting that index; never copy a player field from an HTTP request. `view` and `submit` reject bot seats and invalid indices, but do not authenticate a person. `load`, listing, bot advancement and theme changes likewise require caller authorization before any future public exposure.

`human_seats` is a nonempty `frozenset` of integer indices in the game, excluding booleans. It defaults to `{0}`. Every other seat is a bot, with exactly one strategy assigned in ascending seat order. All-human two-, three- and four-player games use an empty strategy tuple. Controller assignments are fixed for the saved game.

`record.human_seats` identifies the human controllers. `record.bot_seats` gives the player index for each corresponding entry in `record.bots` and `record.strategies`. These pairs remain stable even when bots occupy seat 0 or noncontiguous seats. Bot seeds depend on the actual seat index; the default layout retains its original seeds.

Only the human who owns `state.pending.player` can submit that decision. It may be a reaction during another player's turn. Views contain only that viewer's allowed information and pending choice. `advance_bots` commits a bounded number of decisions and stops at any human-owned pending choice; it cannot answer for a human. Bot computation uses its own persisted state and filtered view.

Commands keep the existing decision ID and expected revision. Stale or competing submissions fail without overwriting the saved state, and a repeated human submission may return a revision conflict after the first succeeds. Each accepted transition atomically stores the new snapshot, attributed engine events and command using the existing storage contract. No principal-level command receipts or authentication are implied.

## Save envelope

The engine's snapshot format and SQL schema are unchanged. Application snapshot schema 2 contains:

- `engine`: the existing serialized engine JSON string;
- `human_seats`: a sorted list of human player indices;
- `bots`: an object whose canonical decimal seat keys map to the existing versioned `BotState` fields.

Bot keys must exactly cover the remaining seats. Invalid assignments, duplicate human indices, invalid bot profiles/versions and inconsistent engine revisions reject the save without rewriting it. New game metadata also records `human_seats`; metadata is advisory and is never the source of controller authorization.

Original application schema-1 saves load as human seat 0 with positional bots in seats 1 onward. Loading preserves their snapshot bytes, engine state, random state and bot memory. The next accepted gameplay transition writes schema 2 atomically; read-only access and a theme-only update do not rewrite the envelope. Legacy summary metadata remains valid after this upgrade.

## Local browser boundary

The existing local routes create only the default arrangement. A valid save with any other human arrangement receives a clear unsupported-table response before rendering or accepting a decision, bot advance or theme mutation. Its snapshot, revision and theme remain unchanged. The browser exposes no player-index input and does not simulate waiting for another human through its bot-progress loop.

The separate [HostedService and application](MULTIPLAYER.md) implement identity, private memberships, reconnect credentials, invitations and per-viewer preferences using an isolated hosted database. They reuse the engine and application snapshot format; they do not expose this trusted local API or make the local server safe to publish.
