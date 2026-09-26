# Deferred work

Ordinary follow-ups live here; whole-codebase review-derived work lives in [review/BACKLOG.md](review/BACKLOG.md). Follow [the queue guide](docs/TODO_GUIDE.md) before claiming or resolving work. The active release roadmap lives in [SPEC.md](SPEC.md).

## Needs triage

### P0 Critical

### P1 High

### P2 Normal

### P3 Low

### Unprioritized

- [PLATFORM] `hosted-installation-operations` — **Finish installation recovery and capacity acceptance.** The Cloudflare pilot has verified TLS/origin, HTTP/browser behaviour and isolated synthetic PITR; the deployed Installation still needs its own operational recovery rehearsal and capacity bounds.
  - Starting point: Follow docs/HOSTING.md and deployment/cloudflare/README.md to establish an operator-controlled recovery procedure for the actual Installation, rehearse it with protected recovery evidence, and assess invite-only load limits. Self-hosted endpoint deployment acceptance remains separate; an isolated RecoveryDrill namespace does not prove application Installation restoration.
  - Source: hosted multiplayer implementation, 2026-09-24
  - Remaining from: `hosted-deployment-cutover`
  - Related: `postgresql-shared-game-storage`

- [PLATFORM] `portable-hosted-data-transfer` — **Move an existing hosted installation between SQLite and Cloudflare.** Selecting a runtime does not transfer its players, credentials or games.
  - Starting point: Define a versioned whole-installation export/import with validation, downtime/cutover and rollback; preserve credential revocations, memberships, snapshots, revisions and receipts. Do not merge installations or copy local single-human saves into hosted mode.
  - Source: dual-hosting adapter implementation, 2026-09-25
  - Related: `hosted-installation-operations`

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
  - Related: `hosted-installation-operations`
