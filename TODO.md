# Deferred work

Ordinary follow-ups live here; whole-codebase review-derived work lives in [review/BACKLOG.md](review/BACKLOG.md). Follow [the queue guide](docs/TODO_GUIDE.md) before claiming or resolving work. The active release roadmap lives in [SPEC.md](SPEC.md).

## Needs triage

### P0 Critical

### P1 High

### P2 Normal

### P3 Low

- [PLATFORM] `portable-hosted-data-transfer` — **Move an existing hosted installation between SQLite and Cloudflare.** Selecting a runtime does not transfer its players, credentials or games. Low priority; current work focuses on hosted verification and recovery.
  - Starting point: Define a versioned whole-installation export/import with validation, downtime/cutover and rollback; preserve credential revocations, memberships, snapshots, revisions and receipts. Do not merge installations or copy local single-human saves into hosted mode.
  - Source: dual-hosting adapter implementation, 2026-09-25; user priority, 2026-09-30
  - Related: `hosted-live-operational-acceptance`

### Unprioritized

- [PLATFORM] `hosted-live-operational-acceptance` — **Rehearse recovery of the deployed installation and establish live capacity limits.** Maintenance-gated capture/restore/undo tooling is implemented; a production maintenance window and deployment-specific capacity acceptance remain operator work.
  - Starting point: Follow deployment/cloudflare/recovery/INSTALLATION.md with reviewed configuration, an explicitly authorized maintenance window and protected recovery checkpoints. Validate restored player access, game state and bot progress before reopening. Assess invite-only load limits separately: disposable recovery and bounded local request measurements do not establish production restoration or player capacity. Self-hosted endpoint acceptance is needed only if that runtime is deployed.
  - Source: hosted recovery follow-up, 2026-09-30
  - Remaining from: `hosted-installation-operations`
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

- [BACKEND] `postgresql-shared-game-storage` — **Add PostgreSQL if multiple self-hosted servers must share games.** A distant, conditional scaling option, behind cross-runtime transfer; the Cloudflare installation already uses its own durable state boundary.
  - Starting point: Implement an adapter preserving the complete identity/game transaction contracts, run shared and cross-process concurrency tests, and execute the verified transfer/backup/cutover/rollback requirements in ARCHITECTURE.md. Preserve game IDs, revisions, snapshots and history; add infrastructure only when deployment calls for it.
  - Source: accepted Sway persistence plan, 2026-09-22; user priority, 2026-09-30
  - Related: `hosted-live-operational-acceptance`

### Unprioritized
