# Deferred work

Ordinary follow-ups live here; whole-codebase review-derived work lives in [review/BACKLOG.md](review/BACKLOG.md). Follow [the queue guide](docs/TODO_GUIDE.md) before claiming or resolving work. The active release roadmap lives in [SPEC.md](SPEC.md).

## Needs triage

### P0 Critical

### P1 High

### P2 Normal

### P3 Low

### Unprioritized

- [PLATFORM] `hosted-deployment-cutover` — **Deploy and verify the private multiplayer service on its chosen host.** The application and operating procedures are implemented; an actual endpoint needs deployment-specific TLS, proxy, capacity and recovery verification.
  - Starting point: Choose the host and canonical origin, then execute docs/HOSTING.md deployment acceptance and an isolated restore drill before inviting players. No deployment has been performed.
  - Source: hosted multiplayer implementation, 2026-09-24
  - Remaining from: `public-hosting-and-identity`
  - Related: `postgresql-shared-game-storage`

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
  - Related: `hosted-deployment-cutover`
