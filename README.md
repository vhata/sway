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

To compare cards with the [original terminology reference](docs/TERMINOLOGY.md), start the server with `SWAY_DEV_TERMINOLOGY=1 scripts/dev.sh`. This optional developer mode adds visible `Original: …` subtext beneath themed card names, including setup and decision choices. It works with either theme and does not change saved games or gameplay. The flag is read at server startup and is disabled unless its value is exactly `1`; omit it and restart to return to normal rendering. Installed servers support the same environment variable.

Developer mode also links to `/developer/cards`, a read-only catalogue of all 33 cards with a theme selector. It uses the same card faces as the game and opens separately from an active table, so inspecting designs does not discard an unfinished selection. The catalogue is unavailable when developer mode is off.

[SPEC.md](SPEC.md) records the accepted local release. A separate hosted application supports invite-only human multiplayer on a laptop/VM or Cloudflare Python Workers; [hosting instructions](docs/HOSTING.md) explain the deployment choices and their operational boundaries. PostgreSQL, public matchmaking, expansions and more advanced opponents remain deferred.


`setup.sh` synchronizes `uv.lock`, installs checksum-verified Biome, and installs staged-format/lint and pre-push hooks. `install-browsers.sh --with-deps` also installs system dependencies on supported Linux hosts. All project Python commands run through `uv run --locked`.

| Command | Purpose |
| --- | --- |
| `scripts/dev.sh` | Local server with reload |
| `scripts/hosted.sh` | Configured private multiplayer server behind a TLS proxy |
| `scripts/cloudflare.sh` | Cloudflare runtime tooling; defaults to local development ([guide](deployment/cloudflare/README.md)) |
| `scripts/cloudflare-check.sh --browser` | Shared contracts, pending-alarm restart and multiplayer browser checks on real local workerd |
| `scripts/format.sh` | Format Python, JavaScript, CSS and JSON |
| `scripts/fmt-check.sh` | Check formatting without rewriting |
| `scripts/lint.sh` | Ruff and Biome lint |
| `scripts/typecheck.sh` | Strict basedpyright |
| `scripts/test.sh` | Unit and integration tests; forwards pytest arguments |
| `scripts/coverage.sh` | Unit/integration tests and 90% engine branch coverage gate |
| `scripts/e2e.sh` | Chromium browser tests with failure traces |
| `scripts/build.sh` | Locked-environment wheel and source distribution |
| `scripts/install-smoke.sh` | Install the wheel into an isolated uv environment and probe packaged assets |
| `scripts/check.sh` | Formatting, lint, types, coverage tests, build and installed-wheel smoke |

CI runs `check.sh`, the native browser suite and `cloudflare-check.sh --browser`. For dependencies, use `uv add` or `uv add --dev` and commit both `pyproject.toml` and `uv.lock`. Change `.uv-version` and the matching `tool.uv.required-version` together; Biome upgrades also update `.biome-version`, configuration schema and `scripts/biome.sha256`.

## Private multiplayer

Hosted tables have two to four seats, with invited humans and independently selected computer opponents. Create a guest player, save the recovery code, and share a seat invitation privately. Every human readies the current setup before the host starts. Each browser sees only its own hand and decisions, including reactions during another player's turn. Waiting tables update automatically, and computers keep playing when no browser is open.

Recovering a player rotates the recovery code and signs out older sessions. A disconnected human keeps their seat indefinitely. Save the recovery code: losing it and all browser sessions requires starting another table. The host can cancel a table but cannot take another player's seat or view their cards. Theme choices affect only the viewer.

Choose the deployment adapter described in [HOSTING.md](docs/HOSTING.md):

- **Laptop or VM:** `scripts/hosted.sh`, one Python process behind a TLS proxy, a private SQLite database and local backup/restore tools.
- **Cloudflare:** Python Workers with one SQLite-backed Durable Object per installation and durable bot alarms. The same hosted rules, identity policies and browser interface apply.

Local saves are never published by hosted mode. Selecting another runtime does not copy existing players or games; cross-runtime export/import is not implemented. No public deployment is bundled or automatically performed.


## Project documents

- [AGENTS.md](AGENTS.md): focused PRs, isolated worktrees and agent responsibilities.
- [SPEC.md](SPEC.md): release scope, delivery sequence and acceptance criteria.
- [ACCEPTANCE.md](ACCEPTANCE.md): executed release checks and requirement evidence.
- [ARCHITECTURE.md](ARCHITECTURE.md): rules, rendering, privacy and persistence boundaries.
- [TODO.md](TODO.md): ordinary deferred work.
- [Review index](review/README.md) and [review backlog](review/BACKLOG.md): historical evidence and review-derived work.

MIT licensed. Sway is an independent project, unaffiliated with Dominion's creators or publisher. Original terminology and presentation reduce reuse of protected expression; they are not a legal clearance assessment.
