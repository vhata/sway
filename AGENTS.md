# Sway: agent contract

Sway is a local deck-building game with deterministic Python rules and interchangeable original themes.

## Workflow

- Use focused branches and PRs for substantive code and documentation changes that need review. Two things go straight to `main` without a branch or PR: documentation that records work to be done (adding or triaging `TODO.md` entries, and plans; a plan is planning for work, not work, and everything it describes still goes through branches, PRs and review), and housekeeping metadata files such as `.git-blame-ignore-revs` or recovery of already reviewed changes, only when the user says so for that case. Extrapolate with common sense and say so in the commit; everything else, including all code and documentation that describes behaviour, goes through a PR. The user merges implementation PRs unless explicitly delegated. Preserve linear history; rebase dependent branches after prerequisites land.
- Use sub-agents for bounded implementation and independent review. Give each implementation agent a separate branch and worktree, with a PR when the review policy requires one. The coordinating agent owns shared interfaces and integration. Land or explicitly stack shared contracts before dependent work.
- Run `bash scripts/workflow/claim-check.sh <slug>` before starting (open and merged PRs, branches, worktrees), then create the branch and worktree with `bash scripts/workflow/start-work.sh <queue> <slug>`; any branch name containing the exact slug is an equivalent claim. Serialize queue bookkeeping and assign one owner to dependency changes. Preserve unrelated user changes. After a PR lands, `bash scripts/workflow/cleanup-landed.sh --apply` removes its worktree and branch.
- Use Python 3.12 through uv and the worktree's own `.venv`; use `uv run --locked`, not the user's shared interpreter or another worktree's environment. Commit dependency changes and `uv.lock` together.
- Use the executable `scripts/` entrypoints listed in README; `scripts/workflow/` holds the queue, link, PR-marker and review-drift validators described in the [quality policy](docs/QUALITY.md#workflow-checks). Complete relevant checks and independent review before presenting implementation PRs. Describe actual outcomes, evidence and remaining limitations.
- When a PR is required, open a draft after the first meaningful commit. Explain the need and resulting behaviour, then validation. Do not merge implementation PRs or tag a release without explicit authorization.
- Keep the current task focused. Capture separately shippable discoveries in the appropriate queue. User-authorized work does not need repeated permission.
- Keep rules in one authoritative home. Update documentation when behaviour changes; distinguish accepted plans from implemented features.
- Commit messages and PR bodies carry no AI attribution trailers or footers; the repository credits tooling once, in README or the repository description.

## Read when relevant

- Code or validation: [quality policy](docs/QUALITY.md).
- Deferred work: [TODO and backlog workflow](docs/TODO_GUIDE.md).
- Reviews and review-derived fixes: [code review guide](docs/CODE_REVIEW_GUIDE.md).
- Rules, decisions, privacy, themes or persistence: [architecture](ARCHITECTURE.md).
- Product scope and release gates: [accepted specification](SPEC.md).
- Card naming and rules provenance: [terminology](docs/TERMINOLOGY.md).

Keep this entrypoint short. Add detail to the relevant guide only when it prevents a concrete mistake.
