# Sway

A local deck-building game with original themes, a deterministic Python rules engine and configurable computer opponents. The accepted release target follows Dominion second edition base mechanics; no official art or copied card descriptions are bundled. See [terminology and rule references](docs/TERMINOLOGY.md).

## Development

Install **uv 0.12.17** using the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is selected by `.python-version`. Each worktree has an independent `.venv` and ignored tool caches.

```bash
scripts/setup.sh
scripts/install-browsers.sh
scripts/dev.sh
```

The server defaults to `http://127.0.0.1:8000`. `scripts/dev.sh` supports uvicorn arguments, for example `--port 8001` for another worktree. The foundation PR installs tooling; gameplay and the `sway.web:app` entrypoint arrive in the dependent implementation PRs. [SPEC.md](SPEC.md) describes the accepted release, not a claim that every feature has shipped.

`setup.sh` synchronizes `uv.lock`, installs checksum-verified Biome, and installs staged-format/lint and pre-push hooks. `install-browsers.sh --with-deps` also installs system dependencies on supported Linux hosts. All project Python commands run through `uv run --locked`.

| Command | Purpose |
| --- | --- |
| `scripts/dev.sh` | Local server with reload |
| `scripts/format.sh` | Format Python, JavaScript, CSS and JSON |
| `scripts/fmt-check.sh` | Check formatting without rewriting |
| `scripts/lint.sh` | Ruff and Biome lint |
| `scripts/typecheck.sh` | Strict basedpyright |
| `scripts/test.sh` | Unit and integration tests; forwards pytest arguments |
| `scripts/coverage.sh` | Unit/integration tests and 90% engine branch coverage gate |
| `scripts/e2e.sh` | Chromium browser tests with failure traces |
| `scripts/build.sh` | Locked-environment wheel and source distribution |
| `scripts/check.sh` | Formatting, lint, types, coverage tests and build |

CI runs `check.sh` and the browser suite. For dependencies, use `uv add` or `uv add --dev` and commit both `pyproject.toml` and `uv.lock`. Change `.uv-version` and the matching `tool.uv.required-version` together; Biome upgrades also update `.biome-version`, configuration schema and `scripts/biome.sha256`.

## Project documents

- [AGENTS.md](AGENTS.md): focused PRs, isolated worktrees and agent responsibilities.
- [SPEC.md](SPEC.md): release scope, delivery sequence and acceptance criteria.
- [ARCHITECTURE.md](ARCHITECTURE.md): rules, rendering, privacy and persistence boundaries.
- [TODO.md](TODO.md): ordinary deferred work.
- [Review index](review/README.md) and [review backlog](review/BACKLOG.md): historical evidence and review-derived work.

MIT licensed. Sway is an independent project, unaffiliated with Dominion's creators or publisher. Original terminology and presentation reduce reuse of protected expression; they are not a legal clearance assessment.
