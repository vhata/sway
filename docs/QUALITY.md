# Quality and validation

Read when changing code or preparing a PR. [README](../README.md#development) lists executable scripts shared by developers, hooks and CI.

## Toolchain and gates

Python 3.12 and uv are mandatory. Every worktree owns its `.venv`. Use `uv sync --locked` and `uv run --locked`; dependencies and their lockfile change in the same PR. Ruff formats and lints Python, including htpy rendering. basedpyright uses strict checking for source and tests; suppressions must be narrow and explain the limitation. Biome formats/lints JavaScript, CSS and JSON. Pinned tool versions and checksum files are upgraded deliberately.

Pre-commit uses pre-commit's staged-file handling, including temporary unstaged-change preservation. It only formats/lints staged files. Pre-push runs types and unit/integration tests. Run `scripts/setup.sh` after changing hooks. Tracked `.githooks` wrappers resolve tools in the current worktree; they do not pin another worktree's interpreter. Setup configures `core.hooksPath` to that relative directory.

`scripts/check.sh` runs formatting, lint, type checking, unit/integration tests with the 90% engine branch gate, and package builds. CI adds `scripts/e2e.sh` using Chromium; local browser changes require that suite as well.

The normal path to `main` requires a PR, the `Required quality checks` check against the current base, linear history and resolved review conversations. Owner/administrator bypass is permitted for small documentation corrections and explicitly authorized recovery of already reviewed changes under the [review policy](../AGENTS.md#workflow), with proportionate validation. Local setup installs hooks; it does not change GitHub protection settings.

Do not claim tests passed when no tests were collected or a suite was skipped. Foundation scaffolding has no fabricated application tests. Unit/coverage scripts explicitly report a foundation-only skip only while both the engine directory and all Python test files are absent. The browser script reports a pending-implementation skip only while both the web module and Python browser tests are absent. Once the relevant code or tests exist, missing suites and empty collection fail normally; dependent implementation PRs supply real acceptance coverage. Report network, sandbox or missing-browser boundaries separately from application failures. Never silently disable a failing gate or lower coverage to finish a PR.

## Meaningful tests

- Rules: independently specified expected outcomes for all cards, nested effects, reaction timing, empty supply, cleanup, scoring and ties. Test invalid choices before effects occur.
- Invariants: Hypothesis checks card conservation, exclusive membership, legal accounting and rejected-command immutability.
- Determinism: saved/resumed and replayed games match uninterrupted state, including pending effects and random streams. Preserve failing seeds.
- Privacy: inspect every player view, rendered fragment, history event and bot input for hidden data leaks.
- Storage: reusable contract tests verify atomic snapshots/history, revisions, rollback, duplicate commands and reopen recovery. Reuse them for PostgreSQL when introduced.
- Browser: exercise real local widgets, refresh/focus, stale tabs, duplicate submits, bot-turn reactions, theme changes and restart recovery. Keep failure traces.
- Strategies: representative seeded games across profiles and player counts; bound simulations and report incomplete games honestly.

Use tests that fail for a meaningful regression, not assertions copying implementation details. Documentation-only work needs link/claim checks, not invented tests. Run the relevant checks once, then repeat or broaden only to investigate a concrete failure, code change or remaining concern.

## PR evidence

Include checks actually run, outcomes and any limits. For a behaviour change, include a concise reproducible scenario. Use an independent sub-agent review before presenting implementation PRs. See [review guidance](CODE_REVIEW_GUIDE.md) for findings and immutable review ledgers.
