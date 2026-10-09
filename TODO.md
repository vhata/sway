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

- [BACKEND] `unreadable-table-member-views` — **Show an unreadable table as unavailable and let its host cancel it.** A table whose snapshot the running code cannot load raises `SaveFormatError` from every member view, so its members' home pages return 500 and, on Cloudflare, the host's cancel rolls back.
  - Starting point: Make `HostedService._view` tolerate `SaveFormatError` (render the table as unavailable without a board) so `list_tables`, `view`, `retry_bots` and `cancel` succeed for members; keep the snapshot unchanged. Reproduce with a table whose snapshot has `"schema": 99` on both runtimes.
  - Source: independent review of `hosted-bot-scan-resilience` (PR #34), 2026-10-09

- [BACKEND] `blank-guest-name-loses-invitation` — **Keep the invitation retryable when a guest's display name is rejected.** A display name of only spaces passes the browser's `required` check but fails server validation, and the generic 422 "Check your choices" page leaves the invitee with no way back, because the join page has already removed the secret from the address.
  - Starting point: Re-render the invitation form with the validation message (and the hidden secret) on display-name errors, or trim and validate in the browser; cover with a TestClient test.
  - Source: `request-error-responses` implementation (PR #33), 2026-10-09

- [TOOLING] `e2e-scoring-revision-wait-flake` — **Stop the full-game browser test timing out on a busy machine.** `test_complete_game_reaches_scoring_and_saved_result` waits the default 5 s for `#board` to change `data-revision` after each confirmed choice, and failed once while another pytest process was running; it passed 3/3 in isolation.
  - Starting point: Give the revision `expect` in `tests/e2e/test_browser.py` the same explicit timeout as the surrounding waits, or wait on the server revision instead.
  - Source: `request-error-responses` implementation (PR #33), 2026-10-09

- [TOOLING] `setup-installs-test-browser` — **Make a fresh worktree's browser suite run without a separate setup step.** `scripts/setup.sh` does not install Chromium, so `scripts/e2e.sh` in a new worktree errors on every test until `scripts/install-browsers.sh` runs; three parallel agents hit this in one session.
  - Starting point: Call `scripts/install-browsers.sh` from `setup.sh` (it is per-worktree under `.cache/playwright`), or have `e2e.sh` fail fast with the command to run.
  - Source: parallel review-backlog fan-out, 2026-10-09
