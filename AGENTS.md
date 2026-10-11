# Sway: agent contract

Sway is a local deck-building game with deterministic Python rules and interchangeable original themes.

<!-- docket:begin -->
## Docket

This project is run with docket. Read [docket/CONTRACT.md](docket/CONTRACT.md) before any work; it is the authoritative workflow, and this section records only this project's settings. The installer keeps this section current: the text above the list is rewritten on every run, the list keeps the values this project has set.

- Queue areas: `[UI]`, `[GAMEPLAY]`, `[AUDIO]`, `[BACKEND]`, `[PLATFORM]`, `[TOOLING]`, `[DOCS]`.
- Concurrency cap: none recorded. Each worktree has its own `.venv`, `.runtime/` saves and dev-server port, but the browser suite has timed out while another pytest process was running (`e2e-scoring-revision-wait-flake` in `TODO.md`), so stagger `scripts/e2e.sh` and `scripts/cloudflare-check.sh --browser` runs across worktrees.
- Merging and releases: no standing merge delegation. Deployments, anything that publishes a hosted installation, and changes to CI, hook policy and branch protection need the user's explicit authorization, as release tags do under the contract.
- Optional pieces in force: all of them, including the review ledger, stacked PRs and the daily validation of `main` (`.github/workflows/daily.yml`). There is no roadmap queue; the accepted release scope and sequence are in [SPEC.md](SPEC.md).
- Environment: Python 3.12 through uv with the worktree's own `.venv` (`scripts/setup.sh`, then `uv run --locked`), never the user's shared interpreter or another worktree's environment. Dependency changes have one owner in a fan-out (the lockfile rule is in [docs/QUALITY.md](docs/QUALITY.md)). Each worktree's dev server takes its own port (`scripts/dev.sh --port`). Preserve unrelated user changes in any worktree.
- Direct to main: in addition to the exceptions in the contract, recovery of already reviewed changes, only when the user says so for that case.
- Authorization: work the user has authorized needs no repeated permission; within an authorized task the coordinator resolves overlapping assignments itself and asks only when ownership is unclear.
- Scope records: [SPEC.md](SPEC.md) is the accepted scope and [ACCEPTANCE.md](ACCEPTANCE.md) the executed evidence; documentation distinguishes accepted plans from implemented features.
- Commits: capitalized imperative subjects. No generated-with footers in commits, PR bodies or anything else that reaches git history or a review thread; the repository credits tooling once, in README or the repository description. The repository's git identity (personal email) is already set.
- Queue routing: ordinary discoveries go to `TODO.md` even when they are bugs; only findings promoted from a codebase review go to `review/BACKLOG.md`.
- Landing and cleanup: after a PR lands, run `bash docket/scripts/cleanup-landed.sh` and then `--apply` to remove its worktree and branch; never remove dirty worktrees or unmerged work without permission.
<!-- docket:end -->

## Read when relevant

- Code or validation: [quality policy](docs/QUALITY.md).
- Deferred work: [queue guide](docket/TODO_GUIDE.md).
- Reviews and review-derived fixes: [code review guide](docket/CODE_REVIEW_GUIDE.md).
- Rules, decisions, privacy, themes or persistence: [architecture](ARCHITECTURE.md).
- Product scope and release gates: [accepted specification](SPEC.md).
- Card naming and rules provenance: [terminology](docs/TERMINOLOGY.md).
- Non-obvious choices and their trade-offs: [decisions](docs/DECISIONS.md).
