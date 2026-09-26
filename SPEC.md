# Accepted release specification

This is the accepted implementation target. Current capabilities and validation evidence belong in README and implementation PRs; unchecked release criteria remain work to complete.

## Game and presentation

- One human against one to three independently selected bots; complete Dominion second edition base mechanics (26 Kingdom definitions plus seven basic definitions).
- Preset, seeded random and manual ten-pile Kingdom selection. Deterministic games, readable history, final scoring and exact interrupted-decision recovery.
- Selectable economy, engine-building and attack-oriented bot profiles, each able to handle every decision shape and adapt to the selected supply. A seeded headless runner supports regressions and comparisons.
- Original bundled names, descriptions and simple artwork. Maintain stable IDs and a mapping to official terminology and mechanics references in [TERMINOLOGY.md](docs/TERMINOLOGY.md); document intentional deviations. Do not redistribute official card images or copied rule/card text.
- Two contrasting, complete data-only themes. Switching midgame updates labels, cards and history without changing mechanics, randomness or the pending decision.
- Keyboard-operable cards and choices, visible focus, clear constraints, accessible names and reduced motion. Local selection and ordering require no network request until confirmation.

The mechanics reference is the publisher's [second edition rulebook](https://www.riograndegames.com/wp-content/uploads/2016/09/Dominion2nd.pdf). This original local release excludes hosting, human multiplayer, expansions, expert AI and elaborate animation. Invite-only human play is now implemented as a separate [hosted extension](docs/MULTIPLAYER.md); actual deployment remains in [TODO.md](TODO.md). Retain the existing MIT licence. Original expression and a terminology mapping do not constitute legal clearance.

## Architecture commitments

The local release uses Python 3.12, uv, FastAPI, htpy, HTMX, small JavaScript modules, CSS and SQLite. Ruff handles Python formatting/lint; basedpyright checks strict types; pytest, Hypothesis and Playwright cover behaviour. Biome handles browser sources without a Node frontend build.

Keep the rules engine independent of web, themes, bots and storage. Humans and bots answer the same structured decisions. Filter every player view before rendering or passing it to a bot. Serialize the effect stack, pending decisions and separate game/bot random streams.

[ARCHITECTURE.md](ARCHITECTURE.md) defines the storage boundary. Local saves use SQLite. The separate hosted extension targets both laptop/VM self-hosting with SQLite and Cloudflare Python Workers with SQLite-backed Durable Objects, sharing application behaviour and transaction contracts. PostgreSQL is a deferred option for a different self-hosted scaling requirement, not a prerequisite for Cloudflare. Hosting does not expand this local release's one-human scope or automatically migrate its saves.

## Delivery

1. Foundation: process contracts, queues, packaging, scripts, hooks and CI.
2. Engine contract: typed state, structured decisions, serializable effects, private views, deterministic replay and invariants.
3. Parallel implementation PRs: starter card mechanics, bot profiles, htpy/HTMX interface with themes, storage interface with SQLite.
4. Playable milestone: complete saved browser game using the starter supply.
5. Full set: remaining cards in coherent batches with interaction tests.
6. Release review: full codebase review; separate fixes; incremental verification and release evidence.

The coordinating agent integrates independent branches after shared interfaces are established. Follow the [review policy](AGENTS.md#workflow) for PRs and direct-change exceptions; the user merges implementation PRs by default.

## Release acceptance

- [x] Every base definition has independently specified tests, including reactions, repeated/nested actions, partial effects, empty piles, shuffling, cleanup, scoring and ties.
- [x] State invariants cover card conservation, exclusive zone membership, legal resource accounting and invalid-command rejection.
- [x] Uninterrupted, resumed and replayed seeded games reach equivalent state; gameplay and bot randomness survive snapshots.
- [x] No forbidden information appears in player views, HTML, fragments, public history or bot inputs.
- [x] Storage proves atomic snapshots/history, stale-update rejection, duplicate submission handling, rollback and process restart recovery.
- [x] Every decision widget works in Chromium, including ordering, local selection, stale tabs, duplicate submits and human reactions during bot turns.
- [x] Both themes cover the full set; theme changes during pending decisions and reload preserve mechanical state.
- [x] Every bot profile finishes representative games across two, three and four players. Bounded simulations report unfinished runs without changing rules.
- [x] Shared quality scripts, package build and browser suite pass; engine branch coverage is at least 90% with meaningful assertions.
- [x] Full and follow-up incremental reviews leave no release-blocking correctness or information-disclosure finding unresolved.

All criteria were verified against the reviewed code; see [release evidence](ACCEPTANCE.md) for commands, commits, outcomes and limits.
