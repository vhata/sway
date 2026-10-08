# Review index

Historical codebase reviews are immutable snapshots; the latest review is the current finding inventory. Implementation PRs supply evidence and later incremental reviews verify closure. See [CODE_REVIEW_GUIDE.md](../docs/CODE_REVIEW_GUIDE.md).

| Review (UTC, newest first) | Type | Reviewed commit | Open findings |
| --- | --- | --- | --- |
| [2026-10-08 07:23](2026-10-08-0723-full.md) | Full | `5a321ca` | 25 |
| [2026-09-22 09:45](2026-09-22-0945-incremental.md) | Incremental | `00ede93` | 0 |
| [2026-09-22 09:34](2026-09-22-0934-full.md) | Full | `55c3052` | 4 |

[BACKLOG.md](BACKLOG.md) holds promoted review work. Historical open counts describe each reviewed commit; the newest snapshot owns the current inventory.

## Review baseline

The [2026-10-08 full review](2026-10-08-0723-full.md) reviewed `5a321ca`, which is reachable from `main`. Start incremental reviews and ancestry-based review-drift measurements from that commit. The 2026-09-22 snapshots record commits `55c3052` and `00ede93`, which are not ancestors of `main` and whose trees differ from the landed revisions. They remain historical evidence only. The 2026-10-08 review rechecked their four findings on `main` and confirmed all four fixed. See the [2026-10-07 workflow audit](../docs/WORKFLOW_AUDIT.md) for how the gap arose.

## Pending reconciliation

None recorded.
