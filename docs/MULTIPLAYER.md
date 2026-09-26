# Invite-only multiplayer design and implementation

**Implemented as a separate hosted application with two runtime adapters.** The original [local release](../SPEC.md) keeps its one-human, no-account workflow. The hosted identity, service and browser layers share the contracts below across laptop/VM self-hosting and Cloudflare Python Workers. [HOSTING.md](HOSTING.md) describes deployment choices and self-hosted recovery; the [Cloudflare guide](../deployment/cloudflare/README.md) covers that runtime. Platform-specific validation is recorded in [hosted acceptance evidence](HOSTED_ACCEPTANCE.md). These changes do not publish a real endpoint or establish production recovery readiness.

## Scope and defaults

A private table has two to four seats, at least one human, and independently selected bots in the remaining seats. The creator occupies a human seat and manages the lobby. There is no public game directory, spectator access, chat, matchmaking or turn timer. Display names are labels, not authentication. This is casual play between invited people; it does not establish real-world identity or prevent collusion.

The host chooses the supply and seat arrangement before play. Hosted games generate their gameplay seed on the server and keep it secret: the current local seed field would let a participant reproduce hidden shuffles. Supply randomization uses a separate random source. Seeds, bot memory and authoritative snapshots never enter browser responses.

## Application boundaries

| Boundary | Implementation |
| --- | --- |
| [Engine `view_for` and `advance`](../src/sway/engine/core.py) already support any player index and nested decisions. | Keep rules and serialization independent of identity and transport. Resolve authorization before calling them. |
| [GameService](../src/sway/service.py) supports configured human seats and seat-indexed bot snapshots. | [HostedService](../src/sway/hosting/service.py) resolves seats from authenticated membership and reads room, preference and snapshot data consistently. |
| [StateStore](../src/sway/hosting/state.py) provides synchronous read/write callbacks through a typed SQL session. | Self-hosted SQLite and Cloudflare Durable Object adapters keep rooms, identities, memberships, invitations, preferences and receipts in one transaction boundary; raw snapshots and history remain internal. |
| [Hosted web routes](../src/sway/hosting/web.py) authenticate every private page, update and mutation. | Shared card components receive filtered views; hosted waiting states distinguish human decisions and paused bots. Themes use viewer preferences, while the separate local routes retain local save discovery. |

## Identity, invitations and reconnects

Use a server-issued guest principal rather than passwords or an identity-provider dependency for this scope. Authentication proves possession of a credential for that principal; it does not trust a posted player index, display name or game ID.

Join, recovery and first-time table creation begin with a short-lived anonymous session for CSRF protection. Only an explicit POST creates or restores a principal; replace the anonymous session with a fresh authenticated session after success and show a new principal's recovery code.

| Record | Contract |
| --- | --- |
| Principal | Stable opaque ID. At most one human membership per game. Display-name edits cannot change ownership. |
| Session | Independent random 256-bit bearer token per browser, stored hashed server-side and delivered in a `Secure`, `HttpOnly`, `SameSite=Lax`, host-only cookie with path `/`. Fixed 30-day lifetime; revocable individually or for the whole principal. |
| Recovery code | Separate random 256-bit credential, shown once for the player to save and stored only as a hash. Redeeming it restores the same principal, rotates the code and revokes all prior sessions atomically. A normal reload with a valid session needs no recovery code. |
| Invitation | Random 256-bit secret bound to one unoccupied human seat, stored hashed, single-use, expiring after 24 hours. Host can revoke/reissue before play. Possession authorizes the first claim; forwarding an invitation delegates that access. |

Invitation links use a public invitation ID and put the secret in the URL fragment. The join page removes the fragment from browser history, retains it only in memory, and waits for an explicit **Join table** POST. A preview/GET never claims a seat. The POST validates same-origin CSRF protection, expiry and availability, then atomically consumes the invitation and binds the current or newly created principal to the seat. Concurrent claims have one winner. A retry by that same principal returns its existing membership; another principal receives no table details.

The creator can change bot profiles, remove lobby members and issue invitations while the lobby is open. Every human explicitly readies the current lobby revision; any setup change clears readiness. A readiness change increments the visible lobby revision while carrying other ready humans forward, so polling detects it without cancelling their consent. Start requires all seats filled and humans ready, then atomically freezes controller assignments and creates the engine snapshot. Host powers do not grant another player's hand or decision. After start there is no seat transfer, replacement bot or reconnect invitation.

Disconnection leaves the seat and pending decision intact indefinitely; approximate online presence is only a UI hint. Recovery restores access to all of the principal's seats. If both session and recovery code are lost, there is no name-based or host-assisted takeover: the group starts another table. The host may cancel an unfinished table, recorded as a separate lifecycle status with no invented score or winner; cancellation never reveals hidden cards. A stale tab with a revoked session must clear its private board when its next request is rejected.

## Authorization, commands and private views

For each request: authenticate the session, find membership, load consistent game/room/preference data in one short read transaction, resolve the seat, then call `view_for(state, seat)`. Unknown games and games outside that principal's membership return the same response. Protect full pages, fragments, updates, preferences and command receipts equally. Templates receive the filtered view and public lobby/controller metadata, never a `GameRecord` or raw storage history.

Authorize a new command against **`state.pending.player`**, not `active_player`. For example, when Alice attacks Bob, Bob alone sees and answers his reaction; Alice waits even though it remains her turn. Charlie sees only Charlie's view and public events. Bot decisions receive that bot's filtered view. Waiting messages may name the decision owner but must not expose a private prompt or its options.

Each confirmed choice sends a fresh request ID plus the existing decision ID, expected game revision and ordered selections. Keep the request ID and exact payload for transport retries. Server processing is:

1. Authenticate and check membership; look up the receipt by `(game_id, principal_id, request_id)`.
2. An identical committed retry returns its accepted revision plus a newly filtered current view, even if the next decision belongs to someone else. Reusing an ID for different content is a conflict.
3. For a new request, validate lifecycle, pending owner, decision ID, revision and legal selections. Compute the transition outside the service read/write callbacks.
4. In one short transaction, recheck session validity, membership, lifecycle and expected revision; store the snapshot, bot state, attributed command/events and receipt together. A competing commit either yields the same receipt or fails without changing state.

The hosted service checks authenticated receipts before current-decision checks; the local service retains its existing decision-bound command behaviour. Retain receipts for the lifetime of the saved game. Never replay old choices against a newer decision automatically.

Multiple tabs may share a seat. The first valid choice wins; a conflicting choice gets a 409 and that viewer's current board. Preserve local selection/focus only while the decision ID still matches. Reconnect always reloads authoritative state before enabling a choice. Theme preference belongs to `(principal_id, game_id)` and has its own version; it neither advances the game nor changes another viewer's theme.

## Updates and bot progress

The hosted browser serializes authenticated fetch polling with form submissions: every two seconds while visible, every fifteen seconds while hidden, with connection-error backoff capped at thirty seconds. Refetch immediately on reconnect or becoming visible. This fits four-seat, turn-based play and the shared HTML fragment renderer without a persistent connection or extra transport dependency. Local play retains HTMX; hosted play uses a small fetch coordinator to retain exact requests across uncertain transport failures. Reconsider SSE only if measured update delay or request volume warrants it; preserve the same authorization and filtering contract.

An update request carries the last game revision, lobby/lifecycle revision and viewer-preference version. After authorization, return 204 if unchanged or a fresh filtered board. GET never advances gameplay. Serialize each tab's board requests, coalesce polls during a submission, and discard responses older than the latest applied versions; an old poll must not overwrite a successful choice. Private responses use `Cache-Control: no-store`; shared caches cannot serve one player's board to another.

Automatic bot progress belongs to the runtime scheduler, not the browser. The self-hosted adapter uses a threaded dispatcher with one outstanding job per game and periodic scans of durable pending work. The Cloudflare adapter uses Durable Object alarms and reschedules bounded work while a bot remains pending. It commits durable wakeups with the operation that makes work pending, so eviction after a successful response cannot strand a game. Revision checks remain the correctness boundary on both targets. Process at most eight bot decisions or 100 ms per job, checking elapsed time between decisions and completing any current commit. Requeue fairly if another bot decision remains. Stop at every human decision, including reactions. Keep choices and rendering outside the service read/write callbacks. Cloudflare additionally wraps each operation and its alarm update in an outer transaction to preserve durable wakeups; computation within that object-level boundary remains bounded.

Persist each successful bot decision and its new random state atomically, using an internal bot actor and decision-bound command key; recheck its controller and revision instead of requiring a human session. A bot failure records a paused reason code and exposes a retry control to members; no unbounded retry loop. Clients cannot submit choices on behalf of a bot. Self-hosted startup and periodic bounded scans queue pending bot work, excluding paused games; Cloudflare alarms scan the same pending markers. The saved pending decision is the durable work source. Recovery of wakeups is adapter-specific, and progress must not depend on a player's tab staying open.

## Storage, recovery and hosting boundary

Keep multiplayer records in the same database as their games so invitation consumption, lobby start and command authorization can be transactional. Extend the portable storage contract with principal/session/recovery records, memberships/invitations, lobby/lifecycle revisions, viewer preferences and attributed command receipts. Controllers are frozen on start; versioned application snapshots map bot states to seat indices. Engine card/effect data stays in its existing versioned JSON format.

Back up before an explicit schema migration. Existing saves retain their local meaning: one human at seat 0, with bots in subsequent seats. They must not silently become hosted tables or become visible to the first remote visitor. Self-hosted multiplayer uses a separate configured data directory; Cloudflare multiplayer uses its own installation object. Unsupported formats preserve original saves and produce a recoverable error.

Self-hosted multiplayer uses one application process on a laptop or VM with SQLite on local disk. Cloudflare multiplayer uses one SQLite-backed Durable Object for the entire installation, preserving atomic identity/game operations. Sessions, invitations, memberships, receipts and pending decisions survive restart on either target. In-memory locks, presence and queue contents are not the source of truth.

Both adapters share the engine, identity policy, multiplayer service, filtered web routes and browser. The self-hosted adapter supplies local transaction execution, process coordination and the dispatcher; the Cloudflare adapter supplies object transactions, platform execution and durable alarms. A single installation object has finite storage and throughput, and bot batches share its execution capacity with requests. Sharding or adding self-hosted workers requires additional design and crash-recovery tests; the current adapter boundary is not a claim of unlimited scaling. [PostgreSQL](../ARCHITECTURE.md#postgresql-transition) remains an optional future self-hosted adapter.

Selecting another runtime does not transfer stored players or games. No export/import between self-hosted SQLite and a Durable Object is provided, and local saves never become hosted tables automatically.

Local mode stays loopback-bound and retains its current no-account workflow. Hosted mode must be explicit and fail closed unless a canonical HTTPS origin, allowed hosts, session storage and the selected runtime's transport boundary are configured. Enforce session-bound CSRF tokens and exact-origin checks on all mutations, including join/recovery; never accept forwarded origin headers from arbitrary clients. Apply bounded request sizes and rate limits to join, recovery and commands. Do not log bearer credentials, private choices or snapshots, and keep secrets out of query strings and redirects. Deployment backup/restore, access control and abuse controls require their own hosting review; this design does not authorize public exposure.

## Acceptance scenarios

- Separate browser identities can join two-, three- and four-seat human/bot tables; unfilled or unready lobbies cannot start. Concurrent invite claims, revocation and expiry cannot assign the same seat twice.
- Guessing a game ID or posting another seat/name cannot read its pages, updates, receipts or history, or make decisions. The host has no private-view privilege. Cross-origin/CSRF failures leave all records unchanged.
- A human attacks another human while a third viewer polls: only the target receives reaction options; a bot attack also pauses for the correct human. Assert absence of hidden data in HTML and update responses, not merely hidden elements.
- Two tabs submit different choices at one revision: exactly one commits. Identical retries after a lost response return success without another transition; conflicting payloads under one request ID fail. A delayed poll cannot restore an old board.
- Recovery keeps seat ownership while rotating credentials; revoked sessions lose access. Restart during a reaction preserves its owner/options, and restart between a bot commit and enqueue produces the same eventual state and bot randomness as uninterrupted play.
- Concurrent bot wakeups, a failed bot and a server restart cannot double-advance or spin indefinitely. A request waiting on another game's bot must still make progress.
- Viewer theme changes preserve that viewer's pending local choice and do not alter anyone else's theme or game revision. Hosted forms/responses expose no gameplay seed. Local saves remain private to local mode.
- Run the shared behavioural contracts against each supported adapter, including forced rollback, stale revisions, receipt retries and recovery. Exercise separate connections/processes for self-hosted SQLite and actual object transactions, alarms and restart behaviour for Cloudflare. Prove identity/game recovery together using the selected platform's procedure. A future adapter must pass the same contracts before deployment.

The backend service tests cover separate identities, concurrent invitation claims, guest-join rollback, readiness and start races, human-targeted reactions, command retry and revision races, credential revocation during computation, independent preferences and deterministic bot restart. HTTP tests cover filtered access, CSRF, origin and transport limits; real HTTPS browser tests exercise signup, invitations, private decisions, serialized polling and transport recovery. Deployment-specific TLS/proxy and recovery drills remain mandatory before a real endpoint opens. Verified accounts, transferable seats, spectators and timed play remain separate product decisions.
