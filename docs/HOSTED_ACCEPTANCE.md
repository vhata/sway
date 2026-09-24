# Invite-only multiplayer acceptance evidence

Recorded on 2026-09-24 for source commit `494c04f`, with hosted HTTPS browser acceptance still pending. The implementation is proposed in four **draft, unmerged PRs**: [#14 identity and storage](https://github.com/vhata/sway/pull/14), [#15 multiplayer service](https://github.com/vhata/sway/pull/15), [#16 hosting operations](https://github.com/vhata/sway/pull/16) and [#17 browser play](https://github.com/vhata/sway/pull/17). No deployment or release tag has been performed. The historical local release checks remain in [ACCEPTANCE.md](../ACCEPTANCE.md).

[Multiplayer contracts](MULTIPLAYER.md) describe the behavior; [hosted storage](HOSTED_STORAGE.md) defines identity and transaction semantics; [hosting instructions](HOSTING.md) own deployment and recovery procedures. This record documents verification rather than adding operational rules.

## Completed checks

Counts at successive component heads include inherited tests; they are not additive.

| Scope | Recorded outcome |
| --- | --- |
| Identity and storage, `cc4a341` | 304 unit/integration tests passed, including 22 identity tests; strict types, formatting/lint, package build and installed-wheel smoke passed |
| Multiplayer service, `67b0989` | 322 unit/integration tests passed, including 18 hosted service tests |
| Hosting operations, `87ddcd5` | 369 unit/integration tests passed, including 47 hosting configuration and backup tests |
| Combined implementation | `scripts/check.sh` passed all gates: 379 unit/integration tests, formatting/lint, strict types, coverage, source/wheel builds and isolated installed-wheel smoke |
| Existing local browser acceptance | 19 Chromium tests passed in 35.88 seconds |
| Independent HTTP review | 10 hosted HTTP tests passed; the stale-CSRF reproduction was rerun successfully after correction |
| Independent browser control review | Chromium confirmed that offline selection keeps confirmation disabled and an unchanged successful update restores a valid selection |

The engine branch result remains **95.40% (311/326)**; statements remain 98.13% (736/750). No coverage threshold was lowered. Local validation used macOS, Python 3.12.14, uv 0.12.17, locked dependencies and separate worktree environments. Chromium required permission to launch outside the process sandbox; installing locked runtime dependencies for the wheel probe required network access. Existing upstream Starlette/httpx and AnyIO deprecation warnings remain visible.

## Behavior and review evidence

| Contract | Evidence |
| --- | --- |
| Persistent guest identity | [Identity tests](../tests/test_hosted_identity.py) cover fixed expiry, session revocation, single-use recovery across separate processes, principal creation races, caller rollback, reopening and hash-only persisted credentials |
| Private table ownership | [Service tests](../tests/test_hosted_service.py) and [HTTP tests](../tests/test_hosted_web.py) cover seat invitations, readiness, two- to four-player tables, membership-scoped access and filtered decisions; unknown and inaccessible tables share the same response |
| Atomic commands and progress | Service tests cover revision conflicts, identical retries, reaction ownership, durable bot decisions and recovery without browser-driven mutation; browser requests retain the same decision payload for an uncertain retry |
| Request boundary | HTTP tests cover exact origin/host checks, CSRF, body/rate limits, secure session cookies, private response headers and recovery revoking an old browser |
| Separate and recoverable storage | [Configuration tests](../tests/test_hosted_config.py) and [backup tests](../tests/test_hosted_backup.py) cover local/hosted separation, process ownership, private files, live-WAL backups, whole-database relationships, format validation and refusal to overwrite existing paths |
| Local compatibility | Existing local browser acceptance passed; local storage and the no-account entrypoint remain separate from hosted identity |

Independent review found and corrected these concrete failures before acceptance:

- Existing hosted database paths now reject permissive files and symlinks before SQLite opens them, without changing original files or permissions. The regression passed at `cc4a341`.
- Backup creation now refuses preexisting SQLite sidecars, including broken symlinks, before opening the destination. The original reproduction confirmed preservation of unrelated sidecar bytes. Unknown or newer component schemas are rejected during copy verification.
- Submitting an old CSRF form after another tab changes the session now returns 403 while preserving the valid current cookie. Invalid or revoked sessions still lose access. The original HTTP reproduction passed at `34a9e4e`.
- Polling and submissions are serialized; a submission during polling is retained, and reconnects restore confirmation state after an unchanged response. The shared selection handler respects the connection lock. Independent Chromium verification passed at `34a9e4e`.

Real HTTPS browser investigation also exposed native form submissions losing the required Origin under `Referrer-Policy: no-referrer`. Commit `494c04f` uses `same-origin`, preserving same-origin submission behavior while suppressing cross-origin referrers. The corresponding hosted browser acceptance remains pending below; the policy change is not evidence that an actual deployment proxy has been tested.

## Pending acceptance and deployment limits

Hosted HTTPS browser tests are still being completed. This snapshot does **not** claim passing end-to-end coverage for the complete invitation, recovery, concurrent-tab, reaction, reconnect and background-bot flows. Record the final source commit and actual hosted/browser suite outcomes before closing that gate.

The complete PR stack remains subject to user review before landing. There has been no public deployment, release tag or production TLS/proxy verification. Deployment-specific host/origin rejection, cookie behavior through the actual TLS proxy, backup/restore rehearsal and operational monitoring remain the acceptance checks in [HOSTING.md](HOSTING.md#deployment-acceptance).

The supported architecture is one process with SQLite on one server. These checks do not establish distributed-worker safety, PostgreSQL compatibility, account verification, public matchmaking or resistance to every abuse scenario.
