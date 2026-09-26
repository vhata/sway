# Cloudflare deployment

The shared hosted application runs in one Python Durable Object per installation.
Identity, rooms and command receipts stay in the same SQLite transaction domain.
This supports a small invite-only installation, not arbitrary horizontal scaling:
all requests and bot execution share one object's compute and storage limits.
Self-hosting continues to use `scripts/hosted.sh` with its SQLite directory.
Changing launchers does not transfer existing players or games between stores.

## Local development

Install the repository's pinned uv, Node.js (22 or newer), and run from the repo:

```sh
scripts/cloudflare.sh
```

This prepares separate locked tool/dependency environments, copies the shared
application into the Worker bundle and starts HTTPS at `https://localhost:8799`.
The local TLS certificate is self-signed. Production still requires valid HTTPS.
The local state lives in `deployment/cloudflare/.wrangler/`; do not commit it.

The root project stays on Python 3.12. Workers compatibility date `2026-09-25`
selects Python 3.14; `pywrangler` prepares that native/Pyodide environment itself.
`uv.lock` pins development tools, `pylock.toml` pins WebAssembly runtime packages,
and `package-lock.json` pins Wrangler/workerd. Keep all three with dependency
changes. Root application dependencies and deployment dependencies are separate
because the native package declares Python 3.12 and includes Uvicorn.

## Configuration and deployment

`wrangler.jsonc` binds `INSTALLATION` to the SQLite class `Installation`; its
stable object name is `installation`. Do not change this name to scale or reset
state: that would create a different installation. `ASSETS` contains only public
files; the application still checks Host and attaches security headers before
serving them. Themes are also bundled for server-side validation/rendering.

Set `SWAY_HOSTED_ORIGIN` to the canonical HTTPS origin in the target Wrangler
configuration. The optional request limits use the same names as self-hosting:
`SWAY_HOSTED_MAX_REQUEST_BYTES`, `SWAY_HOSTED_MUTATIONS_PER_MINUTE`,
`SWAY_HOSTED_CREDENTIALS_PER_MINUTE`, `SWAY_HOSTED_MAX_RATE_LIMIT_KEYS`.
Defaults are 65536, 60, 10 and 10000 respectively. Local `.dev.vars` overrides
are ignored by Git; never increase production limits merely to make tests pass.

After reviewing the target configuration and authenticating Wrangler, an
operator can run `scripts/cloudflare.sh deploy`. No deployment is performed by
checks. The test-only `wrangler.test.jsonc` is never a deployment configuration.

## Durability and operations

Every application operation runs in an outer Durable Object transaction; each
shared SQL callback also uses `transactionSync` for exception rollback. Pending
bot work and its alarm commit atomically. Alarms process at most four tables per
invocation, with the service's existing per-table decision/time limits. They
reschedule only while pending work exists. Repeated delivery is safe through
revision checks; storage/compute failures throw so Cloudflare can retry.

Request limits persist through object eviction. Peer identity comes from
Cloudflare's `CF-Connecting-IP`, forwarded internally after overwriting the
private header. Arbitrary client `X-Forwarded-For` is never trusted. The durable
limiter currently uses a bounded fixed 60-second window; the native limiter uses
a sliding window. Both are abuse controls, not account authorization.

Workers observability is disabled in the supplied configuration because route
paths may include invitation IDs. Do not enable full request tracing or log
cookies, bodies, recovery codes or invitation secrets. Unexpected edge errors
return a generic body and log only the exception type.

Use Cloudflare's Durable Object point-in-time recovery for cloud storage. Native
SQLite backup/restore commands apply only to self-hosted installations. A
cross-platform export/import utility is not implemented by this adapter.

## Verification

Run `scripts/cloudflare-check.sh` from the repository root (no account login or
deployment). It owns a temporary local server and state directory, checks alarm
and bot progress, restarts workerd and checks persistence. Set
`SWAY_CLOUDFLARE_TEST_PORT` to change its default port 8798. After installing
Chromium with `scripts/install-browsers.sh`, run
`scripts/cloudflare-check.sh --browser` to also start the full HTTPS application
on port 8800 (contract port plus two) and run the same two-, three- and four-player
browser flows used for self-hosting. Only that synthetic test process receives
higher request limits.

The reusable `contract_checks.py` runs against native SQLite in pytest and against
real local workerd storage through the test-only Worker. It covers transaction
rollback and foreign-key integrity, session/recovery rotation, invitation consumption and guest rollback,
private views, membership, stale commands and receipt replay. The Worker also
checks nested SQL/alarm rollback, concurrent transactions and alarm delivery.

Live Cloudflare account deployment and remote recovery remain operator release
checks; successful local workerd tests do not establish those outcomes.

Sources: [Python Workers](https://developers.cloudflare.com/workers/languages/python/),
[SQLite transactions](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/),
[alarms](https://developers.cloudflare.com/durable-objects/api/alarms/).
