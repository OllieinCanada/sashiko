# Adaptive cooldown acceptance evidence

Status: **not ready for submission**. 50 VERIFIED, 12 PARTIAL, 2 BLOCKED of 64 scenarios. A verified row applies only within its recorded scope; it does not waive separate completion gates.

Source: the user's pasted 64-row condensed master checklist. These are requirements to verify, not a claim that the inaccessible original attachment has been reread.

Production checkpoint: `bd59059f1864aea81b11b5de0eb97e5d2ec53667`.
Upstream base: `7f92f869a960a20f7d395550b4879d897ebdf4ea`, observed unchanged at 20:39 UTC on 2026-10-19.
Native suite checkpoint: `dbe259abb32b5f585f020ce7faee96694e8869c4`; only the two fork workflow files listed in the JSON differ from the production checkpoint.
Source-only bundle HEAD: `fa8a32646362a11ce00b7a90a14df3af828465d3`, tree `178107288293535d3adeaf180ba0328b9da6714a`. These are checked bundled commits, not a published GitHub branch.

See [execution report](ADAPTIVE_EXECUTION_1_5.md), [machine-readable matrix](adaptive-acceptance-matrix.json), and [analytical evidence](adaptive-execution-1-5.json).

## Evidence index

- **[SUITE](https://github.com/OllieinCanada/sashiko/actions/runs/39320690309)** — Production-equivalent dbe259: fmt, Clippy all/minimal/cache, 1032 library +49 main +7 CLI +23 integration =1111 pass;2 ignored.
- **[FOCUS](https://github.com/OllieinCanada/sashiko/actions/runs/39320285627)** — Final source exact-duplicate/failed-review/starvation/publication claims; dates8x2TZ;12 legacy settings cases;adaptive ACL;actual minimal/cache --no-ai CLI; unknown flag.
- **[CONFIG](https://github.com/OllieinCanada/sashiko/actions/runs/39320285705)** — Six DB recovery/pruning/config fixtures on final source; FOCUS supplies twelve actual ingestion compatibility combinations.
- **[SQLITE](https://github.com/OllieinCanada/sashiko/actions/runs/39320285705)** — Query-only/busy writers, pruning, stale leases, disable/cancel/reopen and source selection.
- **[ROUTE](https://github.com/OllieinCanada/sashiko/actions/runs/39320285605)** — Natural30-second expiry; restarted workers; recording sendmail; paused transport with independent writer. Completed review supplied as fixture.
- **[NATIVE](https://github.com/OllieinCanada/sashiko/actions/runs/39320285829)** — Final-source maximum1024-part actual series, injected history-read failure, separate-process restart, and prior-query reference paired comparison all PASS. Reference is candidate logic with prior owner-query shape, distinct from matched upstream baseline.
- **[FAULT](https://github.com/OllieinCanada/sashiko/actions/runs/39320285708/artifacts/12219503429)** — ENOSPC/EIO/torn WAL writes and SIGKILL before/after COMMIT. Software model, not physical power loss.
- **[CONCUR](https://github.com/OllieinCanada/sashiko/actions/runs/39320285821/artifacts/12218509418)** — 16 handles;128 admissions;128 replays;64 releases;8 scopes on final source.
- **[OLD](https://github.com/OllieinCanada/sashiko/actions/runs/39320285661/artifacts/12219787348)** — Stopped old-code DB compatibility, unsafe negative, untouched backup, exact15-table restore and resumed pending work. Not live daemon downgrade.
- **[PERF](https://github.com/OllieinCanada/sashiko/actions/runs/39320285590/artifacts/12220276794)** — Final matched upstream/base/disabled/enabled18samples; frozen ratio-of-medians<=1.20/1.50 pass; legacy tuples equal. Raw individual fresh pair1.2392 exceeds20%; prior FAIL_BUDGET runs preserved.
- **[PROBE](https://github.com/OllieinCanada/sashiko/actions/runs/39320285682/artifacts/12219638673)** — Calibrated SQL API counters and writer distributions, separate instrumented-debug run; prior844.91ms and finalbaseline150.31ms outliers preserved.
- **[MUT](https://github.com/OllieinCanada/sashiko/actions/runs/39320285657/artifacts/12220621203)** — 8 compiled semantic mutants killed, targeted positives/unrelated controls/restored replay; negative contexts inspected separately.
- **[PREP](https://github.com/OllieinCanada/sashiko/actions/runs/39320285692/artifacts/12218764477)** — Three clean DCO-signed commits; make check-pr before each; make sob after each; clean source-only bundle.
- **[INSPECT](https://github.com/OllieinCanada/sashiko/actions/runs/39321984128/artifacts/12219849932)** — Verified bundle HEAD/tree/source equivalence, patch SHA256, DCO trailers, all3 makecheck-pr summaries and8 semantic mutation failure contexts; no rebuilding/model calls.
- **[HISTORICAL](https://github.com/OllieinCanada/sashiko/actions/runs/39320939517/artifacts/12219539032)** — Harness compiles; source fixture readonly write-negative passes. Actual archive replay BLOCKED: HTTPS403 and NNTP timeout on prior bounded attempt; replay_performed=false.
- **[RFC](https://github.com/OllieinCanada/sashiko/blob/codex/held-series-ci-20261019/.github/ADAPTIVE_MAINTAINER_POLICY_RFC.md)** — Ready-to-post policy proposal; posting403; no issue/agreement.
- **[MODEL](https://github.com/OllieinCanada/sashiko/actions/runs/39316716214)** — MissingLLM_API_KEY confirmed by hosted readiness and user. Budget controls offline-pass; no modelreview/call/spend.

## A. Configuration and compatibility

### A01 — VERIFIED

Default/absent setting preserves all existing behavior.

Evidence: FOCUS 12-case omitted/disabled/inheritance/fixed-delay ingestion matrix; PERF legacy tuples equal; SUITE legacy no-intent/event control.

Scope / remaining: Existing configuration behavior retained in the exercised combinations; no universal all-input proof.

### A02 — PARTIAL

Explicitly disabled differs correctly from omitted.

Evidence: FOCUS explicit false and omitted through ingestion, with numeric templates; CONFIG strict enablement.

Scope / remaining: Behavior is tested; confirm omitted/false inheritance semantics with maintainers.

### A03 — PARTIAL

Zero delays and inherited settings retain their meanings.

Evidence: FOCUS fixed embargo omitted/0/2 across inherited/omitted/disabled settings; independent expected None/+7200.

Scope / remaining: Legacy zero/NULL semantics verified; adaptive zero-limit rejection remains a policy agreement question.

### A04 — VERIFIED

Invalid limits and contradictory settings fail safely.

Evidence: explicit_enablement_templates_and_strict_types; hand_checked_linear_thresholds_and_composition.

Scope / remaining: Bounds, strict types, step/cap contradictions and overflow reject; resource ceilings are not deployment defaults.

### A05 — VERIFIED

Unknown configuration fields and CLI options are rejected.

Evidence: CONFIG unknown/invalid TOML; FOCUS unknown CLI flag rejects with exit2 in both minimal profiles.

Scope / remaining: Relevant parser behavior tested; no automatic acceptance of misspelled options.

### A06 — PARTIAL

Cross-posted lists respect precedence and opt-outs.

Evidence: CONFIG source/recipient matrix; test_cooldown_crosspost_before_admission_is_legacy.

Scope / remaining: Current policy sends any cross-post through shared legacy handling. Maintainer agreement and a full precedence/opt-out matrix are missing.

### A07 — VERIFIED

Configuration reaches the actual production workflow.

Evidence: ROUTE; test_cooldown_config_to_real_release_and_sendmail.

Scope / remaining: Real policy file -> parsed NNTP article -> admission/release worker -> recording sendmail; completed review is a fixture.

### A08 — VERIFIED

Existing local review commands and feature profiles still work.

Evidence: SUITE three Clippy profiles; FOCUS actual --project sashiko review --no-ai --agent under minimal and minimal+cache.

Scope / remaining: Both real no-AI commands return complete one-patch JSON; outbound proxy refuses network. This is CLI compatibility, not model self-review.


## B. Identity and submission accounting

### B01 — VERIFIED

One patch series counts once, regardless of patch count.

Evidence: NATIVE maximum 1024-part series; PERF mixed 1/2/4/8-part series; incomplete/out-of-order regression.

Scope / remaining: One event per complete canonical revision; covers and individual parts do not multiply activity.

### B02 — VERIFIED

Duplicate messages and replays cannot count twice.

Evidence: test_cooldown_incomplete_out_of_order_and_duplicate; ROUTE three delivered-message replays; CONCUR.

Scope / remaining: Frozen decisions and event counts remain unchanged after replay.

### B03 — VERIFIED

Simultaneous duplicate submissions create one event.

Evidence: SUITE/FOCUS test_cooldown_same_message_concurrent_replay_preserves_owner; MUT stale-snapshot deletion killed.

Scope / remaining: Independent handles/barrier four trials plus deterministic stale-snapshot case. Identical replay preserves one owner/event; changed payload remains quarantined.

### B04 — VERIFIED

Concurrent revisions cannot lose accounting updates.

Evidence: test_cooldown_distinct_connections_serialize_author_history; CONCUR.

Scope / remaining: 16 independent handles, 128 admissions, eight scopes, exact saturated-count distribution.

### B05 — VERIFIED

One author's activity cannot penalize another.

Evidence: test_cooldown_deadline_boundary_clean_exception_and_isolation; author-scope mutant in MUT.

Scope / remaining: Distinct author has zero prior activity; removing author scope is detected.

### B06 — VERIFIED

Author identity is normalized without merging unknown authors.

Evidence: identity_normalization_has_no_unknown_bucket; CONFIG invalid-author case.

Scope / remaining: ASCII bare mailbox normalization; malformed/unsupported identities error instead of sharing an unknown key. From is unauthenticated.

### B07 — VERIFIED

Late, incomplete, and out-of-order series are handled.

Evidence: test_cooldown_incomplete_out_of_order_and_duplicate; real_versions_and_late_cover_remain_separate; unbound_adopted_cover_cannot_admit.

Scope / remaining: Unresolved provenance cannot promote Pending; frozen revisions cannot be extended silently.

### B08 — VERIFIED

Series-size metadata is validated against manipulation.

Evidence: maximum-series control; owned_content_cannot_change_without_context; same_version_extension_cannot_escape_frozen_owner; large_source_metadata_is_compact_during_admission.

Scope / remaining: Actual unique indices and source metadata are checked; changed denominator/content quarantines the owner.


## C. Timing and cooldown logic

### C01 — VERIFIED

First submission and burst thresholds produce expected delays.

Evidence: hand_checked_linear_thresholds_and_composition; test_cooldown_hand_trace_scope_and_window.

Scope / remaining: Independent threshold table checks first, burst, linear step and saturation.

### C02 — VERIFIED

Larger series follow the defined limits without overflow.

Evidence: NATIVE 1024 real parts; core policy bounds/overflow tests.

Scope / remaining: Current v1 policy has no size multiplier. Policy agreement is an independent completion gate.

### C03 — VERIFIED

Time-window boundary cases are correct.

Evidence: test_cooldown_hand_trace_scope_and_window.

Scope / remaining: History uses (t-W,t]; event exactly on excluded lower boundary drops from the count.

### C04 — VERIFIED

Inactivity resets or decays the cooldown correctly.

Evidence: test_cooldown_hand_trace_scope_and_window; seeded_restart_replay_trace.

Scope / remaining: Sliding-window expiration resets the count; no separate exponential decay is implemented.

### C05 — VERIFIED

Forged or incorrect email dates cannot bypass the cooldown.

Evidence: FOCUS test_cooldown_untrusted_dates_use_local_admission_time.

Scope / remaining: Eight parsed Date cases:1970/2100/invalid/9999 and both DST offsets, under UTC and America/New_York. Deadline computed from bounded local UTC admission.

### C06 — PARTIAL

Clock changes, time zones, and timestamp limits are tested.

Evidence: SUITE backward-clock/negative/overflow/window-boundary tests; FOCUS eight untrusted dates in UTC and America/New_York.

Scope / remaining: TZ/DST/header extremes now exercised; no comprehensive real wall-clock forward-jump scheduling matrix.

### C07 — VERIFIED

Reviews release at the deadline, never prematurely.

Evidence: test_cooldown_deadline_boundary_clean_exception_and_isolation; ROUTE natural 30-second expiry.

Scope / remaining: No ordinary release at deadline-1; release at deadline. Existing clean/authorized-override exceptions remain valid eligibility paths.

### C08 — VERIFIED

Continuous new submissions cannot postpone an old review forever.

Evidence: deadline_boundary_clean_exception_and_isolation; frozen replay tests; seeded trace.

Scope / remaining: Later activity does not move an earlier frozen decision; incremental delay is capped.


## D. Database, concurrency and recovery

### D01 — VERIFIED

Fresh databases and upgraded databases both work.

Evidence: SUITE fresh migrations, v8/v10 and complete v11 fixture; interim_version14_upgrade_preserves_decision.

Scope / remaining: Schema 15 retains prototype decisions and repairs the held-series index.

### D02 — VERIFIED

Deadlines and duplicate protection survive restarts.

Evidence: NATIVE separate-process restart; FAULT post-COMMIT recovery; restart_preserves_decision_and_release.

Scope / remaining: Reopened workers and processes preserve frozen values and deduplication.

### D03 — VERIFIED

Failed transactions leave no partially committed state.

Evidence: history_failure_rolls_back_and_retries; SQLITE recovery; FAULT ENOSPC/EIO/precommit/torn-write.

Scope / remaining: Failed target admission leaves no patch/event; successful retry records one target event.

### D04 — VERIFIED

Crash recovery preserves committed work.

Evidence: FAULT before/after COMMIT and partial WAL write; NATIVE process exit after commit.

Scope / remaining: SIGKILL/torn-write software model passed integrity checks. Physical electrical power loss is not demonstrated.

### D05 — VERIFIED

Concurrent database connections cannot corrupt decisions.

Evidence: CONCUR; two independent-connection regressions.

Scope / remaining: 128 events and replay/release snapshots remain consistent. Scope is the tested bounded workload.

### D06 — PARTIAL

Slow operations do not block unrelated writers.

Evidence: PROBE paused collaborator; ROUTE gated sendmail; deliberate contention calibration.

Scope / remaining: External pauses permit unrelated writes. Unbounded indivisible canonical-owner quarantine remains a documented exception; broad load/fairness is not established.

### D07 — VERIFIED

Database failures are visible and handled safely.

Evidence: SQLITE read-only/busy controls; FAULT; outbox_and_release_queries_propagate_cursor_step_errors.

Scope / remaining: Failures surface as errors and do not silently publish or fall back to legacy admission.

### D08 — VERIFIED

History cleanup, configuration changes, and rollback preserve pending work.

Evidence: SQLITE event pruning/config reload; OLD untouched15-table backup restore and pending-work resume.

Scope / remaining: Processes stopped; no new work during old-code rehearsal. Old-code scratch state cancels work; untouched backup preserves and restores runnable pending state. Not live rolling downgrade.


## E. Publication and existing protections

### E01 — VERIFIED

Held findings cannot be sent before release eligibility.

Evidence: ROUTE; live_claims_and_null_patch_notification; quarantine API regression; SQLITE stale leases.

Scope / remaining: Checks ordinary mail, NULL patch notifications and live claim guards. Remote acceptance already completed cannot be recalled.

### E02 — VERIFIED

Successful clean reviews retain existing immediate-release behavior.

Evidence: test_clean_patchset_is_releasable_before_embargo_expiry; adaptive deadline_boundary_clean_exception_and_isolation.

Scope / remaining: A complete successful no-finding review remains eligible before its time deadline.

### E03 — VERIFIED

Failed or incomplete reviews cannot masquerade as clean.

Evidence: SUITE/FOCUS test_cooldown_failed_and_partial_reviews_are_not_clean; no-AI predicate tests.

Scope / remaining: Enabled adaptive release matrix covers Failed/Pending/Skipped/missing/partial and literal mixed Reviewed+Failed with target2.

### E04 — VERIFIED

Superseded versions are cancelled without blocking newer ones.

Evidence: held supersession prerequisite regressions; held-series partial-index/candidate-capacity checks.

Scope / remaining: Unpublished Reviewed predecessors and unsent outboxes cancel atomically; release race remains protected.

### E05 — VERIFIED

Multiple workers cannot claim the same queue item incorrectly.

Evidence: SUITE/FOCUS test_cooldown_independent_publication_claims_have_one_winner.

Scope / remaining: Two independent handles race release/email/Patchwork claims; exactly one winner for each eligible item. Frozen past legacy deadline fixture is explicit.

### E06 — VERIFIED

Retries, leases, and cooldown deadlines cooperate correctly.

Evidence: SQLITE stale lease quarantine/reopen; ROUTE expiry/restart/replay; release claim lease tests.

Scope / remaining: Expired claims are rechecked against live guards. Exactly-once SMTP acceptance/acknowledgement is outside this evidence.

### E07 — VERIFIED

Authorized early release works; unauthorized release is denied.

Evidence: SUITE/FOCUS test_adaptive_release_patchset_embargo_authorization_and_endpoint.

Scope / remaining: Existing role/visibility/authorization endpoint matrix reused with persisted decided adaptive owner and future fixed embargo. Earned adaptive-extra hold covered separately.

### E08 — PARTIAL

Mailing-list rules, ignored authors, recipients, visibility, and integrations stay correct.

Evidence: CONFIG; FOCUS adaptive release ACL/visibility; recording recipients; refreshed upstream security/routing tests in SUITE.

Scope / remaining: Missing complete adaptive-enabled ignored-author/routing/integration combinations.


## F. Adversarial and edge cases

### F01 — VERIFIED

Held reviews cannot block eligible reviews behind them.

Evidence: SUITE/FOCUS test_cooldown_held_queue_head_does_not_starve_eligible_work.

Scope / remaining: Held head followed by eligible work, selector limit1, across review/outbox/release candidates; eligibility tested before limiting.

### F02 — PARTIAL

Forged identities or subjects cannot cause unbounded penalties.

Evidence: Identity validation, fixed increment cap, frozen deadlines, source/metadata quarantine.

Scope / remaining: No comprehensive adversarial/fairness corpus. Forged/shared From addresses can affect another person using the same key; document and obtain policy agreement.

### F03 — VERIFIED

Ambiguous series titles and revision histories do not collide.

Evidence: real_versions_and_late_cover_remain_separate; mixed_canonical_merge_blocks_before_moving_rows; late_cover_recovers_explicit_part_version.

Scope / remaining: Supported versions remain separate; unsupported ownership reconciliation quarantines before mutation.

### F04 — PARTIAL

Large series and activity histories remain resource-bounded.

Evidence: NATIVE 1024 parts; indexed bounded history; PROBE retained-owner comparison; pruning control.

Scope / remaining: Permanent tombstones are not globally storage-bounded; canonical multiowner quarantine is an unbounded indivisible group. No blanket bounded-writer claim.

### F05 — PARTIAL

Malformed input cannot cause injection or uncontrolled allocation.

Evidence: Strict config/mailbox/ID validation, bound checks and parameterized SQL; compact facts with 1 MiB subject.

Scope / remaining: No complete malformed-input fuzz/allocation bound audit across ingestion. Outside-writer preprocessing still allocates in proportion to input.

### F06 — PARTIAL

Cancellation cleans up tasks and prevents indefinite hangs.

Evidence: Cancellation regressions, timeout child-reaping tests, bounded hosted subprocesses, OLD quiescence.

Scope / remaining: Add adaptive-specific in-flight review/transport cancellation coverage; remote acceptance cannot be undone.

### F07 — PARTIAL

Diagnostics do not expose private information or credentials.

Evidence: Quarantine hides direct public review/log endpoints; general redaction tests; diagnostic counters omit SQL payloads.

Scope / remaining: No dedicated held-content/secret-canary audit over all new logs and manifests. Raw model review logging remains untested.

### F08 — BLOCKED

Read-only replay cannot alter real database or repository state.

Evidence: HISTORICAL read-only write-negative and compiled shadow harness; actual archive HTTPS403/NNTPtimeout.

Scope / remaining: No historical email replay performed. Requires an accessible actual public raw message/corpus; readonly source fixture is not real production state.


## G. Testing quality and performance

### G01 — VERIFIED

At least one integration test exercises the complete affected workflow.

Evidence: ROUTE and test_cooldown_config_to_real_release_and_sendmail.

Scope / remaining: Policy -> real parsed article -> DB -> completed-review fixture -> release worker -> recording transport. No model call; review-computation boundary is explicit.

### G02 — VERIFIED

Expected results are calculated independently of production code.

Evidence: Hand-checked threshold table; seeded small-state oracle; fixed expected concurrent count distribution.

Scope / remaining: Expected values are not obtained by invoking the production cooldown calculator.

### G03 — VERIFIED

Regression tests fail when their intended protection is removed.

Evidence: MUT8 compiled/killed mutants; INSPECT actual negative assertions/errors and unrelated controls.

Scope / remaining: Author scope,frozen replay,deadline,release marker,NNTPenablement,stale identical replay,source correction,and snapshot quarantine. No infrastructure failure counted as a killed mutant.

### G04 — VERIFIED

Generated tests reproduce restart, replay, and concurrency failures.

Evidence: Three seeded 96-admission traces; source-race regressions; CONCUR; process/crash controls.

Scope / remaining: Coverage is bounded and reproducible, not an exhaustive interleaving proof.

### G05 — VERIFIED

Small, large, and mixed workloads are tested.

Evidence: PERF 1000 series/3750 parts; NATIVE 1024-part series; compact metadata with 1 MiB subject; 10000 archived owners.

Scope / remaining: Generated/synthetic workload sizes are recorded; no historical replay is implied.

### G06 — VERIFIED

Measure enabled versus disabled performance and database costs.

Evidence: PERF18 raw final samples; PROBE calibrated counts; previous two FAIL_BUDGET18-sample runs retained in execution JSON.

Scope / remaining: Final ratio-of-medians:disabled/upstream1.1500/1.1486;enabled/disabled1.1137/1.1531. Fresh individual pair~1.2392 exceeds20%; not a production latency guarantee.

### G07 — VERIFIED

Run the required test suites on the exact final code revision.

Evidence: SUITE on dbe259; PREP three source commits; INSPECT final source-only tree equals bd590 across complete production paths.

Scope / remaining: Only fork workflow changes distinguish native checkpoint from production checkpoint. Re-run checks if production or upstream base changes.

### G08 — VERIFIED

Test harness detects invalid fixtures and misleading passes.

Evidence: Exact one-test assertions, compiler artifact checks, SQL calibration, OS fault-hit markers, SIGKILL exit checks, restored-source controls.

Scope / remaining: Earlier invalid fixtures and a wrongly selected mutation target are documented and corrected; no invalid pass is reused.


## H. Evidence, rollout and completion

### H01 — VERIFIED

Record tested commit, command, environment, logs, and outcome.

Evidence: SUITE/PREP/INSPECT/PERF/PROBE/FAULT/CONCUR/OLD and .github/ADAPTIVE_EXECUTION_1_5.md plus .github/adaptive-execution-1-5.json.

Scope / remaining: Exact source/base/tree/commands/environment/outcomes recorded. Artifacts expire after14days; analytical samples and summaries preserved in fork.

### H02 — VERIFIED

Distinguish upstream failures from newly introduced failures.

Evidence: Untouched7f stable-Rust1.99.1 four result_large_err errors isolated;1.90 baseline does not reproduce. PREP first compatibility commit passes1065tests; final1111tests pass.

Scope / remaining: Upstream lint compatibility patch is separate and function-scoped. Invalid Date cursor/config fixture and packaging failures are retained as harness defects, not production regressions.

### H03 — VERIFIED

Refresh against upstream and revalidate the final diff.

Evidence: Upstream7f refreshed; overlapping main/server hunks validated; SUITE/PREP/INSPECT and PERF final source revalidated.

Scope / remaining: Observed upstream still7f at20:39UTC. New upstream changes require fresh comparison; this does not close policy/model/coverage gates.

### H04 — VERIFIED

Do not claim email or token savings without real measurements.

Evidence: Design and reports make no savings claim; all review outputs are fixtures in deterministic tests.

Scope / remaining: Cooldown delays publication; no token/email reduction measurement or claim has been made.

### H05 — VERIFIED

Preserve negative results and document fairness tradeoffs.

Evidence: Previous FAIL_BUDGET runs, raw paired ratios and corrected harness failures retained; design limitations.

Scope / remaining: Includes unauthenticated/shared authors, cold history, retained storage and indivisible quarantine limitations.

### H06 — BLOCKED

Required model-assisted self-review is completed or explicitly marked blocked.

Evidence: MODEL hosted missing-key check; user explicitly confirms no provider key.

Scope / remaining: No authenticated Sashiko model review. Free-tier Gemini key is an option; paid fallback is not enabled. --no-ai and offline proxy tests do not satisfy review.

### H07 — PARTIAL

Rehearse dry-run, rollback, and pending-work preservation.

Evidence: ROUTE local recording transport; OLD unsafe negative, stopped quiescence, exact backup restore, pending resume.

Scope / remaining: Pending-state preservation is now demonstrated in stopped DB rehearsal. Full production-daemon rollback, operational dry-run and in-flight cancellation matrix remain unverified.

### H08 — VERIFIED

No unauthorized emails, pushes, deployment changes, secret leaks, or paid calls.

Evidence: Authorized fork-only checkpoints; temporary recording transports; no upstream PR/deployment/model calls.

Scope / remaining: No external mail or paid AI call was made by this work. Source publication remains separately gated.

## Additional completion gates

- **VERIFIED: Verify the feature is still missing in current upstream.** Adaptive config/accounting absent in inspected7f upstream; fixed embargo exists. Observed upstream unchanged20:39UTC.
- **PARTIAL: Recover historical tests and identify coverage gaps.** Existing regressions mapped and extended;64rows reconciled. Public archive replay blocked despite compiled readonly shadow harness.
- **OPEN: Get maintainer agreement on the intended cooldown policy.** Policy RFC prepared. Posting403; no issue or agreement. Zero values/crosspost/fairness/storage/atomic ownership exception require decisions.
- **PARTIAL: Implement the smallest defensible change.** Three source-only commits, guarded point-query optimizations and regressions. Scope/minimality and indivisible ownership exception still require maintainers/model review.
- **PARTIAL: Run all applicable regression and integration tests.** Required suite1111passes/2ignored; focused/fault/concurrency/restore/mutation and maximum-series/history-fault/process-restart checks pass.12PARTIAL and2BLOCKED rows remain.
- **VERIFIED: Validate performance and document tradeoffs.** Final matched median budgets pass unchanged;~15% disabled overhead and11-15% incremental enabled overhead measured. Prior failed budgets, individual outliers, querycounts and storage/writer exceptions preserved.
- **BLOCKED: Complete applicable Sashiko self-review requirements.** No provider key; no authenticated model review/spend. Required local model stage not complete; upstream bot stage waits separately approved PR.
- **PARTIAL: Confirm no regressions against upstream.** Refreshed final native suites green, legacy tuples match, upstream lint differences isolated. Remaining feature-specific matrix gaps mean no blanket no-regressions claim.
- **VERIFIED: Produce reproducible evidence with exact commit hashes.** Exact hashes/commands/environment and raw analytical samples preserved. Three-commit checked source bundle and patch hashes independently verified; downloadable raw logs expire14days.
- **PARTIAL: Prepare a clean PR for separate approval before publishing.** Clean three-commit source bundle and .github/ADAPTIVE_PR_DRAFT.md prepared. Policy/model/coverage blockers remain. No upstream PR opened.

## Definition of complete

The applicable tests pass, limitations are documented, existing behavior is preserved when disabled, and the implementation is ready for maintainer review—not merely that the checklist has been ticked.

There is no authenticated model review, no maintainer policy agreement, and no actual historical archive replay. No upstream PR was published. Earlier negative performance results and corrected fixture failures remain part of the evidence.
