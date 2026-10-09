# Quality and validation

Read when changing code or preparing a PR. [README](../README.md#development) lists executable scripts shared by developers, hooks and CI.

## Toolchain and gates

Python 3.12 and uv are mandatory. Every worktree owns its `.venv`. Use `uv sync --locked` and `uv run --locked`; dependencies and their lockfile change in the same PR. Ruff formats and lints Python, including htpy rendering. basedpyright uses strict checking for source and tests; suppressions must be narrow and explain the limitation. Biome formats/lints JavaScript, CSS and JSON. Pinned tool versions and checksum files are upgraded deliberately.

Pre-commit uses pre-commit's staged-file handling, including temporary unstaged-change preservation. It only formats/lints staged files. Pre-push runs types and unit/integration tests. Run `scripts/setup.sh` after changing hooks. Tracked `.githooks` wrappers resolve tools in the current worktree; they do not pin another worktree's interpreter. Setup configures `core.hooksPath` to that relative directory.

`scripts/check.sh` runs formatting, lint, type checking, unit/integration tests with both the existing 90% combined-coverage gate and a separate 90% engine branch gate, package builds and an installed-wheel smoke check. The branch gate prints statement and branch percentages separately from coverage JSON; high statement coverage cannot compensate for missing branches. The wheel check installs locked runtime dependencies and the wheel into a disposable uv environment, changes away from the checkout, disables Python path injection, and checks the homepage and packaged theme/browser assets. CI adds `scripts/e2e.sh` using Chromium; local browser changes require that suite as well.

The normal path to `main` requires a PR with zero approving reviews (independent agent review is recorded in `## Review`), the `Required quality checks` check, and linear history. The `Queue and PR hygiene` job runs alongside it and is not a required check. Since 2026-10-07 branches need not be up to date with `main` before merging and conversation resolution is not required; force pushes and deletions on `main` are allowed for the owner and never used by agents. The rule is not enforced for administrators, which permits the direct-to-main exceptions in the [agent contract](../AGENTS.md#workflow), each with its proportionate check. Local setup installs hooks; it does not change GitHub protection settings.

Do not claim tests passed when no tests were collected or a suite was skipped. Foundation scaffolding has no fabricated application tests. Unit/coverage scripts explicitly report a foundation-only skip only while both the engine directory and all Python test files are absent. The browser script reports a pending-implementation skip only while both the web module and Python browser tests are absent. Once the relevant code or tests exist, missing suites and empty collection fail normally; dependent implementation PRs supply real acceptance coverage. Report network, sandbox or missing-browser boundaries separately from application failures. Never silently disable a failing gate or lower coverage to finish a PR.

## Workflow checks

`scripts/workflow/` holds the repo-workflow validators, copied from the skill so that hooks, CI and agents without the skill run the same tools. They need bash 3.2 and git, plus `gh` for pull request lookups.

| Script | Purpose |
| --- | --- |
| `check-queues.sh --strict` | Entry format, unique slugs, `Source` lines, resolvable `Related`/`Depends on`, one finding per backlog entry, in `TODO.md` and `review/BACKLOG.md` |
| `check-links.sh` | Every relative Markdown link resolves |
| `check-pr-markers.sh --body FILE` | `## Why` first; every Claims/Resolves/Files marker matches the queues at `origin/main` and `HEAD` |
| `claim-check.sh <slug>` | Existing claims across open and merged PRs, branches and worktrees |
| `start-work.sh <queue> <slug>` | Claim check, then branch and worktree under `.worktrees/` |
| `cleanup-landed.sh [--apply]` | Remove worktrees and branches whose PR merged; dry run by default |
| `review-due.sh --paths 'src tests'` | Drift since the newest reviewed commit; a report, never a gate |

Run the queue and link checks before committing queue or documentation edits and the marker check on a PR body before marking it ready. The Quality workflow's `Queue and PR hygiene` job runs the queue and link checks on every PR and push to `main`, and the marker check against the PR body on pull requests. The daily quality lane runs `review-due.sh` and keeps its report with the lane's evidence.

## Red main

Quality cancels only superseded pull request runs; each push to `main` runs in its own concurrency group, so no merge's run is cancelled or replaced and every merge keeps its own validation evidence. When a push run or a daily run on `main` fails, the same day either revert the change or file a P1 `TODO.md` entry (P0 if it blocks a release) with the run link and the evidence artifact. A green fix branch is not recovery; recovery is the next run on `main` going green, and the entry stays open until it does. A missing scheduled run is not a pass.

## Meaningful tests

- Rules: independently specified expected outcomes for all cards, nested effects, reaction timing, empty supply, cleanup, scoring and ties. Test invalid choices before effects occur.
- Invariants: Hypothesis checks card conservation, exclusive membership, legal accounting and rejected-command immutability.
- Determinism: saved/resumed and replayed games match uninterrupted state, including pending effects and random streams. Preserve failing seeds.
- Privacy: inspect every player view, rendered fragment, history event and bot input for hidden data leaks.
- Storage: reusable contract tests verify atomic snapshots/history, revisions, rollback, duplicate commands and reopen recovery. Reuse them for PostgreSQL when introduced.
- Browser: exercise real local widgets, refresh/focus, stale tabs, duplicate submits, bot-turn reactions, theme changes and restart recovery. Keep failure traces.
- Strategies: representative seeded games across profiles and player counts; bound simulations and report incomplete games honestly.

Use tests that fail for a meaningful regression, not assertions copying implementation details. Documentation-only work needs link/claim checks, not invented tests. Run the relevant checks once, then repeat or broaden only to investigate a concrete failure, code change or remaining concern.

`scripts/e2e.sh` prints a unique `browser-evidence/run-*` directory for each invocation,
including reruns. It retains the commit, pytest arguments/output/exit status,
failed Playwright and hosted-context traces, and the temporary server databases
and logs. The script owns pytest's `--output` and `--basetemp` paths; use the
printed directory to inspect evidence. Existing runs remain untouched. These
ignored directories can contain private sessions and game state: retain a failed
run before cleaning local artifacts and share only the relevant sanitized evidence.
The paths stay outside pytest-playwright's default `test-results/`, which even
non-browser pytest sessions clear at startup. CI uploads both directories when a
check fails.

## Daily verification

The **Daily verification** workflow runs on `main` at **11:23 UTC every day**
(04:23 Pacific daylight time / 03:23 Pacific standard time). GitHub schedules are
best-effort and can be delayed; the off-hour minute avoids the busiest scheduling
boundary. The schedule becomes active when the workflow lands on the default
branch. Use Actions → Daily verification → Run workflow to run it manually on
the selected ref. Every lane checks out the same event commit. PRs changing the
daily workflow or its dedicated gates also run it before landing.

Seven independent jobs collect results even if another job fails:

- Full formatting, lint, strict types, unit/integration tests, both coverage
  thresholds, source/wheel builds and installed-wheel smoke. The invariant
  property runs 300 examples instead of the normal 30; the Actions run ID seeds
  Hypothesis so a rerun reproduces the corpus.
- The complete native Chromium suite, including hosted browser acceptance.
- Real local Workers contracts, pending-alarm restart and 2/3/4-player browser
  checks, then package build/install with the generated Workers tree present.
- Private local recovery RPC against synthetic state, including identity,
  game/receipt changes and credential revocation. The ordinary unit suite also
  checks maintenance gating and the operator controller's lost-response recovery.
- Three simulation jobs for 2/3/4 players, each running 600 games: 25 fixed seeds
  and 25 rotating seeds across preset/random kingdoms, all three homogeneous
  bot profiles and three mixed seat rotations. Unfinished games fail the job;
  later successful batches cannot hide a failure.

The quality lane also records `scripts/workflow/review-due.sh` so review drift is
visible without a local checkout. The daily concurrency group is separate from
push/PR quality checks and does not cancel an in-progress daily run. There are no automatic test retries. Artifacts
are uploaded on success and failure for 14 days: logs, coverage/JUnit output,
simulation JSON with seeds/configurations, and each browser run's evidence.
Recovery proof files remain outside uploads. These tests use local synthetic
state and no deployment credentials; local workerd does not support PITR, so
this workflow does not establish live production restore or capacity evidence.

To reproduce the extended gates locally, use the same scripts and recorded seeds:

```sh
SWAY_PROPERTY_EXAMPLES=300 scripts/check.sh --hypothesis-seed <run-id> --hypothesis-show-statistics
scripts/daily-simulations.sh 2 <run-id> # Repeat for 3 and 4 players.
scripts/cloudflare-recovery-check.sh
scripts/cloudflare-check.sh --browser
scripts/build.sh && scripts/install-smoke.sh
```

Simulation output is under `daily-evidence/simulations-<players>/`; recovery logs
are under `daily-evidence/recovery/`. Browser evidence uses the per-run directories
described above. GitHub's [schedule documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
describes delay and inactivity-disable behaviour; a missing scheduled run is not
a passing check.

## PR evidence

Include checks actually run, outcomes and any limits. For a behaviour change, include a concise reproducible scenario. Use an independent sub-agent review before presenting implementation PRs. See [review guidance](CODE_REVIEW_GUIDE.md) for findings and immutable review ledgers.
