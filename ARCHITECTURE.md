# Architecture contracts

These boundaries guide implementation. [SPEC.md](SPEC.md) records the accepted local release; [the multiplayer contract](docs/MULTIPLAYER.md) covers the separate hosted extension, and [TODO.md](TODO.md) tracks remaining work. Implementation PRs establish the concrete typed interfaces.

## Rules and decisions

The engine owns authoritative state and all rules, independently of HTTP, HTML, databases and names. Card definition IDs are stable; every physical card instance has its own ID and exactly one zone. Include temporary revealed and set-aside zones in conservation checks.

The public operations are `new_game(config, seed)`, `advance(state, command)` and `view_for(state, player)`. A transition returns new state and structured events. Decisions name their owner, kind, options, selection limits and ordering constraints. Commands carry the decision ID and expected revision. Validate every command before accepting a transition; the browser is not an authority.

Effects use a serializable stack that can pause at nested choices and opponents' reactions. Do not encode continuation state in generators, closures or HTTP sessions. Explicit game and bot random streams keep replay independent of rendering and strategy implementation details.

Bots receive the same filtered view and decision as a human, plus their own persisted versioned memory and random source. Strategies express preferences over available legal choices. They do not inspect authoritative opponents' hands, hidden deck order or the gameplay random stream.

## Presentation and privacy

Use typed htpy functions accepting presentation data from a filtered player view. Rules, costs and effects never depend on visible text. Local play uses HTMX to submit decisions and request fragments; hosted play serializes polling and submissions through its fetch coordinator. Small JavaScript components maintain selection/order locally, preserve focus on refresh and reset when the decision ID changes.

Filter structured events as well as state: discarded/revealed public cards and hidden draws have different visibility. Never send authoritative snapshots to templates or clients. Render pending choices only for their owner. The future API can expose the same player views and decisions without changing rules or bots.

Bot progress is bounded per server step; stop for a human reaction. Failures are recoverable and visible. A stale browser re-renders current state after a rejected revision; it never overwrites it.

Theme packs contain versioned data for stable IDs: names, independently written descriptions, terminology, accessibility labels, local asset references and design tokens. Validate coverage and asset references before activation; no scripts, executable rules or trusted HTML. Keep the active theme when validation fails. Resolve history at render time, so switching themes changes history labels as well as cards. Theme preference is not mechanical state.

## Persistence boundary

The [game-service API](docs/SERVICE.md) defines trusted human controllers, bot-to-seat mapping and application-save compatibility. The local browser retains its single-human boundary.

The storage interface supports creation, loading with revision, listing saves and committing a transition against an expected revision. Each commit atomically stores the versioned JSON snapshot, command, resulting events and next revision. Snapshot state includes pending effects/decisions, random states and bot memory. Do not use pickle or map every card/effect to database tables.

The initial adapter uses standard-library `sqlite3`. Keep transactions short: load, compute the proposed transition outside the transaction, then commit only if the expected revision still matches. Duplicate or competing submissions cannot commit a second time. Preserve incompatible save data and explain version rejection.

Keep runtime data outside tracked files, isolate worktree data, and bind the development server to localhost. Reject cross-origin mutations. The local release does not promise remote identity/authentication.

[The multiplayer contract](docs/MULTIPLAYER.md) defines the implemented hosted identity, private seats, reconnects and updates. Its separate application and database follow the [hosted storage boundary](docs/HOSTED_STORAGE.md) and [hosting procedures](docs/HOSTING.md); local saves are never published automatically. [Development decisions](docs/DECISIONS.md) record the chosen defaults and their tradeoffs for review.

## Hosted runtime adapters

The hosted extension supports two deployment targets: self-hosting on a laptop or VM, and Cloudflare Python Workers. Both use the same engine, identity and multiplayer services, filtered HTTP routes, templates and browser coordinator. The separate local application remains a no-account game for one human against bots; changing hosted runtimes never exposes its saves.

`StateStore.read(operation)` and `write(operation)` run synchronous callbacks with a typed `SqlSession`. Results are materialized values, not native database connections or cursors. Reads provide one consistent snapshot; writes commit all effects or roll back. Identity creation plus an invitation claim is one operation; session/membership revalidation plus a command receipt and snapshot is another. Compute engine transitions and bot choices outside these service callbacks, then recheck before committing. The public application operations remain `IdentityService` and `HostedService`; SQL sessions are an internal persistence boundary, not an HTTP API.

The self-hosted adapter uses a private on-disk SQLite database and a bounded threaded bot dispatcher in one application process. The Cloudflare adapter uses SQLite storage in **one Durable Object per installation**, holding all identities, sessions, invitations, memberships and games together. That deliberately preserves cross-record atomicity instead of splitting identity and games across objects. Durable alarms drive bounded bot work without browser requests. Cloudflare additionally encloses each runtime operation and its alarm update in one outer transaction, so a pending marker cannot commit without a durable wakeup. This includes bounded computation within that object-level transaction; other requests share the object's execution capacity. Runtime adapters select operation execution and scheduling; application rules do not choose platforms.

One installation object is also a capacity boundary: its requests and bot work share one object's execution and storage limits. This design does not claim automatic scaling across objects, and sharding requires a new authorization/transaction design. Review the current [Durable Object limits](https://developers.cloudflare.com/durable-objects/platform/limits/) before sizing a deployment. Self-hosted SQLite likewise remains limited to one application process on local disk.

## PostgreSQL transition

PostgreSQL remains an optional future adapter for a self-hosted deployment that needs multiple application servers or different recovery/availability guarantees. It is not required for the Cloudflare deployment, whose authoritative state and coordination live in a Durable Object. Measured contention, backup/failover needs or other deployment requirements can justify evaluating another adapter; player count alone does not select one.

Adapters preserve the same versioned engine snapshots and application operations. Driver-specific execution and transaction handling stay inside adapters; another database engine may also require different SQL. No PostgreSQL dependency, service or ORM is included.

The deferred `postgresql-shared-game-storage` task must:

1. Pass the same storage contracts for atomic commits, rollback, stale revisions, duplicate submissions and recovery; additionally test separate concurrent processes.
2. Transfer versioned SQLite snapshots and histories while preserving IDs and revisions. Validate counts, contents and representative resumed/replayed games.
3. Document backups and demonstrate restore before cutover. Stop writes during final transfer and verify the imported state before routing traffic.
4. Define rollback both before new writes and after PostgreSQL accepts writes; do not point back at a stale SQLite file.

Selecting a hosting runtime does not transfer existing data. No automatic live migration between a self-hosted database and a Durable Object is included. A future export/import must preserve all identity, membership, snapshot and receipt records, quiesce writes, validate the destination and define rollback. Keeping the application boundary small confines that migration to persistence and deployment; it does not remove the operational checks.
