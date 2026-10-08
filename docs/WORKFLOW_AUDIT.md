# Workflow audit — 2026-10-07

Sway has substantial product validation and compatible queue/review conventions, but availability, review baselines and workflow enforcement need attention. This is a workflow audit of main `f93f650007f2cda27488b7fa78a2477a58407971`, not a full codebase review or production acceptance.

The audit used the installed repo-workflow skill, its setup/queue/quality/review references, repository instructions and two independent read-only agents: `audit_queues` and `audit_gates`. Historical comparison notes guided what to recheck; all findings below were checked against current files or live GitHub records.

## Policy, enforcement, records and limits

| Area | Written policy | Actual enforcement | Current records and limits |
| --- | --- | --- | --- |
| Ownership and scope | [Contract](../AGENTS.md) requires focused branches/worktrees, claim checks, draft PRs and independent review. | Manual branch/worktree/PR inspection; no installed claim tools. | No open PRs at inspection. Two local hosted follow-up branches and one extra worktree remain; neither claims a current queue slug. Ownership/abandonment is unknown; preserve them. |
| Queues | [Guide](TODO_GUIDE.md) separates ordinary discoveries and promoted review findings; exact slugs, claims, remainders and split-before-parallel-work are documented. | No queue or PR-marker validation in CI/hooks. Bundled strict queue check passes. | Three original entries; review backlog empty. PostgreSQL is Ready despite being behind transfer and conditional on deployment need. Format validity does not establish availability. |
| Ready policy | Guide says understood enough to implement. | No dependency/readiness enforcement. | Skill requires unblocked too. Merged [PR #23](https://github.com/vhata/sway/pull/23) records the PostgreSQL conditions. Definition change awaits the user's choice. |
| Hooks and suites | [Quality](QUALITY.md) specifies staged format/lint, pre-push types/tests, coverage, package and browser checks. | `.githooks` is installed through `core.hooksPath`; wrappers are executable. Scripts preserve empty-suite failure once application/tests exist. Coverage requires both combined and separate engine-branch thresholds. | Hook code/config inspected; no scratch commit or local product suite run during this audit. |
| PR/main CI | Required quality check against current base. | [Quality workflow](../.github/workflows/ci.yml) runs full checks, Chromium and actual local Workers checks on PRs/main. `cancel-in-progress: true` also cancels main runs. | [Main push run](https://github.com/vhata/sway/actions/runs/37165425322) passed at audited SHA. Concurrent main pushes could lose intermediate validation evidence. |
| Scheduled checks | Daily synthetic recovery, browser, extended properties and 1,800 simulations; evidence retained. | [Daily workflow](../.github/workflows/daily.yml) has independent lanes, separate non-cancelling concurrency, timeouts and 14-day artifacts. | [October 7 run](https://github.com/vhata/sway/actions/runs/37662310053) passed all seven jobs at audited SHA. October 6 failed two simulation lanes; October 5 has a cancelled quality lane and overall failure, with no failed-step log returned. |
| Hosting protection | PR, required quality, current-base checks, linear history, resolved conversations; documented admin exceptions. | Live protection matches: strict quality check, linear history, conversation resolution; zero required approvals, admin enforcement off, main force-push/deletion disabled. No rulesets. | Squash only, title/body from PR, auto-delete merged head branch. Zero forge approvals cannot prove agent review absent; review remains procedural. No hosting changes needed to align existing policy. |
| Review evidence | Independent review required. | Forge does not enforce agent identity/reviewed revision; PR body evidence is manual. | Recent PRs assert independent review, but often omit reviewer identity or exact reviewed revision. This audit adds explicit requirements and a template section; historical reviews were not independently reconstructed. |
| Review baseline | Immutable snapshots; incremental reviews start at newest reviewed revision. | No scheduled drift check. | Both recorded hashes exist but are outside main ancestry. Latest tree differs from landed quality revision in 21 files; substitution would be inaccurate. Exact latest-review-to-main delta: 174 files, +13,772/-523 lines. |
| Failure response | No explicit red-main response policy. | Failing daily simulations propagate failure; later successes cannot swallow it. | No existing TODO captured October 6 failures. Today's green rotating corpus is different. Audit files a reproducible triage entry. Same-day response policy requires an explicit decision. |

## Findings and dispositions

1. **Workflow availability is misleading.** `postgresql-shared-game-storage` is not presently available under the skill's Ready definition. Proposed repair: Ready means understood and unblocked; move PostgreSQL to Needs triage with `Depends on: portable-hosted-data-transfer` plus the deployment condition. The existing definition is preserved pending choice; no product scope is expanded.
2. **Review baselines cannot support ancestry-based coverage.** Both `00ede93` and `55c3052` are off main. Bundled `review-due.sh` reports **BASELINE LOST**; its 25-commit/+21,965-line/full-due figures are merge-base approximations, not exact reviewed coverage. A fresh full review is queued. The index now explains the limitation; snapshots remain unchanged. New guidance requires main-reachable baselines or preserved branch trees with verified landed correspondence.
3. **Workflow enforcement is absent and main cancellation is unsafe.** Install adapted queue/link/marker validators, scheduled drift reporting and PR-only Quality cancellation in a separately authorized CI change. These are grouped under `workflow-gate-automation`. Do not transplant validators blindly: the existing guide's accepted Ready/dependency policy must first be reconciled.
4. **Independent review evidence is incomplete.** A new PR-template Review section and guide text require reviewer identity, exact reviewed commit and verified dispositions, including later changes. A Pending reconciliation list is added to the index for landed finding fixes awaiting the next review. No old review is fabricated or declared invalid solely from missing metadata.
5. **Daily failures need durable follow-up.** Downloaded October 6 artifacts each show 24/25 completed games in rotating random attack batches. The three-player seed `37502405135` reaches 4,000 decisions/1,726 turns; four-player seed `37502405136` reaches 4,000 decisions/696 turns. Both have `finished: false`. Queue entry `daily-attack-simulation-noncompletion` records commands and evidence. The cause remains uninvestigated product work; this audit does not change bots, rules, acceptance or budgets.
6. **External instructions contain a Python conflict.** Session instructions require the shared Python 3.12 virtualenv, while tracked AGENTS requires per-worktree uv environments. Audit helper scripts used the explicitly requested shared interpreter; no application validation was run with it. Normal repo workers should follow tracked per-worktree tooling; do not silently rewrite either policy from this audit.

Two smaller alignment opportunities remain: no `CLAUDE.md` import exists, and daily determinism checks do not include a dedicated repeated-seed comparison lane. Neither invalidates current Codex operation or existing ordinary determinism tests. Establish a concrete need before adding harness files or another expensive lane.

## Repairs and proposals

This branch contains the audit, explicit PR-review evidence requirements, review-baseline guidance/limitations, pending-reconciliation scaffolding and three sourced queue entries. It does not modify CI, hooks policy, GitHub settings, historical snapshots, existing hosted branches/worktrees or product code.

Proposed CI diff: replace Quality `cancel-in-progress: true` with `${{ github.event_name == 'pull_request' }}`. Add compatible workflow validators to existing script entrypoints/CI and scheduled review-drift reporting after deciding Ready semantics and review cadence. Proposed red-main policy: investigate the same day, revert or file a sourced priority entry, and verify recovery on main with the original failed corpus where applicable. These are proposals requiring authorization under the skill, not implemented controls.

GitHub settings already match Sway's documented policy. Keep strict quality, linear history, conversation resolution and squash title/body conventions. The owner may choose approving-review/admin requirements; agent review is presently evidenced in PR bodies rather than forge approvals. No hosting setting was applied.

## Checks and evidence limits

At audited main:

- Bundled `check-queues.sh --strict`: passed, three entries.
- Bundled `check-links.sh`: passed, all tracked relative Markdown targets resolve.
- Bundled `claim-check.sh` for all three original slugs and this audit slug: no existing claims found.
- Bundled `review-due.sh --paths 'src tests'`: exit 0, **BASELINE LOST**, approximate full-review-due verdict. Exit 0 is tool completion, not a healthy baseline.
- `bash -n scripts/*.sh .githooks/pre-commit .githooks/pre-push`: passed.
- Read-only GitHub API: live main SHA matches local SHA; protection, rulesets, merge settings, open/recent merged PRs and latest twelve Actions runs inspected. October 6 failed artifacts downloaded and parsed; original failed games not rerun.

On the audit branch, strict queue validation passed with six entries, relative links passed, all three Files TODO markers validated against main, and whitespace/shell syntax checks passed. Independent reviewer `review_audit` inspected commit `8fbb785`, verified the artifacts and key live/source claims, and reported no actionable findings. Product suites are unnecessary for these documentation/template-only changes; live passing runs are forge evidence, not fresh local execution. CI is a safety net, not proof of ownership, independent review, current codebase-review coverage or production capacity/recovery.

The user retains final review and landing. This audit does not authorize a merge, release, deployment, protection edit or destructive cleanup.
