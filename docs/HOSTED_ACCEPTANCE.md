# Invite-only multiplayer acceptance evidence

## Dual-hosting verification — 2026-09-25

The revised stack supports the shared hosted application on a laptop/VM and Cloudflare Python Workers. [#14](https://github.com/vhata/sway/pull/14) and [#15](https://github.com/vhata/sway/pull/15) provide portable atomic state callbacks; [#16](https://github.com/vhata/sway/pull/16) retains self-hosted operations and defines runtime contracts; [#17](https://github.com/vhata/sway/pull/17) assembles the shared browser application; [#20](https://github.com/vhata/sway/pull/20) adds the Cloudflare adapter. All remain pending user review and landing. No production deployment or release tag has been performed.

| Scope | Executed outcome |
| --- | --- |
| Combined quality gates at `9825e2e` | `scripts/check.sh` passed: 388 unit/integration tests, formatting/lint, strict typing, both coverage gates, builds and installed-wheel smoke |
| Engine coverage | Statements 98.13% (736/750); branches 95.40% (311/326); no threshold change |
| Native browser at `2424b13` | All 30 browser-suite cases passed in 56.36 seconds, including the deterministic privacy-assertion regression |
| Worker browser parity | The identical two-, three- and four-player scenarios passed against actual local workerd; direct run 8.26 seconds and final integrated wrapper run 8.27 seconds at `13cd083` |
| Shared persistence contract | The same assertions passed on native SQLite and real Durable Object storage, including rollback, foreign keys, invitation/session/recovery semantics, private views, stale revisions and command receipts |
| Cloudflare scheduling | Real workerd checks passed nested SQL/alarm rollback, concurrent transactions, alarm delivery and bot progress after stopping with a future alarm pending and restarting on the same storage |
| Shared runtime isolation | Tests passed with threadpool execution forbidden and `fcntl` unavailable |

The adapter/source and required CI integration were verified at `13cd083`; rebasing onto the privacy-test correction produced `4243eaa` with no production-code changes. The Cloudflare test wrapper `scripts/cloudflare-check.sh --browser` builds its own test-only Worker, owns isolated local state and processes, verifies readiness with a run nonce, and launches the shared browser scenarios against the actual application. It does not deploy. Native development uses Python 3.12; the pinned Workers compatibility date selects Python 3.14. Dependency environments and locks remain separate.

Independent review covered the portable state refactor, runtime extraction, integrated native application, Cloudflare adapter, check tooling, CI and documentation; the reviewer was separate from each code author. Review found one adapter mismatch: SELECT reported a prior write's affected-row count. The author corrected it and added an assertion exercised by both storage backends. No actionable findings remain in those reviewed scopes.

### Verification limitations and retained evidence

CI at the documentation head exposed a false positive in the reaction privacy assertion: the private card ID `c32` occurred inside an unrelated random CSRF token. The correction at `2424b13` checks complete identifiers across the entire HTML response. A deterministic regression accepts the exact token collision while rejecting card IDs in form values, arbitrary attributes, embedded JSON and text. That regression and the native reaction/restart scenario passed together (2 cases); independent review found no actionable findings. The full browser suite now contains 30 cases. Production code and timeouts are unchanged. The original failed CI log is retained at `/private/tmp/sway-dual-ci19-failure.log`.

An initial native browser run passed nine cases before the existing complete-game scenario timed out. Its preserved trace showed about 48 seconds of browser/input inactivity before the request was sent; the server then replied successfully in 18 ms and advanced revision 12 to 13. No application or JavaScript exception was found. The isolated scenario passed unchanged in 35.19 seconds, and the complete 29-case rerun passed unchanged. The stall's underlying cause remains unproven. Original trace, database and logs were preserved at `/private/tmp/sway-dual-failure-6Aj78SC9` before any rerun; no timeout or assertion was weakened.

The first direct Cloudflare browser run passed the two- and three-player cases but the four-player case reached the real default request budget: an already-running Wrangler process had not loaded newly created test overrides. Restarting with explicit test-only limit arguments made all three cases pass. The reproducible wrapper now supplies those arguments when launching its isolated application; production defaults are unchanged.

Local workerd evidence does not establish a real Cloudflare deployment, remote recovery, production capacity or TLS/origin setup. Self-hosted deployment acceptance also remains operator work. One Durable Object contains the complete Cloudflare installation, so its capacity bounds apply to all hosted games. Runtime selection does not migrate existing identities or games; cross-runtime export/import is deferred in [TODO](../TODO.md). The original single-human local application remains separate.

## Historical single-server verification — 2026-09-24

The following record retains the original source revisions and outcomes; it is not Cloudflare validation.

Verified on 2026-09-24 for source commit `47d7d6c`. The implementation is recorded in four focused PRs: [#14 identity and storage](https://github.com/vhata/sway/pull/14), [#15 multiplayer service](https://github.com/vhata/sway/pull/15), [#16 hosting operations](https://github.com/vhata/sway/pull/16) and [#17 browser play](https://github.com/vhata/sway/pull/17). No deployment or release tag has been performed. The historical local release checks remain in [ACCEPTANCE.md](../ACCEPTANCE.md).

[Multiplayer contracts](MULTIPLAYER.md) describe the behavior; [hosted storage](HOSTED_STORAGE.md) defines identity and transaction semantics; [hosting instructions](HOSTING.md) own deployment and recovery procedures. This record documents verification rather than adding operational rules.

### Completed checks

Counts at successive component heads include inherited tests; they are not additive.

| Scope | Recorded outcome |
| --- | --- |
| Identity and storage, `cc4a341` | 304 unit/integration tests passed, including 22 identity tests; strict types, formatting/lint, package build and installed-wheel smoke passed |
| Multiplayer service, `67b0989` | 322 unit/integration tests passed, including 18 hosted service tests |
| Hosting operations, `87ddcd5` | 369 unit/integration tests passed, including 47 hosting configuration and backup tests |
| Combined implementation | `scripts/check.sh` passed all gates: 381 unit/integration tests, formatting/lint, strict types, coverage, source/wheel builds and isolated installed-wheel smoke |
| Existing local browser acceptance | 19 Chromium tests passed in 35.88 seconds |
| Hosted HTTPS browser acceptance | 10 Chromium scenarios passed in 12.57 seconds, including two-, three- and four-human tables |
| Final integrated browser acceptance | `scripts/e2e.sh -x -v` passed all 29 Chromium cases in 70.43 seconds at `47d7d6c` |
| Independent HTTP review | 12 hosted HTTP tests passed; stale-CSRF, static-asset rate budgets and invalid setup corrections were reproduced and verified |
| Independent browser control review | Chromium confirmed that offline selection keeps confirmation disabled and an unchanged successful update restores a valid selection |

The engine branch result remains **95.40% (311/326)**; statements remain 98.13% (736/750). No coverage threshold was lowered. Local validation used macOS, Python 3.12.14, uv 0.12.17, locked dependencies and separate worktree environments. Chromium required permission to launch outside the process sandbox; installing locked runtime dependencies for the wheel probe required network access. Existing upstream Starlette/httpx and AnyIO deprecation warnings remain visible.

### Behavior and review evidence

| Contract | Evidence |
| --- | --- |
| Persistent guest identity | [Identity tests](../tests/test_hosted_identity.py) cover fixed expiry, session revocation, single-use recovery across separate processes, principal creation races, caller rollback, reopening and hash-only persisted credentials |
| Private table ownership | [Service tests](../tests/test_hosted_service.py) and [HTTP tests](../tests/test_hosted_web.py) cover seat invitations, readiness, two- to four-player tables, membership-scoped access and filtered decisions; unknown and inaccessible tables share the same response |
| Atomic commands and progress | Service tests cover revision conflicts, identical retries, reaction ownership, durable bot decisions and recovery without browser-driven mutation; browser requests retain the same decision payload for an uncertain retry |
| Browser transport and privacy | [HTTPS browser tests](../tests/e2e/test_hosted_browser.py) cover native signup and fragment invitations, same-choice theme changes, lost-response exact retries, delayed polls, offline recovery, revoked sessions, three-viewer reactions across process restart and bot startup with no open tab |
| Request boundary | HTTP tests cover exact origin/host checks, CSRF, body/rate limits, secure session cookies, private response headers and recovery revoking an old browser |
| Separate and recoverable storage | [Configuration tests](../tests/test_hosted_config.py) and [backup tests](../tests/test_hosted_backup.py) cover local/hosted separation, process ownership, private files, live-WAL backups, whole-database relationships, format validation and refusal to overwrite existing paths |
| Local compatibility | Existing local browser acceptance passed; local storage and the no-account entrypoint remain separate from hosted identity |

Independent review found and corrected these concrete failures before acceptance:

- Existing hosted database paths now reject permissive files and symlinks before SQLite opens them, without changing original files or permissions. The regression passed at `cc4a341`.
- Backup creation now refuses preexisting SQLite sidecars, including broken symlinks, before opening the destination. The original reproduction confirmed preservation of unrelated sidecar bytes. Unknown or newer component schemas are rejected during copy verification.
- Submitting an old CSRF form after another tab changes the session now returns 403 while preserving the valid current cookie. Invalid or revoked sessions still lose access. The original HTTP reproduction passed at `34a9e4e`.
- Polling and submissions are serialized; a submission during polling is retained, and reconnects restore confirmation state after an unchanged response. The shared selection handler respects the connection lock. Independent Chromium verification passed at `34a9e4e`.

Real HTTPS browser investigation also exposed native form submissions losing the required Origin under `Referrer-Policy: no-referrer`. Commit `494c04f` uses `same-origin`, preserving same-origin submissions while suppressing cross-origin referrers. The signup/invitation scenarios verify the correction in Chromium.

Repeated independent browser identities also exposed bundled scripts being throttled by the private-page read budget, preventing invitation-fragment removal. Commit `e1819e6` excludes public asset reads from that budget while retaining host checks and private/credential limits. A regression test exhausts private reads while proving scripts remain available; the multi-browser scenarios verify successful invitation handling.

Independent integration drills verified HTTP identity and private-view continuity through live backup, fresh-directory restore and recovery; exclusive application lifetime locking; bot-first startup without an enqueue or browser; and target-only reaction HTML/poll responses before and after restart. Mobile screenshots and geometry checks at 320 and 390 pixels showed readable signup, recovery, lobby and game layouts without horizontal overflow.

### Observed verification limitation

One combined browser run executed alongside coverage failed the existing full-game test after the command committed revision 151 while the browser assertion still observed revision 150. That run was interrupted after 17 passing cases. The failed trace was cleared by the next pytest run, so the precise transport/render cause is unconfirmed. An independent isolated reproduction passed in 28.55 seconds, and the final integrated 29-case run passed without code or timeout changes. Preserve a failed trace before rerunning if this recurs; no assertion or quality gate was weakened.

### Deployment limits

There has been no public deployment, release tag or production TLS/proxy verification. Deployment-specific host/origin rejection, cookie behavior through the actual TLS proxy, backup/restore rehearsal and operational monitoring remain the acceptance checks in [HOSTING.md](HOSTING.md#deployment-acceptance).

The supported architecture is one process with SQLite on one server. These checks do not establish distributed-worker safety, PostgreSQL compatibility, account verification, public matchmaking or resistance to every abuse scenario.
