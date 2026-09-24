# Local release acceptance evidence

Verified on 2026-09-22 against code commit `00ede93622b15fd8e71a9667a268399346c68a61`. Subsequent changes in the release-review PR only record this evidence and close the review queue. The accepted scope is in [SPEC.md](SPEC.md).

## Executed gates

| Command | Result |
| --- | --- |
| `scripts/check.sh` | Ruff/Biome formatting and lint passed; strict basedpyright reported 0 errors/warnings; 218 unit/integration tests passed; sdist and wheel built; isolated installed-wheel probe passed |
| `scripts/e2e.sh` | 11 Chromium tests passed in 25.91 seconds |
| Required GitHub quality check | [PR #7 Linux run](https://github.com/vhata/sway/actions/runs/35711943444) passed, including both shared scripts |

Local environment: macOS, Python 3.12.14, uv 0.12.17, locked dependencies and a separate worktree environment. Chromium used the installed browser cache with process-sandbox permission. The wheel was installed into a fresh uv environment with its 16 hash-verified runtime dependencies, then checked outside the source checkout using isolated Python. Both complete themes, referenced images, homepage, CSS, JavaScript and pinned HTMX runtime were available.

Engine coverage is **95.40% of branches (311/326)** and 98.13% of statements (736/750); the combined measure is 97.30%. The independent branch gate fails below 90% even when statement coverage is 100%. Two upstream Starlette/httpx and AnyIO deprecation warnings are visible; no warnings are suppressed.

## Requirement evidence

| Accepted criterion | Evidence in the passing suites |
| --- | --- |
| All 26 Kingdom and seven basic definitions | `tests/test_engine_rules.py`: independently specified effects, reactions before attack benefits, repeated/nested actions, empty piles, partial gains, cleanup, scoring and ties |
| State invariants and rejection | Hypothesis legal sequences conserve stock and unique card IDs; invalid, stale and duplicate commands leave the input unchanged; resources stay nonnegative |
| Determinism and recovery | Every action's pending choices round-trip; nested attack continuations, replayed commands, bot randomness and a reopened SQLite service produce equivalent future states |
| Private information | Engine projections hide hands, deck order, discard interiors and inspected cards; public events, HTML and bot inputs are tested; the full review's private-recovery finding was reproduced and fixed |
| Atomic storage | `tests/test_storage.py`: concurrent independent connections, revision rejection, idempotent repeats, rollback after forced transaction failure, reopening and original-save preservation |
| Browser decisions | Chromium covers complete play to scoring, card/supply/yes-no/menu choices, ordered subsets, local selection, keyboard controls, stale tabs, reactions during bot turns and reload; web integration tests cover duplicate submission |
| Themes | Both 33-definition packs validate; rendering escapes names and rejects unsafe assets/tokens; theme switching preserves rules, history labels and pending local selection; missing/invalid packs recover safely |
| Opponents | All three profiles finish representative seeded games with two, three and four players; every decision shape has legal-choice coverage; the simulation CLI reports exhausted budgets as unfinished |
| Quality and packaging | Shared scripts, strict types, meaningful branch threshold and independent installed-wheel gate above; local Chromium and Linux CI pass |
| Reviews | [Full review](review/2026-09-22-0934-full.md) followed by [incremental verification](review/2026-09-22-0945-incremental.md); all four inherited findings fixed and no unresolved findings |

The home screen and both game themes were also inspected visually at the final browser commit `adc8b09`; no blocking clipping or overlap was found. These checks establish the tested release scope rather than a guarantee against every possible defect.

## Delivery and remaining scope

The local implementation is on `main`: [#1 foundation](https://github.com/vhata/sway/pull/1), [#2 engine](https://github.com/vhata/sway/pull/2), [#3 bots](https://github.com/vhata/sway/pull/3), [#4 storage](https://github.com/vhata/sway/pull/4), [#5 service](https://github.com/vhata/sway/pull/5), [#6 browser](https://github.com/vhata/sway/pull/6), [#7 quality gates](https://github.com/vhata/sway/pull/7) and [#8 release review](https://github.com/vhata/sway/pull/8). The engine's reviewed squash was recovered from its previous base onto `main` as `9d06829` with explicit user authorization. Later merged changes include development terminology, setup recovery, card illustrations and explicit human-controller support. The dated checks above remain the original 2026-09-22 release evidence; they are not results for those later changes. No deployment or release tag has been performed.

The local application retains its one-human, no-account workflow. Separate invite-only multiplayer work and its review status are recorded in [hosted acceptance evidence](docs/HOSTED_ACCEPTANCE.md); it does not publish local saves. [TODO.md](TODO.md) retains remaining product work. [ARCHITECTURE.md](ARCHITECTURE.md#postgresql-transition) requires PostgreSQL before multiple application servers share games and specifies transfer, verification, cutover and rollback. Original presentation and the [terminology map](docs/TERMINOLOGY.md) do not constitute legal clearance.
