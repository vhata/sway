# Quality and validation

Read when changing code or preparing a PR. [README](../README.md#development) lists executable scripts shared by developers, hooks and CI. This document describes the gates as they exist now; history and rationale for past changes live in [DECISIONS.md](DECISIONS.md) and git.

## What quality means here

- Rules correctness: every card, nested effect, reaction, cleanup and scoring outcome matches an independently specified expectation, and an invalid choice is rejected before any effect occurs.
- Private information: no player view, rendered fragment, history event or bot input carries another seat's hidden cards or decisions.
- Serializable effects and deterministic replay: every accepted decision is a serializable event; saved, resumed and replayed games match the uninterrupted game, including pending effects and random streams.
- Duplicate commands and recovery: a repeated or stale command changes nothing, and a restart, reconnect, rollback or restore recovers the table without losing accepted decisions.
- Accessible decision workflows: cards and choices are keyboard-operable with visible focus, clear constraints and accessible names (see [SPEC.md](../SPEC.md)), and automatic refreshes keep the player's place.
- Deliberately manual: judgement about card art and themed presentation, and the live production recovery rehearsal and capacity limits recorded as `hosted-live-operational-acceptance` in [TODO.md](../TODO.md).

## Toolchain and gates

Python 3.12 and uv are mandatory. Every worktree owns its `.venv`. Use `uv sync --locked` and `uv run --locked`; dependencies and their lockfile change in the same PR. Ruff formats and lints Python, including htpy rendering. basedpyright uses strict checking for source and tests; suppressions must be narrow and explain the limitation. Biome formats/lints JavaScript, CSS and JSON. Pinned tool versions and checksum files are upgraded deliberately.

Pre-commit uses pre-commit's staged-file handling, including temporary unstaged-change preservation. It only formats/lints staged files. Pre-push runs types and unit/integration tests. Run `scripts/setup.sh` after changing hooks. Tracked `.githooks` wrappers resolve tools in the current worktree; they do not pin another worktree's interpreter. Setup configures `core.hooksPath` to that relative directory.

`scripts/check.sh` runs formatting, lint, type checking, unit/integration tests with both the existing 90% combined-coverage gate and a separate 90% engine branch gate, package builds and an installed-wheel smoke check. The branch gate prints statement and branch percentages separately from coverage JSON; high statement coverage cannot compensate for missing branches. The wheel check installs locked runtime dependencies and the wheel into a disposable uv environment, changes away from the checkout, disables Python path injection, and checks the homepage and packaged theme/browser assets. CI adds `scripts/e2e.sh` using Chromium; local browser changes require that suite as well.

The normal path to `main` requires a PR with zero approving reviews (independent agent review is recorded in `## Review`), the `Required quality checks` check, and linear history. The `Queue and PR hygiene` job runs alongside it and is not a required check. Since 2026-10-07 branches need not be up to date with `main` before merging and conversation resolution is not required; force pushes and deletions on `main` are allowed for the owner and never used by agents. The rule is not enforced for administrators, which permits the direct-to-main exceptions in [docket/CONTRACT.md](../docket/CONTRACT.md#workflow) and the Docket section of [AGENTS.md](../AGENTS.md#docket), each with its proportionate check. Local setup installs hooks; it does not change GitHub protection settings.

Do not claim tests passed when no tests were collected or a suite was skipped. Foundation scaffolding has no fabricated application tests. Unit/coverage scripts explicitly report a foundation-only skip only while both the engine directory and all Python test files are absent. The browser script reports a pending-implementation skip only while both the web module and Python browser tests are absent. Once the relevant code or tests exist, missing suites and empty collection fail normally; dependent implementation PRs supply real acceptance coverage. Report network, sandbox or missing-browser boundaries separately from application failures. Never silently disable a failing gate or lower coverage to finish a PR.

## Workflow checks

The queue, link, PR-marker, claim, worktree and review-drift tools are vendored from the docket skill under `docket/scripts/` and are never edited here; `bash ~/.claude/skills/docket/install.sh` resyncs them and `--check` reports drift (see [docket/README.md](../docket/README.md)). Like this project's own gates in `scripts/`, each is a standalone script, runnable from any directory, exiting non-zero on failure, so hooks, CI and agents run the same tools. They need bash 3.2 and git, plus `gh` for pull request lookups.

| Script | Runs | CI on PR | CI on main | Daily |
| --- | --- | --- | --- | --- |
| `docket/scripts/ci.sh` | `check-queues.sh --strict`, `check-links.sh` and, on pull requests, `check-pr-markers.sh` against the PR body (reads `PR`, `BASE`, `HEAD_BRANCH` and `GH_TOKEN` from the environment) | yes | yes | |
| `docket/scripts/review-due.sh --paths 'src tests'` | drift since the newest reviewed commit; a report, never a gate | | | yes |

The Quality workflow's `Queue and PR hygiene` job is one call to `docket/scripts/ci.sh`. No hook calls the vendored validators: run `bash docket/scripts/check-queues.sh --strict` and `bash docket/scripts/check-links.sh` before committing queue or documentation edits, and `bash docket/scripts/check-pr-markers.sh --body <file>` on a PR body before marking it ready. `claim-check.sh`, `start-work.sh` and `cleanup-landed.sh` are the agent-side tools described in [docket/CONTRACT.md](../docket/CONTRACT.md) and [docket/TODO_GUIDE.md](../docket/TODO_GUIDE.md). The daily quality lane keeps the `review-due.sh` report with the lane's evidence.

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

The quality lane also records `docket/scripts/review-due.sh` so review drift is
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

## Review inputs

What the vendored review guide ([docket/CODE_REVIEW_GUIDE.md](../docket/CODE_REVIEW_GUIDE.md)) reads from this project.

- Focus areas: the list under [What quality means here](#what-quality-means-here) (correctness, private information, serializable effects, deterministic replay, duplicate commands, recovery and accessible decision workflows) and the boundaries in [ARCHITECTURE.md](../ARCHITECTURE.md).
- Baseline commands beyond `bash scripts/check.sh`: `scripts/e2e.sh` (record pytest's exit status and the printed `browser-evidence/run-*` directory) and `scripts/cloudflare-check.sh --browser`, the two gates the Quality workflow runs outside `check.sh`. Record environmental gaps (no Chromium, no Node) separately from application failures.
- Review drift: `bash docket/scripts/review-due.sh --paths 'src tests'`.
- Baseline rule: the reviewed commit is reachable from `main`. If a pre-landing review is unavoidable, preserve its exact tree and record the landed revision only after verifying tree equality; a branch commit outside `main` is not an ancestry baseline, and a merge-base estimate does not establish review coverage (see the [review index](../review/README.md#review-baseline)).
- Drift checks for an incremental review: stale terminology against [TERMINOLOGY.md](TERMINOLOGY.md); dead code and configuration; inconsistent interfaces across the local, self-hosted and Cloudflare runtimes; weak assertions; changed dependencies in `uv.lock`; README commands against `scripts/`; this document against `.githooks/`, `.pre-commit-config.yaml` and `.github/workflows/`; `bash ~/.claude/skills/docket/install.sh --check` for drift in `docket/`. Use evidence rather than file-size thresholds.

## PR evidence

Include checks actually run, outcomes and any limits. For a behaviour change, include a concise reproducible scenario. Use an independent sub-agent review before presenting implementation PRs. See [docket/CODE_REVIEW_GUIDE.md](../docket/CODE_REVIEW_GUIDE.md) for findings and immutable review ledgers.
