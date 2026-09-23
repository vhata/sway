# Development decisions

These choices record the defaults selected under the user's authorization to continue independently. They are reviewable design decisions, not a claim that every capability is part of the released game. Detailed contracts belong in the linked documents and implementation tests.

## 2026-09-23

| Decision | Reason and tradeoff |
| --- | --- |
| Original-name hints use the server startup flag `SWAY_DEV_TERMINOLOGY=1`, disabled by default. | One setting covers pages and HTMX fragments consistently. Restarting the server is required to change it; no game or browser preference is stored. |
| Show original names as secondary text beneath themed names. | Works on touchscreens and with keyboard navigation without depending on hover. The normal card, artwork and themed name remain primary. Reuse the catalogue's existing stable-ID mapping. |
| Preserve setup entries after validation errors and bring each new decision into view. | Browser playtesting reproduced lost setup work and mobile turns stranded below the next decision. Theme changes during the same decision retain selection and scroll position. |
| Give cards original, distinct SVG illustrations and clearer type, cost and value hierarchy. | Addresses the repeated-glyph problem while retaining both themes and the existing asset pipeline. Mechanical values come from existing definitions; action descriptions remain authored prose rather than a second implementation of the rules. |
| Prepare multiple-human-seat orchestration before remote routes. | Seat ownership, reaction timing and bot-state assignment can be tested independently of authentication and networking. Local browser behavior must remain explicit and safe while the remote interface is developed. |
| Preserve existing local saves when changing the application snapshot shape. | Seat metadata needs an explicit representation. A lossless conversion of supported local snapshots protects saved games; it does not require legacy aliases for renamed themes. |

## Multiplayer defaults to review

The [multiplayer proposal](MULTIPLAYER.md) owns the detailed identity, invitation, authorization, retry, update and recovery contracts. Its proposed defaults are:

- Invite-only tables with two to four human/bot seats, guest credentials and a separate recovery code; no identity-provider dependency.
- Fixed controller assignments after play begins; disconnected human decisions wait for that player. Losing both session access and recovery credentials requires starting another table.
- A private, server-generated gameplay seed and per-viewer theme preference.
- Authenticated polling initially, with bounded server-owned bot work that can resume after a restart.
- SQLite for one application process on one server. The [PostgreSQL transition](../ARCHITECTURE.md#postgresql-transition) applies before multiple application servers share games, or earlier when operational requirements justify it.

The recovery policy and frozen seats deliberately limit takeover and substitution features. Verified accounts, replacement players, spectators and timed turns can be designed separately. Public deployment remains a separate operational task.
