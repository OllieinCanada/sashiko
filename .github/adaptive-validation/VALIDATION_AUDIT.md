# Adaptive cooldown validation audit

Updated 2026-10-19. This document supersedes validation status in older prototype
notes. It records observed evidence, not upstream readiness or rollout approval.

## Audited source

Production source commit: 006076c04a4a544ab0f9d53c8a48b898e34e1e0a.
Later checkpoints 543e9d91ac3186435d5d04bd2ac13d7ecb23c35d and
62d0ac8a39a2b6f5fa57d33f404a618e8711c651 add hosted test harnesses only.
Upstream comparison base: 715294a276efee9d39fbb55cf31eef267e96c7b1
with libsql 0.10.0.

The latest production fix reuses the binding state already read within the
immediate writer transaction. Patch validation still checks immutable source
content and quarantines changes to admitted revisions. Legacy quarantines remain
part of the binding lookup.

## Completed hosted evidence

- [Formatting, three Clippy profiles and full tests](https://github.com/OllieinCanada/sashiko/actions/runs/39297399989):
  1014 library, 47 main, 7 CLI and 23 integration tests pass; two ignored.
- [Matched upstream performance](https://github.com/OllieinCanada/sashiko/actions/runs/39297399851/artifacts/12210160323):
  PASS under unchanged budgets.
- [Paired owner-query comparison, maximum size, missing history and process restart](https://github.com/OllieinCanada/sashiko/actions/runs/39297399966/artifacts/12209058792):
  PASS.
- [Five mutation controls](https://github.com/OllieinCanada/sashiko/actions/runs/39297399882/artifacts/12209727566):
  5/5 mutants compile and are killed by the intended test. Unrelated controls
  pass under every mutant; restored-source replay passes.
- [Six recovery, pruning and source-selection controls](https://github.com/OllieinCanada/sashiko/actions/runs/39298054345/artifacts/12208014648):
  all pass, including stale leases after durable quarantine, disable/cancel/reopen,
  and configured source/recipient selection.
- [Source-only preparation](https://github.com/OllieinCanada/sashiko/actions/runs/39297399738/artifacts/12209312791):
  both source commits pass make check-pr before creation and sign-off checks.
  The prepared source head is 5936d9cf29c8e773f28767ae66521b6ad31c240e,
  tree ddc288258c91d19a4515f5ab52444acfe60dbd3b. It exists in the artifact bundle,
  not a published upstream branch. Model review remains blocked.

Artifacts have 14-day retention. Preserve them before expiry for a durable review.

## Performance result and limits

Three alternating-order repetitions per case; serial file-backed debug workload
with 1000 series, 3750 parts, two lists, hot and distinct authors, duplicate parts,
and occasional 64 KiB bodies. Retained state is 10000 synthetic archived owners,
not a full archive replay. Budgets remain disabled/upstream <= 1.20 and
enabled/disabled <= 1.50.

| Archived owners | Upstream disabled median | Candidate disabled median | Candidate enabled median | Disabled overhead | Enabled overhead |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 15.8114 s | 18.8922 s | 21.4548 s | 19.4844% | 13.5647% |
| 10000 | 16.0972 s | 18.9992 s | 21.4471 s | 18.0282% | 12.8843% |

Legacy patchset and patch tuple hashes match for both disabled traces. This trace
does not configure a fixed embargo; it is not comprehensive differential proof
for every legacy deadline setting. The fresh-state margin is narrow (0.516
percentage points below the limit), and hosted timings vary. This is a screening
pass for this workload, not a production latency or throughput guarantee.

The earlier 2bdac14184525d59dd2739dbfa91fed02d6a8680 run failed the same limits:
21.4611% fresh and 24.3585% retained disabled overhead. That failure is retained at
https://github.com/OllieinCanada/sashiko/actions/runs/39295632598.
The fix was not obtained by loosening thresholds or changing workload.

The paired owner-query reference uses the feature implementation with its
original owner query; it is not upstream. Its latest ratios are 0.990287 fresh
and 0.997901 retained for candidate disabled/reference disabled. Keep that result
distinct from the upstream comparison above.

## Feature evidence and remaining gaps

This is a requirement-oriented audit of currently available source and evidence,
not a reconstruction of the original 64-row acceptance matrix.

| Area | Concrete evidence | Outcome / scope |
| --- | --- | --- |
| Configuration and attribution | Core configuration tests; hosted source/recipient matrix | PASS; four enabled, three cross-post, three legacy, five non-NNTP cases, invalid author rejection |
| Admission formula and window boundaries | hand_checked_linear_thresholds_and_composition; test_cooldown_hand_trace_scope_and_window | PASS |
| Exact legacy NULL/zero and fixed-deadline composition | hand_checked_linear_thresholds_and_composition | PASS for calculator; broad differential trace covers no fixed deadline |
| Canonical completeness, duplicates, out-of-order parts | test_cooldown_incomplete_out_of_order_and_duplicate | PASS |
| Version separation and late covers | test_cooldown_real_versions_and_late_cover_remain_separate; test_cooldown_late_cover_recovers_explicit_part_version | PASS |
| Unbound adopted cover | test_cooldown_unbound_adopted_cover_cannot_admit | PASS |
| Source changes and policy races | test_cooldown_policy_source_race_cannot_bind_changed_recipients; test_cooldown_owned_content_cannot_change_without_context | PASS |
| Early release and no rehold | test_cooldown_release_before_admission_and_no_rehold; test_cooldown_crosspost_preserves_early_release | PASS |
| Independent writers | test_cooldown_distinct_connections_serialize_author_history; test_cooldown_two_connections_own_opposite_parts_once | PASS; no broad load or fairness claim |
| History faults and backward clocks | test_cooldown_history_failure_rolls_back_and_retries; test_cooldown_coverage_and_backward_clock_fail_closed | PASS |
| Seeded restart and replay oracle | test_cooldown_seeded_restart_replay_trace | PASS for three seeds and 288 admissions |
| Process termination after committed admission | test_cooldown_hosted_process_restart | PASS; write process exits immediately after commit; fresh process verifies frozen state, replay and release |
| Maximum actual parts and compact metadata | test_cooldown_hosted_maximum_series; test_cooldown_large_source_metadata_is_compact_during_admission | PASS; 1024 actual parts; compact metadata with 1 MiB subject |
| SQLite writer failures | test_cooldown_hosted_read_only_writer_retry; test_cooldown_hosted_busy_writer_retry | PASS; query_only and independent writer contention |
| Pruning and permanent deduplication | test_cooldown_hosted_pruning_keeps_dedup_state | PASS; 16 event payloads removed and replay does not recount |
| Stale delivery leases after quarantine | test_cooldown_hosted_stale_leases_recheck_quarantine | PASS; email, NULL patch notification, Patchwork; simulated stale claims, no external delivery |
| Disable, cancellation and reopen rehearsal | test_cooldown_hosted_disable_cancel_reopen | PASS; schema and decisions preserved; no binary downgrade exercised |
| Live publication claims and deadline boundary | test_cooldown_live_claims_and_null_patch_notification; test_cooldown_deadline_boundary_clean_exception_and_isolation | PASS |
| Real ingestion to recording transport | test_cooldown_config_to_real_release_and_sendmail | PASS; completed review supplied as fixture, explicit early release |
| Five focused mutation controls | Author scope, frozen replay, deadline comparison, release marker, NNTP eligibility | PASS 5/5 on optimized source; unrelated controls and restored source also pass |
| Matched upstream performance | 1000 series / 3750 parts, fresh and 10000 archived owners, three repetitions | PASS frozen 1.20 / 1.50 budgets; fresh disabled 1.194844, retained disabled 1.180282; legacy trace hashes equal |
| Writer hold/wait and SQL counters | No current instrumentation evidence | OPEN |
| Slow external collaborator and filesystem/power-loss faults | No current evidence | OPEN |
| Full shadow replay and binary downgrade rehearsal | No current evidence | OPEN |
| Canonical multiowner quarantine bound | Atomic whole ownership group documented as indivisible | LIMITATION; no absolute bounded-writer guarantee |
| Original 64-row acceptance matrix | Original attachment is inaccessible because the local filesystem is full | BLOCKED; this table is not a reconstruction or a 64/64 claim |

Query-only and busy faults validate SQL failure rollback/retry. Stale Sending
leases are simulated with expired timestamps, then recovered through the real
sweep and claim APIs after reopening the database. No external delivery is
attempted in that fault fixture. These checks do not establish exactly-once SMTP
delivery across remote acceptance and local acknowledgement.

The recording-transport integration uses the real parsed-article ingestion,
release worker and email worker, with completed review output supplied as a
fixture. It validates explicit early release; the database deadline-boundary
test supplies deterministic timestamps. It is not a full natural-time scheduling
matrix across all workers and sources.

Do not mark all validation complete until the original acceptance rows are
available and reconciled, remaining instrumentation and fault/replay gaps are
resolved or explicitly accepted, and the separately required model review is
complete. The current local sandbox cannot launch even a read-only attachment
command: bwrap fails creating /workspace/.git with no space left on device.
GitHub-hosted validation remains usable.

No upstream PR was opened and no deployment or model invocation was performed
as part of this validation task.
