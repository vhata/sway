# Development decisions

These choices record the defaults selected under the user's authorization to continue independently. They are reviewable design decisions, not a claim that every capability is part of the released game. Detailed contracts belong in the linked documents and implementation tests.

## 2026-09-23

| Decision | Reason and tradeoff |
| --- | --- |
| Original-name hints use the server startup flag `SWAY_DEV_TERMINOLOGY=1`, disabled by default. | One setting covers pages and HTMX fragments consistently. Restarting the server is required to change it; no game or browser preference is stored. |
| Show original names as secondary text beneath themed names. | Works on touchscreens and with keyboard navigation without depending on hover. The normal card, artwork and themed name remain primary. Reuse the catalogue's existing stable-ID mapping. |
| Preserve setup entries after validation errors and bring each new decision into view. | Browser playtesting reproduced lost setup work and mobile turns stranded below the next decision. Theme changes during the same decision retain selection and scroll position. |
| Give cards original, distinct SVG illustrations and clearer type, cost and value hierarchy. | Addresses the repeated-glyph problem while retaining both themes and the existing asset pipeline. Mechanical values come from existing definitions; action descriptions remain authored prose rather than a second implementation of the rules. |
| Include a read-only card catalogue in developer mode. | All 33 cards can be compared in either theme using their real game components. Opening it separately from an active table preserves unfinished selections; it neither opens nor changes game storage. |
| Prepare multiple-human-seat orchestration before remote routes. | Seat ownership, reaction timing and bot-state assignment can be tested independently of authentication and networking. Local browser behavior must remain explicit and safe while the remote interface is developed. |
| Preserve existing local saves when changing the application snapshot shape. | Seat metadata needs an explicit representation. A lossless conversion of supported local snapshots protects saved games; it does not require legacy aliases for renamed themes. |

## Multiplayer implementation defaults

The [multiplayer contract](MULTIPLAYER.md) owns the detailed identity, invitation, authorization, retry, update and recovery rules. The implemented defaults are:

- Invite-only tables with two to four human/bot seats, guest credentials and a separate recovery code; no identity-provider dependency.
- Fixed controller assignments after play begins; disconnected human decisions wait for that player. Losing both session access and recovery credentials requires starting another table.
- A private, server-generated gameplay seed and per-viewer theme preference.
- Authenticated polling initially, with bounded server-owned bot work that can resume after a restart.
- Self-hosted SQLite for one application process on a laptop or VM, or SQLite storage in a Cloudflare Durable Object. The [PostgreSQL transition](../ARCHITECTURE.md#postgresql-transition) remains a separate option for a future self-hosted scaling requirement.

The recovery policy and frozen seats deliberately limit takeover and substitution features. Verified accounts, replacement players, spectators and timed turns can be designed separately. Public deployment remains a separate operational task.

## Hosted implementation

- Keep local and hosted applications separate, including storage and route registration. Both hosted runtimes require a canonical HTTPS origin; the self-hosted adapter additionally requires a private directory and exclusive process lock.
- Use guest recovery credentials rather than adding an identity-provider dependency. Invitation links carry secrets only in fragments; a GET never claims a seat.
- In self-hosted mode, keep SQLite for one application process with short authorization/write transactions, durable command receipts and two bounded bot workers with one outstanding job per table.
- Use a small fetch coordinator for hosted updates so polling cannot overlap a confirmed submission. A lost decision response retains the exact request for an explicit retry; reconnect reloads authoritative state before re-enabling choices.
- In self-hosted mode, keep forwarded-header trust disabled. The loopback backend checks the configured public Host and Origin; the TLS proxy must preserve them. In-process rate limits share the proxy's network identity and supplement edge limits.
- Backups include credential hashes and private game data. Self-hosted recovery verifies full-database copies and restores only to a fresh private directory; Cloudflare recovery uses its platform-specific procedure. Rollback can revive old credentials on either target and requires a deployment recovery procedure.

## 2026-09-25: two hosted runtimes

- Keep laptop/VM self-hosting as a supported target alongside Cloudflare Python Workers. Share the engine, identity policy, multiplayer operations, filtered routes and browser rather than maintaining separate products.
- Introduce synchronous `StateStore.read`/`write` callbacks with typed SQL sessions. This preserves whole-operation transactions in both standard SQLite and Durable Object storage without emulating a native Python connection in Workers. Bot and engine computation stays outside those service callbacks, followed by authorization/revision rechecks. Cloudflare wraps the complete runtime operation and its alarm update in an outer transaction so durable pending work and wakeups commit together.
- Use one SQLite-backed Durable Object per installation, containing identities and every table. This preserves atomic recovery, invitations, memberships and game commits. It deliberately accepts one object's throughput/storage limits; per-game sharding would need a different cross-object authorization design.
- Select background execution through the runtime adapter: the existing self-hosted dispatcher or durable object alarms. Both operate on persisted pending work and bounded bot decisions without requiring an open browser.
- Keep Python 3.12 and its locked environment for ordinary development/self-hosting. Cloudflare has its own pinned toolchain and lockfiles for the Python version selected by its compatibility date; do not copy that runtime requirement into the local release.
- Keep runtime selection separate from migration. No automatic data transfer, export/import or merging of installations is included; existing local saves stay local. Deployment and recovery drills remain explicit work, and preparing the adapters does not authorize publication.
