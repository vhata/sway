# Sway

A local deck-building game with original themes, a deterministic Python rules engine and configurable computer opponents. The rules implement all 26 Kingdom cards and seven basic card types from Dominion second edition; no official art or copied card descriptions are bundled. See [terminology and rule references](docs/TERMINOLOGY.md).

## Development

Install **uv 0.12.17** using the [uv installation instructions](https://docs.astral.sh/uv/getting-started/installation/). Python 3.12 is selected by `.python-version`. Each worktree has an independent `.venv` and ignored tool caches.

```bash
scripts/setup.sh
scripts/install-browsers.sh
scripts/dev.sh
```

The server defaults to `http://127.0.0.1:8000`. `scripts/dev.sh` supports uvicorn arguments, for example `--port 8001` for another worktree. The browser setup lets you choose two to four players, a separate economy, engine or attack profile for each opponent, and a starter, random or manually selected supply. Select a seed to reproduce a game. Common Ground and Orbital Commons supply original names and visuals; switch themes during play without changing the rules state. Every accepted decision is saved, including interrupted reactions, and saved tables resume from the home screen.

Development saves live in the current worktree's ignored `.runtime/` directory, so separate worktrees never share games by default. Set `SWAY_DATA_DIR` to choose another location. Running the installed `sway.web:app` directly defaults to `~/.local/share/sway`; it honors the same override. Keep the server local: this release has no remote-user authentication.

[SPEC.md](SPEC.md) records the release requirements. PostgreSQL deployment, human multiplayer, expansions and more advanced opponents are deferred.

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
