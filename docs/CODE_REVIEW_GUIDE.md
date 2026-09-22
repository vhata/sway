# Code review

PR review checks a change; whole-codebase review checks accumulated interactions and maintains historical findings. Use independent sub-agent review for implementation PRs. Confirm any reported claim against the actual source and tests before treating it as evidence.

## Scope and artifacts

Read relevant architecture/specification sections, the diff and necessary surrounding code. Focus on correctness, private information, serializable effects, deterministic replay, duplicate commands, recovery and accessible decision workflows. Report actionable findings with a failure scenario, location, severity and evidence. Do not invent findings to fill a review.

[review/README.md](../review/README.md) indexes reviews newest first with type, reviewed commit and open count. [review/BACKLOG.md](../review/BACKLOG.md) is the mutable promoted-work queue. Snapshots use `review/YYYY-MM-DD-HHMM-full.md` or `-incremental.md` in UTC. Once merged they are immutable except for factual corrections. Fix PRs do not edit them to claim closure.

Every review snapshot contains:

1. Header table: review type, reviewed code commit, previous review/commit or None, and baseline commands/results.
2. Summary and checked invariants.
3. Findings by kind, with current locations.
4. A backlog-slug to finding-slugs mapping table and explicit inventory-only decisions.
5. Suggested work order and verification limitations.

## Findings

```md
- `immutable-finding-slug` — **One-sentence title.** Bug · Open · Verified.
  - Where: `path:line` (`symbol`) at the reviewed commit.
  - Severity: P1 High.
  - Failure, reproduction evidence and suggested correction in one to four sentences.
  - Review backlog: `mapped-backlog-slug`
```

Kinds: `Bug`, `Design`, `Duplication`, `Performance`, `Test`, `Style`, `Tooling`, `Docs`. Verification is `Verified` when executed/reproduced, `Read` when based on inspection. One finding represents one independently fixable/verifiable problem; a recurring identical smell may list several locations.

Statuses: `Open`; `Moved` (still open at a new location); `Fixed` (commit/PR, current location and confirmation); `Accepted` (reason for leaving it); `Invalid` (evidence the finding was wrong); `Superseded` (replacement slug). All non-open statuses require evidence. `Moved` counts as unresolved.

Closed entries retain reference, current location and verification, for example:

```md
- `finding-slug` — Fixed in #12 (abc1234). `path:line` (`symbol`): new behaviour. Original reproduction rerun; no longer fails.
```

A PR link alone is insufficient. Use `git show <reviewed-commit>:<path>` to inspect historical locations.

## Full and incremental reviews

Record the reviewed commit first. Run `scripts/check.sh` and `scripts/e2e.sh`; record exact results and environmental gaps. A full review reads all maintained source, tests and relevant configuration, delegating independent areas when useful. Reproduce serious failures where practical.

Incremental review starts from the newest snapshot's reviewed commit:

1. Recheck every standing finding and scan merged PRs for `Resolves review finding: <slug>`. Reproduce previously Verified failures before closing them.
2. Inspect the full delta against inherited invariants, re-read heavily changed files and check cross-module boundaries.
3. Run cheap whole-project checks for stale terminology, dead code/configuration, inconsistent interfaces, weak assertions and changed dependencies. Use actual evidence rather than arbitrary file-size thresholds.
4. Carry immutable slugs forward. Open/Moved findings retain full entries; closed findings retain commit, location and confirmation.
5. Triage every Open/Moved finding at review close, write the new snapshot and update the index.

A full review resets the baseline after major structural change, widespread deltas or repeated incremental reviews revealing substantial whole-program drift. Review depth follows risk; a routine PR does not create a new permanent ledger snapshot unless a codebase review was requested.

## Review-close triage and work

For every unresolved finding, deliberately map to existing backlog work, promote a coherent separate-work entry, or retain as unmapped inventory. Promote verified/user-visible bugs, changes that unblock other work and coherent batches worth their own branch. Avoid duplicate queue entries. Small factual documentation fixes can be separate commits on the review branch with explicit evidence.

Follow [TODO_GUIDE.md](TODO_GUIDE.md) for priorities, ownership, batch splits and exact claim/resolution markers. Select explicitly assigned raw findings first; otherwise select the review backlog by priority. Inventory alone is not an implementation queue.

Every PR resolving a finding starts with `## Why` and includes a human-runnable validation scenario: setup, actions, old failure and expected corrected result. For non-product findings use a concrete command/inspection and define success. Automated checks support that scenario; “tests pass” alone is not enough.

The next incremental review independently confirms fixes, records current locations, reruns original Verified reproductions, and records closure. If confirmation fails, keep the finding open and restore/update its backlog mapping. Preserve history throughout.
