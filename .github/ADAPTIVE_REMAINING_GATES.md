> **Historical baseline evidence.** The results and 55/8/1 counts below describe
> source bd59059f1864aea81b11b5de0eb97e5d2ec53667. The fork now has a
> [bounded-conflict follow-up](ADAPTIVE_CONFLICT_BOUNDING.md) with schema 16.
> These historical counts do not certify the new candidate; extended validation
> and completion gates remain open.

# Remaining acceptance decisions

The ten scenarios below were reviewed individually. Documentation records
technical justification and limits; it does not waive requirements or invent
maintainer agreement. Source remains bd59059f1864aea81b11b5de0eb97e5d2ec53667.

| ID | Current disposition | Executed or inspected support | Limitation | Required resolution |
| --- | --- | --- | --- | --- |
| A02 | Maintainer policy decision | Omitted and explicit false cases pass through real ingestion. Numeric defaults never enable a list. Explicit enablement is a per-list decision. | This deliberately does not inherit an enabled flag. The condensed requirement does not determine a different boolean-inheritance policy. | Accept explicit per-list enablement and false/omitted behavior, or specify a different inheritance rule. |
| A03 | Maintainer policy decision | Existing fixed-embargo zero/NULL and inherited numeric settings pass. Invalid enabled adaptive limits are rejected. | Enabled adaptive window/step/cap must be positive; permitting zero is a policy change, not a missing arithmetic test. | Accept positive-only adaptive parameters or define zero meanings before changing validation. |
| A06 | Maintainer policy decision | Nineteen actual ingestion cases, each replayed twice, include To/Cc/NNTP matches, ignored authors, cross-posts and opt-outs. | Multiple configured matches deliberately select shared legacy handling; they do not choose the strongest adaptive policy. | Accept cross-post legacy fallback, including one opted-out list, or choose an explicit precedence rule. |
| D06 | Unresolved resource exception | Paused external transport permits unrelated writes; independent-writer contention controls pass. Ordinary bounded accounting uses indexed history and bounded part validation. | An indivisible canonical ownership group is quarantined in one writer transaction. Its size and writer-hold time do not have a general finite bound. | Maintainer acceptance of this explicit exception or a designed, validated reconciliation/quarantine redesign. Existing ordinary-workload timings do not waive it. |
| F02 | Unresolved adversarial identity policy | Normalized author/list scope and capped frozen time delay are tested; malformed identities do not share an unknown key. | From is not authenticated. Spoofing a victim address can affect that scope. Conflicting source/Message-ID ownership is fail-closed and can remain quarantined until operator repair; the time-delay cap is not a quarantine-duration cap. | Accept the trust/quarantine tradeoff for opt-in lists or require authenticated identity/provenance and define conflict recovery. Do not claim spoof-resistant attribution. |
| F04 | Unresolved retention/resource policy | Maximum supported parts, bounded indexed history, pruning and 10, 000 archived owners are exercised. Replays retain frozen deduplication ownership. | Permanent tombstones grow with unique revisions; indivisible quarantine groups remain unbounded. There is no fixed global storage guarantee. | Accept retention growth/operational capacity planning, or specify safe expiration/replay-horizon semantics and redesign. Deleting tombstones to make a test pass would break replay protection. |
| F05 | Bounded validation; broader input bound unresolved | 64 SQL-like payloads replay without schema change; 41 invalid authors and six invalid IDs reject, with valid controls. Compact-source facts and a 1 MiB subject are exercised. | This is not exhaustive MIME fuzzing or a universal allocation proof. Parsing, hashing/compression and preprocessing still do work proportional to untrusted input before the writer lock. | Accept the recorded incremental-feature scope, or define upstream ingestion size/time budgets and run a wider parser/allocation audit before claiming the full requirement. |
| F06 | VERIFIED within recorded affected-workflow scope | Strict transport PID disappearance, lease/reopen/single recording, admission abort/rollback/retry, and active-review provider-future/permit/child cleanup pass. Full restored-source1,111 tests and required profiles pass. | Remote delivery accepted before cancellation cannot be recalled; this does not prove every possible unrelated detached-task interleaving. | Preserve the tested scope and remote acknowledgement limitation; no current cancellation-fixture gap remains. |
| F07 | Bounded diagnostic audit; broader logging scope unresolved | Held/quarantined public handlers and tracing pass three fake canaries, with authorized positive views. Budget proxy self-tests keep reflected provider secret/private canaries out of manifests. | This is not an exhaustive audit of every upstream provider/debug logging path. Existing Gemini error classification can log provider error bodies after secret-pattern redaction; arbitrary private text is not universally removed. | Accept a defined new-feature diagnostic scope or separately audit/change broader provider logging. Do not equate token-pattern redaction with complete content privacy. |
| H07 | VERIFIED within stopped-system rehearsal scope | Actual candidate/old/candidate daemons reached health and reviewer startup, then stopped. Exact pending-state equality held before backup and after untouched restore/restart; native resume selection passes. | Review concurrency0 is a controlled pause; transports dry-run and runtime egress refused. No new work during old access; not a live rolling downgrade or remote delivery acknowledgement test. | Use only the documented stopped-system procedure; preserve the operational assumptions. |

Evidence identifiers refer to the [acceptance matrix](ADAPTIVE_ACCEPTANCE_MATRIX.md).
The strict cancellation run is
[39336545890](https://github.com/OllieinCanada/sashiko/actions/runs/39336545890);
the actual-daemon rehearsal outcome is recorded in the completion-gate report.

## Source evidence for limits

- [Canonical candidate scan](https://github.com/OllieinCanada/sashiko/blob/bd59059f1864aea81b11b5de0eb97e5d2ec53667/src/db.rs#L6705)
  has no result-count limit for the matching thread/author/date group.
- [Atomic quarantine](https://github.com/OllieinCanada/sashiko/blob/bd59059f1864aea81b11b5de0eb97e5d2ec53667/src/db.rs#L7003)
  processes the matching ownership group under one transaction; ordinary
  bounded history queries do not bound this group.
- [Cooldown persistence](https://github.com/OllieinCanada/sashiko/blob/bd59059f1864aea81b11b5de0eb97e5d2ec53667/src/db/cooldown.rs)
  prunes history used for counting but retains ownership/deduplication state.
- [Existing provider diagnostics](https://github.com/OllieinCanada/sashiko/blob/bd59059f1864aea81b11b5de0eb97e5d2ec53667/src/ai/gemini.rs#L332)
  can log error bodies after secret-pattern redaction. This provider file is
  unchanged by the candidate; the new handler/proxy canary checks are not a
  complete audit of every pre-existing provider/debug path.

## Policy and upstream coordination

The [prepared RFC](ADAPTIVE_MAINTAINER_POLICY_RFC.md) asks for explicit decisions.
Posting it through the connector returned403 Resource not accessible by
integration. No policy issue or maintainer approval exists.

[Upstream PR 685](https://github.com/sashiko-dev/sashiko/pull/685) is still open
and introduces migration 014 for lineage/cover reviews. The candidate currently
uses014 for the held-series index and 015 for adaptive persistence on current
main. If PR 685 lands first, rebase, renumber migrations and repeat applicable
upgrade/integration/model checks. That unmerged branch is not validated here.

The required Sashiko self-review also remains incomplete after two bounded
attempts; the follow-up returned HTTP 503. No additional model calls run
automatically. Agreement, required redesign and successful review cannot be
replaced by checklist status changes.
