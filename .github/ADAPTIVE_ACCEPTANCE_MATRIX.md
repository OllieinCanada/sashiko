# Adaptive cooldown: reconciled master checklist

This maps all 64 requirements supplied in chat to available source and executed
evidence. The pasted checklist has now been recovered: earlier reports calling
that input inaccessible are superseded by this reconciliation. The original
uploaded full prompt has not been reread; this matrix uses the supplied condensed
requirements verbatim.

**37 VERIFIED / 23 PARTIAL / 3 OPEN / 1 BLOCKED.** Only VERIFIED rows count toward
demonstrated scenario coverage (37/64, 57.8%). These are evidence statuses, not
an assertion that the feature is complete or that an external checklist UI has
been changed. Completion gates are assessed separately below.

VERIFIED means direct executed evidence supports the scoped scenario on the
audited source. PARTIAL retains a concrete missing clause or policy question.
OPEN means the specific case is not demonstrated. BLOCKED identifies a missing
prerequisite. A general suite pass alone does not verify a broad scenario.

## Source and upstream boundary

- Audited production source: 77eefacf3d54a24b7a639f06ac3e339422cc39eb.
- Tested upstream base: 715294a276efee9d39fbb55cf31eef267e96c7b1, libsql 0.10.0.
- Source-only bundled head: ecf8f138dac130324b88119eec19c87623c0cbe7;
  tree 5ac95fc07ae13f90a0d8fb59c27959810c1180b8.
- Upstream inspected during this reconciliation:
  7f92f869a960a20f7d395550b4879d897ebdf4ea, **16 commits newer**.
- Upstream changes overlap main.rs, reviewer.rs, server.rs, patch.rs,
  email_router.rs and worker/email.rs; Cargo.lock and other AI/tool paths also
  changed. Current upstream was not merged or tested in this audit.
- Upstream PR 685 remains open/unmerged; recheck migration numbering before PR.

The target adaptive per-list configuration/accounting is still absent in the
checked current upstream database and email-policy paths. Existing fixed
embargo behavior remains present.

Test names below refer to the audited source:
[core policy](https://github.com/OllieinCanada/sashiko/blob/77eefacf3d54a24b7a639f06ac3e339422cc39eb/src/cooldown.rs),
[adaptive DB tests](https://github.com/OllieinCanada/sashiko/blob/77eefacf3d54a24b7a639f06ac3e339422cc39eb/src/db/cooldown.rs),
[general DB tests](https://github.com/OllieinCanada/sashiko/blob/77eefacf3d54a24b7a639f06ac3e339422cc39eb/src/db.rs),
[server ACL/visibility tests](https://github.com/OllieinCanada/sashiko/blob/77eefacf3d54a24b7a639f06ac3e339422cc39eb/src/server.rs).
Abbreviated test names retain their unique suffix; many DB names start with
test_cooldown_.

## Evidence index

| Reference | Executed evidence | Scope |
| --- | --- | --- |
| SUITE | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023519) | Audited source 77eefac; formatting, Clippy all/local/cache, 1014 library + 47 main + 7 CLI + 23 integration tests passed; 2 ignored. |
| CONFIG | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023353) | Six SQLite/recovery/pruning/config source-selection controls on audited source. |
| SQLITE | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023353) | Readonly writer, busy writer, pruning, stale leases, disable/cancel/reopen and source selection. |
| ROUTE | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023501) | Natural expiry, reopened DB/workers, recording sendmail, paused transport and three actual NNTP replays. Completed review supplied as fixture. |
| NATIVE | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023530) | Maximum actual series, history read fault, separate-process restart and owner-query comparison. |
| FAULT | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023488/artifacts/12216685425) | ENOSPC, EIO, partial WAL write and SIGKILL before/after COMMIT. Software model, not physical power failure. |
| CONCUR | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311179413/artifacts/12216100956) | 16 independent DB handles, 128 admissions, 128 replays and 64 release markers over eight scopes. |
| OLD | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311353746/artifacts/12215806606) | Old/new native DB code on temporary fixture; unsafe copy, quiescence/cancellation and safe access. Not a production-daemon downgrade. |
| PERF | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023321/artifacts/12215842045) | Upstream base 715294a, disabled and enabled traces; unchanged ratio-of-medians limits; all raw samples retained. |
| PROBE | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023387/artifacts/12216626561) | Calibrated SQL API counters and writer boundary timing; independent diagnostic run. |
| MUT | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023419) | Five compiled, killed mutants; unrelated positive controls and restored replay. |
| PREP | [Run/artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39311023425/artifacts/12216560674) | Source-only commits pass make check-pr before creation and sign-off checks; bundled head ecf8f138dac130324b88119eec19c87623c0cbe7. |

## All 64 scenarios

### A. Configuration & compatibility

**A01 — PARTIAL: Default/absent setting preserves all existing behavior.**

Evidence: SUITE; PERF legacy tuple equality; test_cooldown_legacy_has_no_intent_or_events.

Remaining work / scope: Differential trace omits fixed embargo settings; complete the legacy configuration matrix.

**A02 — PARTIAL: Explicitly disabled differs correctly from omitted.**

Evidence: CONFIG; explicit_enablement_templates_and_strict_types.

Remaining work / scope: Confirm intended omitted/false inheritance semantics with maintainers and test both through ingestion.

**A03 — PARTIAL: Zero delays and inherited settings retain their meanings.**

Evidence: hand_checked_linear_thresholds_and_composition preserves None/Some(0); CONFIG templates.

Remaining work / scope: Validate database/route zero fixed-delay combinations. Adaptive zero limits are currently rejected; confirm that policy.

**A04 — VERIFIED: Invalid limits and contradictory settings fail safely.**

Evidence: explicit_enablement_templates_and_strict_types; hand_checked_linear_thresholds_and_composition.

Remaining work / scope: Bounds, strict types, step/cap contradictions and overflow reject; resource ceilings are not deployment defaults.

**A05 — PARTIAL: Unknown configuration fields and CLI options are rejected.**

Evidence: CONFIG strict TOML; test_rejects_unknown_fields_and_invalid_keys; test_unknown_project_is_rejected_by_the_parser.

Remaining work / scope: Add an explicit unknown CLI-flag rejection check for the relevant profiles.

**A06 — PARTIAL: Cross-posted lists respect precedence and opt-outs.**

Evidence: CONFIG source/recipient matrix; test_cooldown_crosspost_before_admission_is_legacy.

Remaining work / scope: Current policy sends any cross-post through shared legacy handling. Maintainer agreement and a full precedence/opt-out matrix are missing.

**A07 — VERIFIED: Configuration reaches the actual production workflow.**

Evidence: ROUTE; test_cooldown_config_to_real_release_and_sendmail.

Remaining work / scope: Real policy file -> parsed NNTP article -> admission/release worker -> recording sendmail; completed review is a fixture.

**A08 — PARTIAL: Existing local review commands and feature profiles still work.**

Evidence: SUITE includes all-feature tests and Clippy all/local/cache profiles; CLI smoke tests.

Remaining work / scope: Run local-review command smoke cases under each minimal feature profile; compile checks alone do not establish runtime behavior.

### B. Identity & submission accounting

**B01 — VERIFIED: One patch series counts once, regardless of patch count.**

Evidence: NATIVE maximum 1024-part series; PERF mixed 1/2/4/8-part series; incomplete/out-of-order regression.

Remaining work / scope: One event per complete canonical revision; covers and individual parts do not multiply activity.

**B02 — VERIFIED: Duplicate messages and replays cannot count twice.**

Evidence: test_cooldown_incomplete_out_of_order_and_duplicate; ROUTE three delivered-message replays; CONCUR.

Remaining work / scope: Frozen decisions and event counts remain unchanged after replay.

**B03 — PARTIAL: Simultaneous duplicate submissions create one event.**

Evidence: test_cooldown_two_connections_own_opposite_parts_once.

Remaining work / scope: This proves concurrent different parts converge on one owner, not simultaneous identical final-message submissions. Add that exact case.

**B04 — VERIFIED: Concurrent revisions cannot lose accounting updates.**

Evidence: test_cooldown_distinct_connections_serialize_author_history; CONCUR.

Remaining work / scope: 16 independent handles, 128 admissions, eight scopes, exact saturated-count distribution.

**B05 — VERIFIED: One author's activity cannot penalize another.**

Evidence: test_cooldown_deadline_boundary_clean_exception_and_isolation; author-scope mutant in MUT.

Remaining work / scope: Distinct author has zero prior activity; removing author scope is detected.

**B06 — VERIFIED: Author identity is normalized without merging unknown authors.**

Evidence: identity_normalization_has_no_unknown_bucket; CONFIG invalid-author case.

Remaining work / scope: ASCII bare mailbox normalization; malformed/unsupported identities error instead of sharing an unknown key. From is unauthenticated.

**B07 — VERIFIED: Late, incomplete, and out-of-order series are handled.**

Evidence: test_cooldown_incomplete_out_of_order_and_duplicate; real_versions_and_late_cover_remain_separate; unbound_adopted_cover_cannot_admit.

Remaining work / scope: Unresolved provenance cannot promote Pending; frozen revisions cannot be extended silently.

**B08 — VERIFIED: Series-size metadata is validated against manipulation.**

Evidence: maximum-series control; owned_content_cannot_change_without_context; same_version_extension_cannot_escape_frozen_owner; large_source_metadata_is_compact_during_admission.

Remaining work / scope: Actual unique indices and source metadata are checked; changed denominator/content quarantines the owner.

### C. Timing & cooldown logic

**C01 — VERIFIED: First submission and burst thresholds produce expected delays.**

Evidence: hand_checked_linear_thresholds_and_composition; test_cooldown_hand_trace_scope_and_window.

Remaining work / scope: Independent threshold table checks first, burst, linear step and saturation.

**C02 — VERIFIED: Larger series follow the defined limits without overflow.**

Evidence: NATIVE 1024 real parts; core policy bounds/overflow tests.

Remaining work / scope: Current v1 policy has no size multiplier. Policy agreement is an independent completion gate.

**C03 — VERIFIED: Time-window boundary cases are correct.**

Evidence: test_cooldown_hand_trace_scope_and_window.

Remaining work / scope: History uses (t-W,t]; event exactly on excluded lower boundary drops from the count.

**C04 — VERIFIED: Inactivity resets or decays the cooldown correctly.**

Evidence: test_cooldown_hand_trace_scope_and_window; seeded_restart_replay_trace.

Remaining work / scope: Sliding-window expiration resets the count; no separate exponential decay is implemented.

**C05 — PARTIAL: Forged or incorrect email dates cannot bypass the cooldown.**

Evidence: ROUTE ingests a 1970 Date while local admission establishes the live deadline; seeded hand trace uses independent admission timestamps.

Remaining work / scope: Add future, invalid and extreme Date-header variants through parsed ingestion.

**C06 — PARTIAL: Clock changes, time zones, and timestamp limits are tested.**

Evidence: test_cooldown_coverage_and_backward_clock_fail_closed; negative/overflow calculator tests.

Remaining work / scope: No explicit TZ/DST environment matrix or forward-jump scheduling matrix has run.

**C07 — VERIFIED: Reviews release at the deadline, never prematurely.**

Evidence: test_cooldown_deadline_boundary_clean_exception_and_isolation; ROUTE natural 30-second expiry.

Remaining work / scope: No ordinary release at deadline-1; release at deadline. Existing clean/authorized-override exceptions remain valid eligibility paths.

**C08 — VERIFIED: Continuous new submissions cannot postpone an old review forever.**

Evidence: deadline_boundary_clean_exception_and_isolation; frozen replay tests; seeded trace.

Remaining work / scope: Later activity does not move an earlier frozen decision; incremental delay is capped.

### D. Database, concurrency & recovery

**D01 — VERIFIED: Fresh databases and upgraded databases both work.**

Evidence: SUITE fresh migrations, v8/v10 and complete v11 fixture; interim_version14_upgrade_preserves_decision.

Remaining work / scope: Schema 15 retains prototype decisions and repairs the held-series index.

**D02 — VERIFIED: Deadlines and duplicate protection survive restarts.**

Evidence: NATIVE separate-process restart; FAULT post-COMMIT recovery; restart_preserves_decision_and_release.

Remaining work / scope: Reopened workers and processes preserve frozen values and deduplication.

**D03 — VERIFIED: Failed transactions leave no partially committed state.**

Evidence: history_failure_rolls_back_and_retries; SQLITE recovery; FAULT ENOSPC/EIO/precommit/torn-write.

Remaining work / scope: Failed target admission leaves no patch/event; successful retry records one target event.

**D04 — VERIFIED: Crash recovery preserves committed work.**

Evidence: FAULT before/after COMMIT and partial WAL write; NATIVE process exit after commit.

Remaining work / scope: SIGKILL/torn-write software model passed integrity checks. Physical electrical power loss is not demonstrated.

**D05 — VERIFIED: Concurrent database connections cannot corrupt decisions.**

Evidence: CONCUR; two independent-connection regressions.

Remaining work / scope: 128 events and replay/release snapshots remain consistent. Scope is the tested bounded workload.

**D06 — PARTIAL: Slow operations do not block unrelated writers.**

Evidence: PROBE paused collaborator; ROUTE gated sendmail; deliberate contention calibration.

Remaining work / scope: External pauses permit unrelated writes. Unbounded indivisible canonical-owner quarantine remains a documented exception; broad load/fairness is not established.

**D07 — VERIFIED: Database failures are visible and handled safely.**

Evidence: SQLITE read-only/busy controls; FAULT; outbox_and_release_queries_propagate_cursor_step_errors.

Remaining work / scope: Failures surface as errors and do not silently publish or fall back to legacy admission.

**D08 — PARTIAL: History cleanup, configuration changes, and rollback preserve pending work.**

Evidence: SQLITE pruning; policy_reload_preserves_decided_but_blocks_waiting; OLD.

Remaining work / scope: Event pruning retains tombstones. Rehearsed rollback cancels pending/held work; live preservation/resumption and a production-daemon downgrade remain unverified.

### E. Publication & existing protections

**E01 — VERIFIED: Held findings cannot be sent before release eligibility.**

Evidence: ROUTE; live_claims_and_null_patch_notification; quarantine API regression; SQLITE stale leases.

Remaining work / scope: Checks ordinary mail, NULL patch notifications and live claim guards. Remote acceptance already completed cannot be recalled.

**E02 — VERIFIED: Successful clean reviews retain existing immediate-release behavior.**

Evidence: test_clean_patchset_is_releasable_before_embargo_expiry; adaptive deadline_boundary_clean_exception_and_isolation.

Remaining work / scope: A complete successful no-finding review remains eligible before its time deadline.

**E03 — PARTIAL: Failed or incomplete reviews cannot masquerade as clean.**

Evidence: test_no_ai_review_is_not_clean; clean predicate and failure handling tests in SUITE.

Remaining work / scope: Add a feature-specific release matrix for failed, missing, partially completed and mixed review outputs.

**E04 — VERIFIED: Superseded versions are cancelled without blocking newer ones.**

Evidence: held supersession prerequisite regressions; held-series partial-index/candidate-capacity checks.

Remaining work / scope: Unpublished Reviewed predecessors and unsent outboxes cancel atomically; release race remains protected.

**E05 — PARTIAL: Multiple workers cannot claim the same queue item incorrectly.**

Evidence: Atomic claim SQL; sequential double-claim/lease tests; restarted-worker dedup in ROUTE.

Remaining work / scope: Add simultaneous independent release/email-worker claims for the same eligible item. Admission concurrency is not publication-claim concurrency.

**E06 — VERIFIED: Retries, leases, and cooldown deadlines cooperate correctly.**

Evidence: SQLITE stale lease quarantine/reopen; ROUTE expiry/restart/replay; release claim lease tests.

Remaining work / scope: Expired claims are rechecked against live guards. Exactly-once SMTP acceptance/acknowledgement is outside this evidence.

**E07 — PARTIAL: Authorized early release works; unauthorized release is denied.**

Evidence: test_release_patchset_embargo_authorization_and_endpoint; adaptive early-release and quarantine regressions.

Remaining work / scope: Shared ACL route and adaptive DB behavior are separately tested; add their combined enabled-adaptive endpoint matrix.

**E08 — PARTIAL: Mailing-list rules, ignored authors, recipients, visibility, and integrations stay correct.**

Evidence: CONFIG; recording recipient check; server visibility regressions; general router/worker tests.

Remaining work / scope: Missing complete adaptive-enabled ignored-author/routing/integration combinations. Upstream now changes relevant paths.

### F. Adversarial & edge cases

**F01 — OPEN: Held reviews cannot block eligible reviews behind them.**

Evidence: Eligibility predicates precede LIMIT in current selectors; no direct head-of-queue starvation fixture identified.

Remaining work / scope: Add held/waiting/quarantined head items followed by eligible review and outbox items, including worker limits.

**F02 — PARTIAL: Forged identities or subjects cannot cause unbounded penalties.**

Evidence: Identity validation, fixed increment cap, frozen deadlines, source/metadata quarantine.

Remaining work / scope: No comprehensive adversarial/fairness corpus. Forged/shared From addresses can affect another person using the same key; document and obtain policy agreement.

**F03 — VERIFIED: Ambiguous series titles and revision histories do not collide.**

Evidence: real_versions_and_late_cover_remain_separate; mixed_canonical_merge_blocks_before_moving_rows; late_cover_recovers_explicit_part_version.

Remaining work / scope: Supported versions remain separate; unsupported ownership reconciliation quarantines before mutation.

**F04 — PARTIAL: Large series and activity histories remain resource-bounded.**

Evidence: NATIVE 1024 parts; indexed bounded history; PROBE retained-owner comparison; pruning control.

Remaining work / scope: Permanent tombstones are not globally storage-bounded; canonical multiowner quarantine is an unbounded indivisible group. No blanket bounded-writer claim.

**F05 — PARTIAL: Malformed input cannot cause injection or uncontrolled allocation.**

Evidence: Strict config/mailbox/ID validation, bound checks and parameterized SQL; compact facts with 1 MiB subject.

Remaining work / scope: No complete malformed-input fuzz/allocation bound audit across ingestion. Outside-writer preprocessing still allocates in proportion to input.

**F06 — PARTIAL: Cancellation cleans up tasks and prevents indefinite hangs.**

Evidence: Cancellation regressions, timeout child-reaping tests, bounded hosted subprocesses, OLD quiescence.

Remaining work / scope: Add adaptive-specific in-flight review/transport cancellation coverage; remote acceptance cannot be undone.

**F07 — PARTIAL: Diagnostics do not expose private information or credentials.**

Evidence: Quarantine hides direct public review/log endpoints; general redaction tests; diagnostic counters omit SQL payloads.

Remaining work / scope: No dedicated held-content/secret-canary audit over all new logs and manifests. Raw model review logging remains untested.

**F08 — OPEN: Read-only replay cannot alter real database or repository state.**

Evidence: Existing generated/fault replays use temporary databases and restored ephemeral source.

Remaining work / scope: No historical read-only shadow-replay tool/corpus and pristine-state guard have been validated.

### G. Testing quality & performance

**G01 — VERIFIED: At least one integration test exercises the complete affected workflow.**

Evidence: ROUTE and test_cooldown_config_to_real_release_and_sendmail.

Remaining work / scope: Policy -> real parsed article -> DB -> completed-review fixture -> release worker -> recording transport. No model call; review-computation boundary is explicit.

**G02 — VERIFIED: Expected results are calculated independently of production code.**

Evidence: Hand-checked threshold table; seeded small-state oracle; fixed expected concurrent count distribution.

Remaining work / scope: Expected values are not obtained by invoking the production cooldown calculator.

**G03 — VERIFIED: Regression tests fail when their intended protection is removed.**

Evidence: MUT five compiled mutants with targeted negative tests and unrelated positive controls.

Remaining work / scope: Author scope, frozen replay, deadline comparison, release marker and NNTP eligibility mutants are killed.

**G04 — VERIFIED: Generated tests reproduce restart, replay, and concurrency failures.**

Evidence: Three seeded 96-admission traces; source-race regressions; CONCUR; process/crash controls.

Remaining work / scope: Coverage is bounded and reproducible, not an exhaustive interleaving proof.

**G05 — VERIFIED: Small, large, and mixed workloads are tested.**

Evidence: PERF 1000 series/3750 parts; NATIVE 1024-part series; compact metadata with 1 MiB subject; 10000 archived owners.

Remaining work / scope: Generated/synthetic workload sizes are recorded; no historical replay is implied.

**G06 — VERIFIED: Measure enabled versus disabled performance and database costs.**

Evidence: PERF; PROBE.

Remaining work / scope: Matched base/disabled/enabled medians, raw samples, SQL API counts and calibrated writer distributions recorded. One fresh pair exceeds the nominal ratio limit.

**G07 — PARTIAL: Run the required test suites on the exact final code revision.**

Evidence: SUITE and PREP pass on the audited source and source-only tree.

Remaining work / scope: The current candidate is tested; upstream refresh/final review may change it. Re-run on that exact final tree before submission.

**G08 — VERIFIED: Test harness detects invalid fixtures and misleading passes.**

Evidence: Exact one-test assertions, compiler artifact checks, SQL calibration, OS fault-hit markers, SIGKILL exit checks, restored-source controls.

Remaining work / scope: Earlier invalid fixtures and a wrongly selected mutation target are documented and corrected; no invalid pass is reused.

### H. Evidence, rollout & completion

**H01 — VERIFIED: Record tested commit, command, environment, logs, and outcome.**

Evidence: SUITE/PREP/PERF/PROBE/FAULT/CONCUR/OLD artifacts and workflows; round-3 report.

Remaining work / scope: Artifacts retain commands, hashes, native binaries or manifests and runner logs; retention is 14 days, so durable preservation remains necessary.

**H02 — PARTIAL: Distinguish upstream failures from newly introduced failures.**

Evidence: Matched upstream performance; prerequisite diagnostic; recorded harness failures.

Remaining work / scope: The latest upstream full suite has not been run. Refresh and compare failures explicitly before final attribution.

**H03 — OPEN: Refresh against upstream and revalidate the final diff.**

Evidence: Upstream now 7f92f869a960a20f7d395550b4879d897ebdf4ea, 16 commits beyond tested base.

Remaining work / scope: Refresh with overlapping main/review/email/server changes, inspect conflict resolutions and revalidate. PR 685 remains open/unmerged.

**H04 — VERIFIED: Do not claim email or token savings without real measurements.**

Evidence: Design and reports make no savings claim; all review outputs are fixtures in deterministic tests.

Remaining work / scope: Cooldown delays publication; no token/email reduction measurement or claim has been made.

**H05 — VERIFIED: Preserve negative results and document fairness tradeoffs.**

Evidence: Previous FAIL_BUDGET runs, raw paired ratios and corrected harness failures retained; design limitations.

Remaining work / scope: Includes unauthenticated/shared authors, cold history, retained storage and indivisible quarantine limitations.

**H06 — BLOCKED: Required model-assisted self-review is completed or explicitly marked blocked.**

Evidence: All reports explicitly mark required Sashiko review pending; no model invocation or spend.

Remaining work / scope: Disclosure requirement is met, but the mandatory completion gate is not. Secret readiness is unconfirmed.

**H07 — PARTIAL: Rehearse dry-run, rollback, and pending-work preservation.**

Evidence: ROUTE uses local recording transport; OLD rehearses stop/cancel and old DB access.

Remaining work / scope: No full production-daemon downgrade or complete dry-run/pending-work continuation matrix. Do not substitute cancellation evidence for preservation of runnable work.

**H08 — VERIFIED: No unauthorized emails, pushes, deployment changes, secret leaks, or paid calls.**

Evidence: Authorized fork-only checkpoints; temporary recording transports; no upstream PR/deployment/model calls.

Remaining work / scope: No external mail or paid AI call was made by this work. Source publication remains separately gated.


## Additional completion gates

| Requirement | Status | Assessment |
| --- | --- | --- |
| Verify the feature is still missing in current upstream. | VERIFIED | At upstream 7f92f869a960a20f7d395550b4879d897ebdf4ea, checked db.rs/email_policy.rs contain no adaptive_cooldown, CooldownContext or review_cooldown persistence/configuration. This is the target feature check, not an assertion that fixed embargoes are missing. |
| Recover historical tests and identify coverage gaps. | PARTIAL | Existing clean-review, no-AI, release-ACL, supersession and failure tests were inspected and mapped. The complete historical corpus/shadow replay and prior change-history audit are not complete. |
| Get maintainer agreement on the intended cooldown policy. | OPEN | No recorded upstream maintainer agreement. Resolve policy semantics, zero values, cross-post/opt-out precedence, author normalization/fairness, cap and indivisible ownership-group exceptions. No outreach was performed. |
| Implement the smallest defensible change. | PARTIAL | Prerequisite and feature are split in source-only artifacts; duplicate SQL reads were removed. Scope/minimality and the unbounded ownership exception still need maintainer/model review. |
| Run all applicable regression and integration tests. | PARTIAL | Audited candidate checks pass; 23 partial and 3 open scenario rows still identify missing coverage. Latest-upstream refreshed final tree does not yet exist. |
| Validate performance and document tradeoffs. | VERIFIED | Declared median screening limits pass on audited source; query reduction is measured. Raw fresh pair above 20%, synthetic workloads and writer outliers are explicitly retained; no production performance guarantee. |
| Complete applicable Sashiko self-review requirements. | BLOCKED | Required local Sashiko model review not run; provider-secret readiness unconfirmed. Subsequent upstream bot findings can only be handled after separately approved submission. |
| Confirm no regressions against upstream. | OPEN | Matched baseline/disabled trace is equal within its scope, but current upstream is 16 commits newer with overlapping changes. Full refreshed comparison and final-tree checks required. |
| Produce reproducible evidence with exact commit hashes. | VERIFIED | Evidence index records source, baseline, source-only tree, workflow commands, logs, hashes and outcomes. Artifacts have 14-day retention and need durable preservation. |
| Prepare a clean PR for separate approval before publishing. | PARTIAL | Clean two-commit source-only bundle and draft materials exist. Refresh, policy agreement, gaps and model review remain; no upstream PR was submitted. |

## Completion decision

**Not ready for submission.** The supplied definition requires applicable tests
to pass, limitations to be documented, disabled behavior to be preserved, and
the implementation to be ready for maintainer review. Ticking rows alone is
insufficient. Upstream refresh, policy agreement, missing coverage and required
self-review still prevent that conclusion.

## Priority for closing gaps

1. Refresh against current upstream, inspect overlapping changes, and re-run on
   the exact resulting source tree. Preserve a separate upstream failure baseline.
2. Resolve policy assumptions with maintainers before changing enablement,
   zero-value, cross-post/opt-out or fairness behavior. Agreement is not implied
   by a passing test suite.
3. Add exact same-message simultaneous admission, head-of-queue eligibility,
   simultaneous publication claims, failed/incomplete-review release and
   combined adaptive authorization/routing cases.
4. Complete disabled/omitted/fixed-zero inheritance, minimal-profile CLI runtime,
   future/malformed Date and TZ/clock cases; audit malformed allocation and
   diagnostic canary handling.
5. Define a real historical corpus, exercise read-only shadow replay with
   pristine-state checks, and finish operational dry-run/pending-work rollback
   coverage. Generated traces are not historical replay.
6. Run the required Sashiko self-review, fix valid findings, and refresh all
   affected evidence before requesting separate upstream submission approval.

The performance medians pass the unchanged 20%/50% ratio budgets, but one fresh
paired sample exceeds 20%; do not hide that tail or claim production headroom.
The indivisible multiowner quarantine exception prevents a blanket bounded
writer/storage claim. From addresses remain unauthenticated.

No new tests, merge, upstream PR, deployment, paid model call or external email
were performed during this reconciliation. This audit records existing evidence
and newly discovered gaps; it does not turn partial rows into passing tests.
