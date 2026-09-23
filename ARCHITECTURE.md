# Architecture contracts

These boundaries guide implementation. The accepted release and unfinished capabilities are tracked in [SPEC.md](SPEC.md); implementation PRs establish the concrete typed interfaces.

## Rules and decisions

The engine owns authoritative state and all rules, independently of HTTP, HTML, databases and names. Card definition IDs are stable; every physical card instance has its own ID and exactly one zone. Include temporary revealed and set-aside zones in conservation checks.

The public operations are `new_game(config, seed)`, `advance(state, command)` and `view_for(state, player)`. A transition returns new state and structured events. Decisions name their owner, kind, options, selection limits and ordering constraints. Commands carry the decision ID and expected revision. Validate every command before accepting a transition; the browser is not an authority.

Effects use a serializable stack that can pause at nested choices and opponents' reactions. Do not encode continuation state in generators, closures or HTTP sessions. Explicit game and bot random streams keep replay independent of rendering and strategy implementation details.

Bots receive the same filtered view and decision as a human, plus their own persisted versioned memory and random source. Strategies express preferences over available legal choices. They do not inspect authoritative opponents' hands, hidden deck order or the gameplay random stream.

## Presentation and privacy

Use typed htpy functions accepting presentation data from a filtered player view. Rules, costs and effects never depend on visible text. HTMX submits completed decisions and requests fragments. Small JavaScript components maintain selection/order locally, preserve focus on refresh and reset when the decision ID changes.

Filter structured events as well as state: discarded/revealed public cards and hidden draws have different visibility. Never send authoritative snapshots to templates or clients. Render pending choices only for their owner. The future API can expose the same player views and decisions without changing rules or bots.

Bot progress is bounded per server step; stop for a human reaction. Failures are recoverable and visible. A stale browser re-renders current state after a rejected revision; it never overwrites it.

Theme packs contain versioned data for stable IDs: names, independently written descriptions, terminology, accessibility labels, local asset references and design tokens. Validate coverage and asset references before activation; no scripts, executable rules or trusted HTML. Keep the active theme when validation fails. Resolve history at render time, so switching themes changes history labels as well as cards. Theme preference is not mechanical state.

## Persistence boundary

The storage interface supports creation, loading with revision, listing saves and committing a transition against an expected revision. Each commit atomically stores the versioned JSON snapshot, command, resulting events and next revision. Snapshot state includes pending effects/decisions, random states and bot memory. Do not use pickle or map every card/effect to database tables.

The initial adapter uses standard-library `sqlite3`. Keep transactions short: load, compute the proposed transition outside the transaction, then commit only if the expected revision still matches. Duplicate or competing submissions cannot commit a second time. Preserve incompatible save data and explain version rejection.

Keep runtime data outside tracked files, isolate worktree data, and bind the development server to localhost. Reject cross-origin mutations. The local release does not promise remote identity/authentication.

[The multiplayer proposal](docs/MULTIPLAYER.md) defines invite-only identity, private seats, reconnects and updates for a future implementation; it does not enable hosted access. [Development decisions](docs/DECISIONS.md) record the chosen defaults and their tradeoffs for review.

## PostgreSQL transition

**SQLite is the local-release adapter. PostgreSQL is the planned adapter before multiple application servers share persistent games.** Single-server public hosting alone does not require migration. Measured write contention, backup/failover needs or other deployment requirements can justify earlier migration.

Both adapters use the same engine state format and storage operations. Backend-specific SQL and transaction handling stay inside adapters. No PostgreSQL dependency, service or ORM is required initially.

The deferred `postgresql-shared-game-storage` task must:

1. Pass the same storage contracts for atomic commits, rollback, stale revisions, duplicate submissions and recovery; additionally test separate concurrent processes.
2. Transfer versioned SQLite snapshots and histories while preserving IDs and revisions. Validate counts, contents and representative resumed/replayed games.
3. Document backups and demonstrate restore before cutover. Stop writes during final transfer and verify the imported state before routing traffic.
4. Define rollback both before new writes and after PostgreSQL accepts writes; do not point back at a stale SQLite file.

Changing adapters is a real migration with operational verification. Keeping the interface small confines that work to storage and deployment.
