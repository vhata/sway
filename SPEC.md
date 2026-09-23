# Accepted release specification

This is the accepted implementation target. Current capabilities and validation evidence belong in README and implementation PRs; unchecked release criteria remain work to complete.

## Game and presentation

- One human against one to three independently selected bots; complete Dominion second edition base mechanics (26 Kingdom definitions plus seven basic definitions).
- Preset, seeded random and manual ten-pile Kingdom selection. Deterministic games, readable history, final scoring and exact interrupted-decision recovery.
- Selectable economy, engine-building and attack-oriented bot profiles, each able to handle every decision shape and adapt to the selected supply. A seeded headless runner supports regressions and comparisons.
- Original bundled names, descriptions and simple artwork. Maintain stable IDs and a mapping to official terminology and mechanics references in [TERMINOLOGY.md](docs/TERMINOLOGY.md); document intentional deviations. Do not redistribute official card images or copied rule/card text.
- Two contrasting, complete data-only themes. Switching midgame updates labels, cards and history without changing mechanics, randomness or the pending decision.
- Keyboard-operable cards and choices, visible focus, clear constraints, accessible names and reduced motion. Local selection and ordering require no network request until confirmation.

The mechanics reference is the publisher's [second edition rulebook](https://www.riograndegames.com/wp-content/uploads/2016/09/Dominion2nd.pdf). Public hosting, human multiplayer, expansions, expert AI and elaborate animation are deferred. Retain the existing MIT licence. Original expression and a terminology mapping do not constitute legal clearance.

## Architecture commitments

Python 3.12, uv, FastAPI, htpy, HTMX, small JavaScript modules, CSS and SQLite. Ruff handles Python formatting/lint; basedpyright checks strict types; pytest, Hypothesis and Playwright cover behaviour. Biome handles browser sources without a Node frontend build.

Keep the rules engine independent of web, themes, bots and storage. Humans and bots answer the same structured decisions. Filter every player view before rendering or passing it to a bot. Serialize the effect stack, pending decisions and separate game/bot random streams.

[ARCHITECTURE.md](ARCHITECTURE.md) defines the storage boundary: SQLite initially, PostgreSQL before multiple application servers share games, with shared contract tests and an explicit migration task. Do not add PostgreSQL infrastructure to the local release.

## Delivery

1. Foundation: process contracts, queues, packaging, scripts, hooks and CI.
2. Engine contract: typed state, structured decisions, serializable effects, private views, deterministic replay and invariants.
3. Parallel implementation PRs: starter card mechanics, bot profiles, htpy/HTMX interface with themes, storage interface with SQLite.
4. Playable milestone: complete saved browser game using the starter supply.
5. Full set: remaining cards in coherent batches with interaction tests.
6. Release review: full codebase review; separate fixes; incremental verification and release evidence.

The coordinating agent integrates independent branches after shared interfaces are established. All work goes through PRs; the user merges by default.

## Release acceptance

- [ ] Every base definition has independently specified tests, including reactions, repeated/nested actions, partial effects, empty piles, shuffling, cleanup, scoring and ties.
- [ ] State invariants cover card conservation, exclusive zone membership, legal resource accounting and invalid-command rejection.
- [ ] Uninterrupted, resumed and replayed seeded games reach equivalent state; gameplay and bot randomness survive snapshots.
- [ ] No forbidden information appears in player views, HTML, fragments, public history or bot inputs.
- [ ] Storage proves atomic snapshots/history, stale-update rejection, duplicate submission handling, rollback and process restart recovery.
- [ ] Every decision widget works in Chromium, including ordering, local selection, stale tabs, duplicate submits and human reactions during bot turns.
- [ ] Both themes cover the full set; theme changes during pending decisions and reload preserve mechanical state.
- [ ] Every bot profile finishes representative games across two, three and four players. Bounded simulations report unfinished runs without changing rules.
- [ ] Shared quality scripts, package build and browser suite pass; engine branch coverage is at least 90% with meaningful assertions.
- [ ] Full and follow-up incremental reviews leave no release-blocking correctness or information-disclosure finding unresolved.

Record checked criteria with actual commands, commits and outcomes in release evidence. Never check a box solely because code exists.
