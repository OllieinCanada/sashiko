# Adaptive cooldown deterministic coverage update

**Not ready for submission.** This report records additional deterministic
coverage on unchanged production source. It does not complete maintainer policy
agreement, historical archive replay, or the required Sashiko model review.

The requirements are the user's pasted 64-row checklist and completion gates.
The inaccessible original attachment was not reread.

## Revisions and reproducibility

- Production source: bd59059f1864aea81b11b5de0eb97e5d2ec53667.
- Original runtime/performance baseline:
  7f92f869a960a20f7d395550b4879d897ebdf4ea.
- Newer upstream f6e2e172e1e669b6767a4c74fe91d062b41fd71c changes
  PRESS.md only. It was merged; the refreshed source-only bundle is based on it.
- Refreshed bundled source-only HEAD:
  6667a81cd25a69feca76e65d94aacb4c83b2ce72; tree:
  d38b668f511e2e0972aa4588174a2c55f3582b30.
  These are bundled commits, not a published remote source branch.
- Hosted Ubuntu 24.04; stable Rust; Cargo build jobs 2; locked dependencies.
  Fetch uses bounded network retries/timeouts; native fixture builds run offline.
  Temporary owned databases and local recording transports; no model generation.
- Each runner rejects production-source differences against the frozen source,
  injects its test-only additions, executes exact one-test selectors, and restores
  the source in finally. Artifact manifests retain hashes, commands and outcomes.

## Confirmed separate checks

The [clock run](https://github.com/OllieinCanada/sashiko/actions/runs/39328125251)
passed six actual process wall-clock states under UTC and America/New_York.
Its LD_PRELOAD shim changes owned processes only; monotonic time stays real.
A probe after the production eligibility query records its actual now/selection.
Deadline-1 and backward time do not release; deadline releases once; post-release
forward/backward replay does not rehold or duplicate the recording.

The [active-review cancellation artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39332466758/artifacts/12225540647)
passed its positive case, two compiled semantic mutants, unrelated controls and
restored positive case, plus all-feature/all-target Clippy. Its overall workflow
failed an independent invalid clock fixture; that run is not labelled green.
The actual stdio RPC loop uses a pending in-process mock provider, exercises the
cancellation watcher, requires the child PID to disappear, drops the provider
future and restores the semaphore permit. No real API request is made.

The [refreshed source-only preparation](https://github.com/OllieinCanada/sashiko/actions/runs/39330032302/artifacts/12224277238)
passed make check-pr before each of its three native signed-off commits, then
sign-off checks afterward. Independent artifact inspection of this refreshed
bundle has not been repeated; earlier inspection covered the prior bundle.

## Final focused batch and restored-source gate

**PASS.** [Run 39333925430](https://github.com/OllieinCanada/sashiko/actions/runs/39333925430)
tested checkpoint d9cc305c8e000add224b93800d21e3edcefc8f11.
[Artifact 12226376491](https://github.com/OllieinCanada/sashiko/actions/runs/39333925430/artifacts/12226376491)
contains manifests,source/fixture/binary hashes,test-only patches,and logs.

All eight fixtures passed:

- ingestion-crosspost-ignore: tests::test_det6_ingestion_crosspost_and_ignore_matrix
- enabled-routing: reviewer::tests::test_det6_enabled_routing_and_integration_matrix
- clock-jumps: db::cooldown::tests::test_det6_forward_clock_release_is_irreversible
- cancel-admission: db::cooldown::tests::test_det6_cancel_uncommitted_admission_releases_writer
- bound-sql: db::cooldown::tests::test_det6_bound_sql_payloads_preserve_schema_and_dedup
- malformed-canaries: cooldown::tests::test_det6_malformed_identity_and_id_errors_do_not_echo_inputs
- private-routes-traces: server::tests::test_det6_held_and_quarantined_canaries_stay_private
- abort-transport-recover: tests::test_det6_abort_adaptive_transport_then_recover

Two compiled guard-removal mutants (ignored-author ingestion and private-review
embargo visibility) failed their intended assertions. Unrelated controls and
restored privacy passed. The separate active-review run adds two compiled
cancellation mutants. Together with the previous eight,twelve semantic mutants
are detected;compilation/infrastructure failures never count as detections.

Injected-fixture all-feature/all-target Clippy passed;source restoration passed.
Then make check-pr RANGE=HEAD~1..HEAD passed sign-off,YAML lint,formatting,
all-feature/minimal/cache Clippy and the restored production suite:
1032 library +49 main +7 CLI +23 integration =**1111 passed,2 ignored**.
Rust 1.99.1 (58cf8f9c3),hosted Ubuntu 24.04,two Cargo build jobs.

Commands:
```text
python3 .github/adaptive-deterministic/run.py
python3 .github/adaptive-review-cancel/run.py
python3 .github/adaptive-clock/run.py
make check-pr RANGE=HEAD~1..HEAD
```

The current matrix is 52 VERIFIED / 10 PARTIAL / 2 BLOCKED. Clock-change evidence
closes the named C06 gap;the enabled-routing matrix closes E08 within its scope.
F06 remains partial because the transport termination test does not establish
immediate reaping or every detached-task/SMTP-acknowledgement path.
The full workflow now shares one checkout/cache;unchanged cancellation checks
reuse their passing evidence. Focused failure suppresses the broad baseline
rebuild;independent fixtures collect failures together.

## Preserved negative outcomes

- [Run 39326569637](https://github.com/OllieinCanada/sashiko/actions/runs/39326569637): **FAIL**. Prior key-check YAML trailing whitespace; preflight stopped before native tests.
- [Run 39326820665](https://github.com/OllieinCanada/sashiko/actions/runs/39326820665): **CANCELLED**. Workflow attempted native checks before toolchain/cache setup; order corrected.
- [Run 39327071620](https://github.com/OllieinCanada/sashiko/actions/runs/39327071620): **FAIL**. Fixture injection used file's last brace instead of test-module closing brace. Baseline1111pass/2ignored; scanner corrected.
- [Run 39327807811](https://github.com/OllieinCanada/sashiko/actions/runs/39327807811): **FAIL**. Runtime proxy accidentally applied to Cargo dependency download. Build/runtime environments separated; fetch retry/time limits and offline compilation added.
- [Run 39329322029](https://github.com/OllieinCanada/sashiko/actions/runs/39329322029): **FAIL**. Fixture attempted Database.clone, which is unsupported. Use existing with_cooldown_context handle constructor.
- [Run 39329895024](https://github.com/OllieinCanada/sashiko/actions/runs/39329895024): **FAIL**. Stored message bytes and patch bytes differed in synthetic helper; production source-content guard rejected correctly. Baseline1111pass/2ignored;19-case ingestion/replay matrix passed before fixture error.
- [Run 39331512754](https://github.com/OllieinCanada/sashiko/actions/runs/39331512754): **CANCELLED**. User interruption: baseline native compilation/link active;3Clippy profiles passed;focused stage skipped.
- [Run 39331512892](https://github.com/OllieinCanada/sashiko/actions/runs/39331512892): **CANCELLED**. User interruption: duplicate baseline compilation/link active;3Clippy profiles passed;active-review focused stage skipped.
- [Run 39332466758](https://github.com/OllieinCanada/sashiko/actions/runs/39332466758): **FAIL**. Clock fixture incorrectly assumed active-window event deletion. Production retains global-maximum window; fix asserts3retained,0prior for late admission,0rejected events.
- [Run 39333144037](https://github.com/OllieinCanada/sashiko/actions/runs/39333144037): **CANCELLED_AFTER_FOCUSED_FAILURE**. Clock fixture conflated authorization with completed publication: actual expired embargo1011 vs expectedNULL. Explicit completed-release call added; normal cancel accepted but runner continued, scoped force-cancel completed. Artifacts preserved.
- [Run 39333601760](https://github.com/OllieinCanada/sashiko/actions/runs/39333601760): **FAIL**. Admission-cancellation fixture held independent SQLite read cursor across retry, so same connection retained old WAL snapshot; explicitly close cursor, verify uncommitted event and rollback state, then require both handles see committed event. Seven other independent fixtures passed; broad suite correctly skipped.

No production-code change was required by these harness corrections. The final
cursor fix passed with stronger assertions:one admission inside the uncommitted
transaction,rollback to waiting/incomplete with no event or clock advance,
writer release,and exactly one committed retry event visible to both connections.

## Limits and remaining gates

The author key remains unauthenticated From; shared/forged-address fairness and
cross-post/zero/inheritance policy still need maintainer agreement. Permanent
deduplication tombstones and indivisible ownership quarantine remain resource
exceptions. Malformed-input and privacy corpora are bounded, not universal fuzz
or allocation/provider-log audits. The transport fixture accepts a dead/zombie
PID as termination; its historical child_reaped marker does not prove immediate
reaping. The separate active-review fixture does require PID disappearance.
Remote SMTP acceptance/acknowledgement and full production-daemon rollback are
outside these tests.

LLM_API_KEY is present and authenticated model listing succeeded. Two tiny
generation probes returned HTTP503 without usage metadata. Actual Sashiko
self-review has not run; provider calls remain paused. No charge or savings
claim is made. No provider call occurred in this deterministic coverage round.

Historical raw-email replay remains blocked by archive access, and the RFC
remains unposted after403; no maintainer agreement is claimed. No upstream PR,
deployment or real email has been sent.

Raw Actions artifacts expire after 14 days. The machine-readable report preserves
analytical summaries and exact identities; raw logs are not committed.
