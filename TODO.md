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

- [TOOLING] `workflow-gate-automation` — **Validate workflow records and preserve every main validation run.** Queue/claim/link checks and review-drift reporting are absent from CI, and Quality currently cancels earlier main runs.
  - Starting point: Obtain explicit authorization for CI/hook policy changes, then adapt the repo-workflow validators to Sway's guides; cancel only superseded PR runs. Decide and document red-main response and review cadence without weakening existing gates.
  - Source: repo-workflow audit at f93f650, 2026-10-07

- [GAMEPLAY] `daily-attack-simulation-noncompletion` — **Investigate two attack-profile games that exhaust the daily decision budget.** October 6 daily evidence records one unfinished game in each of the three- and four-player rotating random-kingdom batches.
  - Starting point: At f93f650 reproduce `scripts/simulate.sh --players 3 --kingdom random --profiles attack --games 1 --seed 37502405135` and the four-player seed 37502405136. Both artifacts report 4,000 decisions, with 1,726 and 696 turns respectively. Determine whether bot policy, game rules or the bounded acceptance contract needs correction; preserve these seeds and do not hide failure by increasing limits. The October 7 passing corpus uses different rotating seeds and does not verify these failures fixed.
  - Source: https://github.com/vhata/sway/actions/runs/37502405129 and downloaded daily-simulations-3-1/daily-simulations-4-1 evidence at f93f650, 2026-10-07

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
