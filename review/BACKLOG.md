# Review backlog

Only work promoted from whole-codebase reviews belongs here. Entries are ready for separate work and grouped by priority, without TODO workflow stages. Follow [review guidance](../docs/CODE_REVIEW_GUIDE.md) and [claim/resolution rules](../docs/TODO_GUIDE.md).

## P0 Critical

## P1 High

- [ENGINE] `base-rules-review-corrections` — **Correct public information and reject unusable saves.** Engine review found one private-information leak, one missing public zone and malformed continuations that fail after loading.
  - Source: review/2026-09-22-0934-full.md, 2026-09-22
  - Findings: `harbinger-hidden-topdeck-event`, `library-public-set-aside`, `snapshot-continuation-and-id-validation`
  - Starting point: Assigned within the currently authorized implementation to engine PR #2 and browser PR #6; verify original failures in the subsequent incremental review.

## P2 Normal

- [TOOLING] `enforce-engine-branch-coverage` — **Enforce the branch threshold separately.** Combined coverage can pass while branches fall below the accepted 90% minimum.
  - Source: review/2026-09-22-0934-full.md, 2026-09-22
  - Findings: `separate-engine-branch-coverage-gate`

## P3 Low

## Unprioritized
