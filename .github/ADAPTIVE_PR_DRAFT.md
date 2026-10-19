# Draft PR — not approved for publication

## Problem and behavior

Complete mailing-list revisions from one author can cluster review notifications.
Add an explicitly enabled per-list publication cooldown based on recent unique,
complete revisions. Review computation continues while findings await release.
Successful clean reviews and authorized early release keep their existing
exceptions. Lists without explicit enablement retain fixed-embargo behavior.

Each complete canonical revision counts once. Admission and the effective
deadline commit atomically; duplicate messages, replay and restart retain that
decision. New submissions cannot extend an old revision's frozen deadline.
The effective hold is the longer of the existing fixed embargo and the adaptive
delay. Per-list numeric templates cannot enable a list.

## Proposed commit structure

1. Four function-scoped Clippy allowances for the upstream handlers that return
   Axum extractor rejections as concrete responses. Keep authentication before
   body parsing, status codes and bodies unchanged. Untouched upstream reproduces
   the warnings; preserve its failing stable-Rust baseline.
2. Retire superseded series reviews still held for publication, cancelling their
   unsent outboxes atomically and preserving active-candidate capacity.
3. Add opt-in configuration, durable admission/accounting, frozen release
   scheduling, publication guards, operator documentation and regressions.

Fork-only workflows, fixtures, audit documents and model-budget preparation are
excluded from the source-only contribution.

## Policy and operational limitations requiring maintainer agreement

- Author identity is a normalized ASCII From mailbox, not authenticated ownership.
  A forged address can affect another author's apparent activity in that scope.
- Multiple configured To/Cc/NNTP matches use the shared legacy policy for the
  complete revision, including a list that opts out. Non-NNTP ingestion stays legacy.
- Resource ceilings (31-day window, 7-day cap, 1024 parts, 4096 history rows) are
  implementation ceilings, not recommended rollout defaults.
- Deduplication tombstones are retained permanently; global storage is not bounded.
- Mixed ownership must be quarantined atomically. An indivisible ownership group
  is an explicit unbounded writer exception; ordinary measured holds do not bound it.
- A rollback requires stopped ingestion/review/delivery and an untouched backup.
  An old binary must not operate on pending adaptive work without quiescing it.

The policy RFC is prepared in .github/ADAPTIVE_MAINTAINER_POLICY_RFC.md.
Posting upstream failed with GitHub 403; no maintainer agreement is claimed.

## Validation status

Production checkpoint bd59059f1864aea81b11b5de0eb97e5d2ec53667 is refreshed
against runtime base 7f92f869a960a20f7d395550b4879d897ebdf4ea.
The newer f6e2e172e1e669b6767a4c74fe91d062b41fd71c changes PRESS.md
only; it was merged and the source-only bundle rebuilt against it.
The checked source-only bundle contains three signed-off commits ending at
6667a81cd25a69feca76e65d94aacb4c83b2ce72, tree
d38b668f511e2e0972aa4588174a2c55f3582b30. Bundle HEAD is not a published branch.

The final restored-source run39333925430 at d9cc305c8e000add224b93800d21e3edcefc8f11
passes formatting, three Clippy feature profiles and the all-feature suite:
1,111 tests passed and two ignored. All eight new focused fixtures pass.
See .github/ADAPTIVE_DETERMINISTIC_EVIDENCE.md for exact hashes and scopes. Each source-only commit passed
make check-pr before creation and sign-off validation afterward. Independent
artifact inspection verified the earlier bundle's source equivalence, patch
hashes and actual test summaries. The refreshed documentation-only bundle
passed its native checks; independent artifact inspection has not been repeated. Fork-only evidence/checkpoint files are excluded.

Focused regressions cover identical concurrent submissions and stale snapshots,
failed/mixed/incomplete reviews, eligible work behind held queue heads,
independent competing release/email/Patchwork claims, eight untrusted dates in
two time zones, enabled-adaptive endpoint ACLs and 12 legacy settings cases.
Actual offline --no-ai reviews pass in minimal and minimal+cache profiles;
these are CLI compatibility checks, not model self-review.

Twelve compiled semantic mutants are detected, with positive/unrelated and
restored controls. Four additional guard-removal cases cover ignored-author
handling, private review visibility and active-review cancellation cleanup. Final-source maximum
series, process restart, 16-writer concurrency, SQLite fault/recovery/pruning,
software crash simulation, expiry/slow recording transport and stopped backup
restore/pending-work resume checks pass. None sends real mail.

Matched upstream performance passes unchanged ratio-of-medians limits:

| Archived owners | Disabled / upstream | Enabled / disabled |
| --- | ---: | ---: |
| 0 | 1.1500 | 1.1137 |
| 10,000 | 1.1486 | 1.1531 |

These are 3-sample medians of an instrumentation-free debug synthetic workload,
not production guarantees. Disabled mode retains about 15% measured overhead.
A final individual fresh pair exceeds 20%; two earlier revisions failed the
median budget. Their 18 samples each are retained alongside the final 18.
Calibrated query API counts fell from 8,750 to 1,250 extra calls over baseline;
this is not physical SQL statement count. Prior 844.91 ms and final-baseline
150.31 ms writer outliers are preserved without assigning an unproven cause.
No email-volume or model-token savings are claimed.

The historical replay harness compiles and rejects writes to its read-only
source fixture, but no actual archive replay ran: HTTPS returned 403 and NNTP
timed out. The source fixture is not a production database.

The 64-row matrix records 52 VERIFIED, 10 PARTIAL and two BLOCKED scenarios.
The new clock/routing/privacy/admission/transport and mock-provider cancellation
checks pass within their documented scopes. Policy agreement, actual model
self-review and the remaining feature-specific
coverage/operational gaps prevent a readiness claim.

## Self-review and publication gates

The required Sashiko model review has not run. The repository secret is now
present and provider authentication/model listing succeeded. Two tiny generation
probes returned HTTP 503 without usage metadata. Calls remain paused; no charge,
completed review or clean result is claimed. Initial plus at most one follow-up
remain bounded by the user's authorization.

Before publication: record final checks and exact hashes, obtain maintainer
policy agreement, complete model review and fix valid findings, refresh the
64-row evidence matrix, and obtain separate approval to publish the PR.
