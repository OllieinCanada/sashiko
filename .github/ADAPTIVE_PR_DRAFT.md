# Draft PR — publication not approved

Proposed title: Add opt-in publication cooldown for complete mail revisions

## Problem and resulting behavior

Complete mailing-list revisions from one author can cluster public review
notifications. Add an explicitly enabled per-list publication cooldown based
on recent unique complete revisions. Review computation continues while
findings await release. Successful clean reviews and authorized early release
retain their exceptions; lists without explicit enablement retain legacy
fixed-embargo behavior.

Persist one admission and one frozen effective deadline per complete canonical
revision. Replays, duplicate parts and restarts cannot add events or extend an
old decision. Use local admission time, not email Date, and take the longer
of legacy embargo and adaptive increment. Numeric templates cannot enable
a list. Multiple configured list matches select shared legacy policy,
including an opted-out list.

Canonical ownership conflicts quarantine the exact owner set. Stage every
member in batches of 64, activate the complete guard atomically, then transfer
protection to durable owner blocks in bounded batches with restart recovery.
Preserve source-owner quarantine before rewriting existing message/thread
bindings, including ingestion without an adaptive context.

## Source and validation

Base: 026195ab58e2099e81017adbc6b97f33c509c8ba.
Review head: d7f7a5516cc805444f23c534199af7e65d51e551.
Tested head: a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9.
Identical tree: 9a92a08ab85001d30c037811f4546381e22dbeab.
Branch: codex/adaptive-cooldown-review-20261020.

Eight signed-off source-only commits: upstream Clippy compatibility,
superseded held-review cleanup, adaptive policy/accounting/scheduling,
bounded conflict groups, consolidated quarantine reads, design limits,
compatible direct SHA hex encoding, and lazy source-owner lookup. No .github
audit/workflow files enter this contribution.

Formatting and all three Clippy profiles pass. Full native suite:
**1126 passed, zero failed, two ignored**. Final fixtures pass production
ingestion/publication, replay, restart, conflict recovery, 16-handle
concurrency, actual SIGKILL, software I/O faults, process clock changes,
stdio cancellation, historical read-only replay and stopped schema-16
rollback. A separate check passes 1024 actual parts and reopened admission
replay. Compiled mutants fail their intended regressions.

The exact upstream base passed 1073 tests with two ignored. Its four known
Clippy large-response failures are separately reproduced; the first
prerequisite scopes compatibility allowances to those extractor responses.
Baseline evidence is explicitly reused from the same exact base/toolchain.

Eighteen file-backed debug samples pass unchanged three-repetition median
budgets: disabled/upstream 1.1713/1.1546 and enabled/disabled 1.1482/1.1445
at 0/10000 retained owners. Disabled legacy state projections match upstream.
One individual disabled pair is 1.304; prior revisions failed median budgets.
All samples and failures remain recorded. These are workload measurements,
not production latency bounds. No email or token savings are claimed.

[Exact evidence and commands](https://github.com/OllieinCanada/sashiko/blob/codex/held-series-ci-20261019/.github/ADAPTIVE_UPSTREAM_REFRESH.md)
and [machine-readable manifests](https://github.com/OllieinCanada/sashiko/blob/codex/held-series-ci-20261019/.github/adaptive-upstream-refresh-evidence.json).

## Policy and operational limits

- From is an unauthenticated ASCII mailbox; forgery can affect another author's
  scope. Conflicts may quarantine an identity until operator repair.
- Explicit enablement, positive adaptive parameters and cross-post fallback
  require maintainer policy agreement.
- Limits of 31 days, seven days, 1024 parts and 4096 history rows are
  implementation ceilings, not rollout defaults.
- Canonical scans, owner-vector memory, same-handle mutex occupancy,
  permanent tombstones and total storage remain unbounded. Owner batching
  does not establish global latency or fairness.
- A delivery already claimed before guard activation may finish afterwards.
- Rollback requires stopped workers, quiesced affected work and an untouched
  complete backup. Old binaries do not understand active conflict guards.
  No new old-version work may be overwritten by restoring the backup.
- Fault injection is a software model; cancellation uses a local mock provider.
  No live SMTP acknowledgment or physical power-loss guarantee is claimed.

## Outstanding before publication

Maintainer policy agreement remains absent. The required Sashiko agent review
on the final source timed out after one bounded generation; no completed
review is claimed, and automatic paid execution is disabled. Resolve those
gates and valid review findings before requesting separate PR publication
approval. After publication, act on every upstream sashiko-bot finding.

Historical 55 verified/eight partial/one blocked counts are not a fresh
certification of all 64 scenarios. Recheck upstream and migration numbering
before publication, especially if PR #685 using migration 014 lands first.
This candidate uses migrations 014, 015 and 016.
