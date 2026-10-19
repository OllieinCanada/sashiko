# Upstream PR preparation — adaptive publication cooldown

Status: draft materials only; not ready for submission.
This document lives on the fork validation branch and is not part of the
proposed upstream source patch.

## Proposed title

mail: add opt-in per-author publication cooldowns

## Proposed description

Mailing lists with sustained submissions currently have only a fixed publication
embargo. Add an explicitly enabled per-list policy that counts each complete
canonical revision once within the configured author/list window. Compute an
incremental publication delay after the configured burst, cap that increment,
and retain the longer existing embargo. Review computation remains available
under the existing rules; deployed list configuration is unchanged.

Persist admission, canonical message ownership, policy snapshots and early-release
markers in the project database. Decide atomically before a new enrolled revision
can become Pending. Restarts and duplicate ingestion retain the original decision.
Incomplete revisions and covers add no events. Ambiguous or changed identity
quarantines the revision and prevents review/publication claims and public result
access. Multi-list and non-NNTP ingestion follows the existing shared legacy policy.

Keep the obsolete-held-review supersession correction as a separate prerequisite
commit so reviewers can evaluate that reliability change independently.

## Verified checkpoint

- Source checkpoint: 3b82f0ae897d1b90ba81f173aaef6198c71128dc.
- GitHub Actions run: https://github.com/OllieinCanada/sashiko/actions/runs/39287394836
- Formatting and all three Clippy feature profiles: PASS.
- Full native suite: 1,089 passed, zero failed, two ignored.
- The owner-lookup behavior and point-query-plan regression passed.
- A hosted paired performance/gap-validation workflow is being introduced.
  Its presence is not a passing result.

## Identity and contribution hygiene

The source prototype was saved locally as signed-off commit
710ce6cc7f6754e2fac9e654725158263a73dd09, with prerequisite
33c09a77fe475d5ef07d73a42becd85785d0dc62.
The fork-only GitHub API checkpoints have different commit metadata and contain
task workflows. They must not be submitted upstream as the contribution series.
Reconstruct proper source-only commits using the configured Git identity, preserve
the configured Signed-off-by trailer, and run make check-pr for the final range.

## Submission blockers

1. Performance: the prior matched upstream/disabled/enabled workload exceeded its
   frozen overhead budget. The new indexed lookup passed native correctness and
   query-plan tests, but its whole-workload effect is not yet measured. The new
   harness isolates that query change; it does not replace the original matched
   upstream comparison or instrument writer hold/wait time.
2. Required local Sashiko agent review: NOT RUN. No authenticated provider is
   currently available through the accessible runtime/tools. Keep the previously
   authorized conservative limits: USD 5 total, 20 minutes total, at most an initial
   review and one follow-up. Confirm enforceable spend limits before invocation.
3. Acceptance evidence: the master requests 64 scenarios. The original local matrix
   predates implementation and is stale. Do not infer 64 PASS results from the full
   suite total. Reconcile every original row with named tests, source identities and
   actual artifacts when the attached master and local evidence are accessible.
4. Remaining gaps include contended slow-collaborator writer measurements, forced
   busy/read-only/I/O faults, combined two-worker claim/lease/retry behavior,
   rollback/pruning rehearsal, full crosspost matrix and read-only shadow replay.
   A new hosted check may close only the exact gap it actually exercises.
5. Canonical multiowner quarantine remains an indivisible, potentially unbounded
   ownership group. Chunking updates could permit publication between chunks.
   No general bounded-writer guarantee is made. Reconcile the master's allowed
   ownership-group exception with explicit measured evidence and design wording;
   do not silently introduce a broader ownership redesign.
6. Recheck upstream main and PR #685 before rebasing. Both the candidate and that
   still-open PR have used migration number 014; renumber if the other lands first.
7. Local filesystem is full; execution fails before the cleanup command starts.
   The elevated cleanup attempt was cancelled and no deletion is confirmed.
   Preserve source, Git history, SDK and evidence. A fresh workspace alongside
   the old one is an acceptable recovery route.

## Rollout and risk statement for the eventual PR

Existing work is not retroactively enrolled. Disabling enrollment preserves stored
decisions and unresolved guards. Permanent compact intent/message/release state
means total database storage is not globally bounded. Raw From identities are
unauthenticated and cannot provide abuse prevention. SMTP acceptance followed by
a crash can still lead to retry; the feature does not promise exactly-once delivery.

Maintainers must approve deployment policy and values. Before a binary/schema
rollback, stop ingestion, resolve or cancel waiting/held work, inspect all outboxes,
and preserve schema/tombstones in backups.

## Upstream submission gate

Do not open the upstream PR until the source-only contribution range, required
checks, Sashiko agent review and honest acceptance matrix are ready. This draft
does not authorize merge, production configuration or rollout.

## Additional measured evidence and active correction

The process-exit/reopen fixture now passes after the fixture closes its read
cursor before writes through the separate connection. The assertions check the
immediate release result and no re-hold after duplicate ingestion. The 1,024-part
series and missing-history-table read fault also pass on checkpoint
583e8d39abb48e501fea1586906cee6d39adeb88:
https://github.com/OllieinCanada/sashiko/actions/runs/39290530692

The first matched-upstream trace completed on checkpoint
4965f93f6f77b9e66c7a09babbd1b9cb071f4f46:
https://github.com/OllieinCanada/sashiko/actions/runs/39290655537

For 1,000 series / 3,750 parts, with three repetitions, the fresh-database medians
were 7.590 seconds upstream, 8.717 disabled and 9.928 enabled. With 10,000 synthetic
archived owners they were 7.437, 11.859 and 13.019 seconds. The fresh case passed
the frozen 20%/50% screening budgets, but retained disabled overhead failed at
59.46%. The observed legacy patchset and patch-state digests matched across all
disabled runs. These debug, serial measurements are not production latency claims.

The active correction adds a partial date/id index for Reviewed patchsets with
a non-NULL hold. The production supersession query explicitly uses that index.
Migration 14 now provides the prerequisite index, and adaptive state moves to
migration 15. Interim prototype version-14 databases retain their state and acquire
the index through the version-15 upgrade. A production-query-plan regression and
an interim-upgrade persistence regression were added. This correction must pass
fresh full checks and both hosted performance workflows before being called
validated. The source-only preparation job includes the index in the prerequisite
commit so applying either commit leaves a consistent migration sequence.

The model-review authentication question remains pending. No model invocation or
model spend has occurred. The old local 64-row matrix remains unreconciled.
