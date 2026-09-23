# Deferred work

Ordinary follow-ups live here; whole-codebase review-derived work lives in [review/BACKLOG.md](review/BACKLOG.md). Follow [the queue guide](docs/TODO_GUIDE.md) before claiming or resolving work. The active release roadmap lives in [SPEC.md](SPEC.md).

## Needs triage

### P0 Critical

### P1 High

### P2 Normal

### P3 Low

### Unprioritized

- [PLATFORM] `public-hosting-and-identity` — **Define a hosted deployment and player identity.** A public service requires explicit authentication, operations and abuse controls beyond the local release.
  - Starting point: Decide deployment scale and session ownership before exposing mutation routes publicly.
  - Source: accepted Sway implementation plan, 2026-09-22
  - Related: `postgresql-shared-game-storage`, `human-multiplayer`
- [GAMEPLAY] `human-multiplayer` — **Support remote human opponents.** Persistent private seats and reconnect handling let people play together.
  - Starting point: Define invitations, turn ownership and disconnect behaviour using existing filtered decisions.
  - Source: accepted Sway implementation plan, 2026-09-22
  - Related: `public-hosting-and-identity`

## Needs proof of concept

### P0 Critical

### P1 High

### P2 Normal

### P3 Low

### Unprioritized

## Ready for separate work

### P0 Critical

### P1 High

### P2 Normal

### P3 Low

### Unprioritized

- [BACKEND] `postgresql-shared-game-storage` — **Add PostgreSQL before multiple servers share games.** A server database supports shared writes and production operating requirements while preserving the engine's storage boundary.
  - Starting point: Implement the storage protocol, run shared and cross-process concurrency tests, and execute the verified transfer/backup/cutover/rollback requirements in ARCHITECTURE.md. Preserve game IDs, revisions, snapshots and history; add infrastructure only when deployment calls for it.
  - Source: accepted Sway persistence plan, 2026-09-22
  - Related: `public-hosting-and-identity`
