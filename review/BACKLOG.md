# Review backlog

Only work promoted from whole-codebase reviews belongs here. Entries are ready for separate work and grouped by priority, without TODO workflow stages. Follow [review guidance](../docs/CODE_REVIEW_GUIDE.md) and [claim/resolution rules](../docs/TODO_GUIDE.md).

The [2026-10-08 full review](2026-10-08-0723-full.md) promoted the entries below. Its remaining findings are retained as inventory in that snapshot.

## P0 Critical

## P1 High

## P2 Normal

## P3 Low

## Unprioritized

- [BACKEND] `hosted-bot-scan-resilience` — **Keep one undecodable room from stopping hosted bots or the Cloudflare installation.** The pending-bot scan deserializes every candidate room, so one unloadable snapshot halts self-hosted bot scheduling and fails every Cloudflare request.
  - Starting point: Isolate decode failures per room in `HostedService.pending_bot_games` and `_step_bot` (pause and report that room), and arm the Cloudflare alarm from a cheap SQL existence check. Reproduce with a room whose snapshot has an unsupported version.
  - Source: review/2026-10-08-0723-full.md, 2026-10-08
  - Findings: `pending-bot-scan-undecodable-room`

- [BACKEND] `anonymous-session-retention` — **Purge expired hosted sessions.** Every cookieless page load stores an anonymous session row that is never deleted, so storage grows without bound in one installation database or Durable Object.
  - Starting point: Delete expired sessions in bounded batches on an existing write path or bot alarm. Verify that row counts stay bounded under repeated cookieless requests on both runtimes.
  - Source: review/2026-10-08-0723-full.md, 2026-10-08
  - Findings: `anonymous-sessions-never-purged`

- [TOOLING] `privacy-and-csrf-regression-tests` — **Make privacy and CSRF tests fail on real regressions.** Making hidden draws public or removing CSRF checks from three local routes leaves the suite green.
  - Starting point: Assert event audiences per kind (draw, Library keep, Sentry order, Artisan topdeck) and rendered history by card name; cover CSRF/Origin rejection on every local mutating route; replace the instance-ID HTML assertion. Demonstrate each new test against the corresponding mutation.
  - Source: review/2026-10-08-0723-full.md, 2026-10-08
  - Findings: `private-event-audience-untested`, `local-mutation-csrf-untested`, `html-privacy-assertion-vacuous`

- [UI] `refresh-preserves-local-ui-state` — **Preserve open panels, unsaved lobby setup and focus across automatic refreshes.** Bot-turn and lobby refreshes collapse disclosure panels, discard the host's setup edits and move keyboard focus.
  - Starting point: Extend `app.js` swap handling to restore `details` state and focus for controls without IDs, and avoid replacing an in-progress lobby setup form. Add Chromium tests for both refresh paths.
  - Source: review/2026-10-08-0723-full.md, 2026-10-08
  - Findings: `lobby-refresh-discards-setup-edits`, `local-refresh-collapses-panels-and-focus`

- [TOOLING] `daily-and-ci-evidence-fidelity` — **Make daily seeds, PR triggers and failure evidence behave as documented.** The daily Hypothesis seed is ignored on Actions, recovery-worker changes skip the daily PR run, and Quality may omit evidence on timeout.
  - Starting point: Disable Hypothesis derandomization for the daily lane or correct QUALITY.md, add `deployment/cloudflare/recovery/**` to the daily PR paths, and upload Quality evidence on any non-success. Obtain explicit authorization for CI changes first.
  - Source: review/2026-10-08-0723-full.md, 2026-10-08
  - Findings: `daily-hypothesis-seed-ignored`, `daily-pr-filter-misses-recovery-sources`, `quality-evidence-skipped-on-timeout`

- [TOOLING] `quality-gate-configuration` — **Align lint, smoke-test, hook and type-check configuration with QUALITY.md.** Biome lint has no rules enabled, the wheel smoke guard can skip silently, a declared pre-push hook never runs and Workers Python is outside strict typing without explanation.
  - Starting point: Choose and enable a Biome rule set (fix or justify current hits), align the install-smoke guard with the other foundation guards, remove or wire the dead hook declaration, and document or narrow the type-check scope.
  - Source: review/2026-10-08-0723-full.md, 2026-10-08
  - Findings: `biome-lint-no-rules`, `install-smoke-single-path-guard`, `dead-pre-push-hook-config`, `workers-python-type-gate-scope`
