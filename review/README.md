# Review index

Historical codebase reviews are immutable snapshots; the latest review is the current finding inventory. Implementation PRs supply evidence and later incremental reviews verify closure. See [CODE_REVIEW_GUIDE.md](../docs/CODE_REVIEW_GUIDE.md).

| Review (UTC, newest first) | Type | Reviewed commit | Open findings |
| --- | --- | --- | --- |
| [2026-09-22 09:45](2026-09-22-0945-incremental.md) | Incremental | `00ede93` | 0 |
| [2026-09-22 09:34](2026-09-22-0934-full.md) | Full | `55c3052` | 4 |

[BACKLOG.md](BACKLOG.md) holds promoted review work. Historical open counts describe each reviewed commit; the newest snapshot owns the current inventory.

## Baseline limitation

The recorded commits exist locally but are not ancestors of current `main`. Their trees differ from the landed revisions; the latest snapshot remains historical evidence, not coverage of subsequent hosting and recovery work. A new full review should establish a baseline on main before relying on ancestry-based review-drift measurements. See the [2026-10-07 workflow audit](../docs/WORKFLOW_AUDIT.md).

## Pending reconciliation

None recorded.
