# Private multiplayer hosting

Hosted Sway uses a separate application and database from the local game. The
initial supported deployment is **one process, one worker, one SQLite database on
local disk**, behind a TLS reverse proxy. Do not expose the local `sway.web:app`,
share the database over a network filesystem, or run multiple application workers.
Public matchmaking, account verification and distributed workers are outside this
release. Review the complete multiplayer PR stack before deploying it.

## Configuration and launch

Install the locked Python 3.12 environment with `uv sync --locked`. Run the server
as a dedicated, unprivileged OS account. Create a private data directory outside
the source checkout and outside any static/document root:

```sh
install -d -m 700 /srv/sway-hosted
export SWAY_HOSTED_ORIGIN=https://sway.example.com
export SWAY_HOSTED_DATA_DIR=/srv/sway-hosted
scripts/hosted.sh
```

The account must own the data directory. The application stores all hosted
identity, invitation, session, lobby and game records in `hosted.sqlite3` there.
Keep the database and any SQLite journal/WAL files private. The launcher uses
`umask 077`; startup rejects a data directory accessible to other users.

`SWAY_HOSTED_ORIGIN` is the exact public HTTPS origin, without a trailing slash,
path, query, fragment, username or password. Use lowercase ASCII DNS names (IDNs
must already be ASCII/punycode). Omit the default `:443`; an explicit nonstandard
HTTPS port is supported. Allowed hosts are derived from this origin. Hosted and
local directories must not overlap, including through symlinks. Local storage is
`SWAY_DATA_DIR`, or `~/.local/share/sway` when unset. Existing local databases are
never imported automatically. Do not move or retarget storage symlinks while the
server runs.

The launcher's optional `SWAY_HOSTED_PORT` changes the **loopback backend** port
(default 8000). It accepts no command-line overrides and starts exactly one
worker without reload or access logging. A lifetime OS lock on `.server.lock`
refuses a second hosted process using the same directory and releases after a
crash; never remove or replace this lock file while a server is running. The hosted web application is
`sway.hosting.web:create_app`; deployment requires the browser/application PR in
the multiplayer stack as well as these operations tools.

## TLS proxy and request boundary

Terminate TLS at a maintained reverse proxy on the same machine, forward traffic
to `127.0.0.1:8000`, preserve the public `Host` header including any nonstandard
port, and restrict the public listener to the configured host. Keep the backend
port inaccessible from other machines. Redirect HTTP to HTTPS at the proxy and
set an appropriate HSTS policy after validating TLS.

Forwarded headers do not establish trust: the launcher disables proxy-header
processing, and `SWAY_TRUSTED_PROXY_IPS` must be unset or empty. The application
compares mutation `Origin` headers with the configured HTTPS origin independently
of backend HTTP and forwarded headers. Cookies are Secure, HttpOnly and host-only.
Do not strip or rewrite browser Origin headers. Avoid caches on all application
routes; private responses carry `Cache-Control: no-store`.

Bound request bodies, connection counts and timeouts at the proxy as well as the
application. The application defaults are:

| Environment variable | Default | Purpose |
| --- | ---: | --- |
| `SWAY_HOSTED_MAX_REQUEST_BYTES` | 65536 | Maximum request body size |
| `SWAY_HOSTED_MUTATIONS_PER_MINUTE` | 60 | Mutation rate budget |
| `SWAY_HOSTED_CREDENTIALS_PER_MINUTE` | 10 | Join/recovery/identity rate budget |
| `SWAY_HOSTED_MAX_RATE_LIMIT_KEYS` | 10000 | Bound in-memory rate-limit tracking |

Private page and update reads share a separate 300-per-minute budget per socket peer. Public bundled assets do not consume that budget; apply asset and connection limits at the proxy.

Limits must be positive integers. They are per-process abuse controls, reset on
restart, and supplement proxy limits. With forwarded headers disabled, connections
through the same proxy share its network identity; do not solve this by trusting
arbitrary `X-Forwarded-For` headers. Size edge limits for the invited group and
monitor denied requests without recording their contents.

Disable sensitive request logging in both proxy and application. Never log
cookies, invitation/recovery credentials, form bodies, private choices, rendered
boards or snapshots. Invitation secrets belong in URL fragments, which browsers
do not send to HTTP servers; never transform them into query strings or redirects.
Recovery codes and backup copies need the same protection as live credentials.

## Backup and restore

Back up before deploying an application/schema update. Keep encrypted off-machine
copies with a deliberate retention policy and restricted access. A backup includes
valid session and recovery hashes, memberships and private game state; it is not
safe to publish or attach to a bug report.

Create a private backup directory, then take a consistent snapshot while the
server is running:

```sh
install -d -m 700 /srv/sway-backups
uv run --locked python -m sway.hosting.backup backup \
  /srv/sway-hosted/hosted.sqlite3 /srv/sway-backups/before-update.sqlite3
```

The destination must not exist. This uses SQLite's online backup API, copies all
tables together, verifies the hosted database format, `integrity_check` and
`foreign_key_check`, and produces a self-contained mode-0600 file. It never copies
just a live main file while committed changes remain in its WAL. Copying times out
after 30 seconds of sustained contention; retry during quieter activity. Failed
copies are removed; the source and any existing destination are preserved.

Restore **with the application stopped**, into a fresh private data directory:

```sh
install -d -m 700 /srv/sway-restored
uv run --locked python -m sway.hosting.backup restore \
  /srv/sway-backups/before-update.sqlite3 /srv/sway-restored/hosted.sqlite3
export SWAY_HOSTED_DATA_DIR=/srv/sway-restored
scripts/hosted.sh
```

Restore refuses to overwrite any existing path, including symlinks. It uses the
same verified copy procedure; it does not modify schemas or merge databases.
Keep the original directory intact until verification is complete. Never copy
restored data over a running database or remove WAL files from a running server.
Use an application version compatible with the backup; unsupported database
formats fail without rewriting the original. Rolling back a database also rolls
back credential rotations and revocations: old sessions and recovery codes may
become valid again. Restrict access during recovery and rotate/revoke affected
credentials before reopening the service.

Rehearse recovery on an isolated loopback instance before relying on backups:
verify that the creator and another human recover their own memberships, that a
pending reaction remains owned by the correct player, and that neither sees the
other's hidden cards. Automated backup tests cover consistent live-WAL snapshots,
identity/game relationships, format rejection, protected files and overwrite
refusal. They do not replace a deployment-specific restore drill.

## Deployment acceptance

Before inviting players, verify TLS and host rejection through the actual proxy;
check that cross-origin mutations fail and no cookie or private response can be
cached. Exercise join, recovery, independent browsers, concurrent choices and a
restart at a human reaction. Confirm background bots resume without an open tab,
and that revoking a session clears the private board on its next request. Monitor
disk space and failed bot jobs without exporting private data. A second process
must not be used to improve throughput: distributed ownership and the PostgreSQL
transition require separate implementation and crash-recovery checks.
