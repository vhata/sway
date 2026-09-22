# Sway: agent contract

Sway is a local deck-building game with deterministic Python rules and interchangeable original themes.

## Workflow

- Put every change, including process documents, on a focused branch and pull request. The user merges unless explicitly delegated. Preserve linear history; rebase dependent branches after prerequisites land.
- Use sub-agents for bounded implementation and independent review. Give each implementation agent a separate branch, worktree and PR. The coordinating agent owns shared interfaces and integration. Land or explicitly stack shared contracts before dependent work.
- Check branches, worktrees and open PRs for existing claims before starting. Serialize queue bookkeeping and assign one owner to dependency changes. Preserve unrelated user changes.
- Use Python 3.12 through uv and the worktree's own `.venv`; use `uv run --locked`, not the user's shared interpreter or another worktree's environment. Commit dependency changes and `uv.lock` together.
- Use the executable `scripts/` entrypoints listed in README. Complete relevant checks and independent review before presenting implementation PRs. Describe actual outcomes, evidence and remaining limitations.
- Open a draft PR after the first meaningful commit. Explain the need and resulting behaviour, then validation. Do not merge or tag a release without explicit authorization.
- Keep the current task focused. Capture separately shippable discoveries in the appropriate queue. User-authorized work does not need repeated permission.
- Keep rules in one authoritative home. Update documentation when behaviour changes; distinguish accepted plans from implemented features.

## Read when relevant

- Code or validation: [quality policy](docs/QUALITY.md).
- Deferred work: [TODO and backlog workflow](docs/TODO_GUIDE.md).
- Reviews and review-derived fixes: [code review guide](docs/CODE_REVIEW_GUIDE.md).
- Rules, decisions, privacy, themes or persistence: [architecture](ARCHITECTURE.md).
- Product scope and release gates: [accepted specification](SPEC.md).
- Card naming and rules provenance: [terminology](docs/TERMINOLOGY.md).

Keep this entrypoint short. Add detail to the relevant guide only when it prevents a concrete mistake.
