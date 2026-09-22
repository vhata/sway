# TODO and review-backlog workflow

Read when capturing, selecting, claiming, moving or resolving deferred work. These rules cover [TODO.md](../TODO.md) and [review/BACKLOG.md](../review/BACKLOG.md).

## Scope and queue boundaries

Keep work required for the requested outcome, correctness and verification in scope. Record separately shippable ideas and continue the original task. An entry does not authorize unrelated implementation. Follow existing user authorization before adding approval steps.

Ordinary discoveries belong in TODO, even when they are bugs. Whole-codebase review findings promoted for separate work belong in the review backlog. Never silently switch queues when a requested queue has no suitable available item. Raw review findings are evidence unless explicitly assigned or necessary for the correctness of current scoped work.

Search existing slugs first; update instead of duplicating. Priorities are **P0 Critical** (active security, data loss or release blocker), **P1 High**, **P2 Normal**, **P3 Low**, and **Unprioritized**. Use Unprioritized unless the user assigned priority or the issue objectively qualifies as P0. Report a newly discovered unrelated P0 promptly and get direction before expanding scope.

TODO entries have stages: **Needs triage** (outcome/dependencies unclear), **Needs proof of concept** (a focused experiment is needed), and **Ready for separate work** (understood enough to implement). Review backlog entries are already ready and use priority sections without stages.

## Entry format

```md
- [PLATFORM] `immutable-kebab-case-slug` — **Short outcome.** One-sentence rationale.
  - Starting point: Optional useful place to begin.
  - Source: task, branch, issue, PR or review filename, YYYY-MM-DD
  - Related: `optional-related-slug`
```

Each entry has exactly one area: `[UI]`, `[GAMEPLAY]`, `[AUDIO]`, `[BACKEND]`, `[PLATFORM]`, `[TOOLING]` or `[DOCS]`. Slugs are unique and never change when an item moves. `Source` is required. Review backlog entries also require `Findings: <raw-finding-slugs>`; each finding maps to at most one backlog entry.

## Claiming

1. Follow the user's selection; otherwise prefer the highest-priority suitable unclaimed ready entry in the selected queue. Do not start triage/prototype work merely because no implementation item is ready.
2. Search open PRs, branch names and active worktrees for the exact slug/title. For review batches also check every raw finding and any mapped backlog slug. A matching worktree is a provisional claim.
3. Assign a dedicated worktree and branch containing the exact slug. Recheck concurrent claims. The coordinator can resolve overlapping assignments already authorized within the active task; otherwise clarify before duplication.
4. After the first meaningful commit, open a draft PR. Keep the source item while work is underway. If draft creation fails, report that the claim is not globally visible and preserve the entry. Close abandoned draft PRs.

Every tracked-work PR begins with `## Why`, explaining the need, impact and resulting capability without requiring readers to open the queue. Use these exact markers after that section:

```text
Claims TODO: <slug>
Claims review backlog: <slug>
Claims review finding: <finding-slug>
```

Use only markers relevant to the selected queue. A review batch claims its backlog slug plus each finding actually in scope. Explicitly assigned raw-finding work without a backlog entry uses only the finding marker and explains the exception.

## Resolution

Before marking ready, verify the complete source entry. Full resolution removes the entry and changes the corresponding marker to `Resolves TODO: <slug>` or `Resolves review backlog: <slug>`. Completed review findings use `Resolves review finding: <slug>` and include the validation instructions in [CODE_REVIEW_GUIDE.md](CODE_REVIEW_GUIDE.md).

Partial resolution removes the original entry and creates a new assessed remainder with a new slug and `Remaining from: <original-slug>`. For review work it lists only open findings. Use:

```text
Partially resolves TODO: <original-slug>
Remaining TODO: <new-slug>
Partially resolves review backlog: <original-slug>
Remaining review backlog: <new-slug>
```

Use only the applicable pair. Do not mark remaining findings resolved. Preserve raw finding slugs. Explain rejected/obsolete items in the removing PR; repair `Related` references in both queues whenever removing an entry.

A batch is a scheduling unit, not permission to mix unrelated fixes. Claim its slug before taking a coherent subset, then create one remainder. For parallel subsets, first land a queue-only split: keep the original slug on one entry and use new slugs with `Split from: <original-slug>` for the others. Splitting is not resolution.

Merging a fix supplies closure evidence. The next incremental review owns verified finding closure; implementation PRs never rewrite historical review snapshots.
