# Deferred work

Ordinary follow-ups live here; whole-codebase review-derived work lives in [review/BACKLOG.md](review/BACKLOG.md). Follow [the queue guide](docs/TODO_GUIDE.md) before claiming or resolving work. The active release roadmap lives in [SPEC.md](SPEC.md).

## Needs triage

### P0 Critical

### P1 High

### P2 Normal

### P3 Low

### Unprioritized

- [PLATFORM] `hosted-deployment-cutover` — **Deploy and verify a private multiplayer installation.** Self-hosted and Cloudflare adapters are implemented; a real endpoint still needs platform-specific origin/TLS, capacity and recovery verification.
  - Starting point: Choose self-hosting or Cloudflare and the canonical origin, then execute docs/HOSTING.md and the selected runtime guide's acceptance checks, including a recovery drill before inviting players. No deployment has been performed.
  - Source: hosted multiplayer implementation, 2026-09-24
  - Remaining from: `public-hosting-and-identity`
  - Related: `postgresql-shared-game-storage`

- [PLATFORM] `portable-hosted-data-transfer` — **Move an existing hosted installation between SQLite and Cloudflare.** Selecting a runtime does not transfer its players, credentials or games.
  - Starting point: Define a versioned whole-installation export/import with validation, downtime/cutover and rollback; preserve credential revocations, memberships, snapshots, revisions and receipts. Do not merge installations or copy local single-human saves into hosted mode.
  - Source: dual-hosting adapter implementation, 2026-09-25
  - Related: `hosted-deployment-cutover`

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

- [BACKEND] `postgresql-shared-game-storage` — **Add PostgreSQL if multiple self-hosted servers must share games.** A server database is a future self-hosting adapter; the Cloudflare installation already uses its own durable state boundary.
  - Starting point: Implement an adapter preserving the complete identity/game transaction contracts, run shared and cross-process concurrency tests, and execute the verified transfer/backup/cutover/rollback requirements in ARCHITECTURE.md. Preserve game IDs, revisions, snapshots and history; add infrastructure only when deployment calls for it.
  - Source: accepted Sway persistence plan, 2026-09-22
  - Related: `hosted-deployment-cutover`
