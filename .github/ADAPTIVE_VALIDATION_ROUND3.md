# Adaptive validation round 3

This report supersedes the performance and remaining-fault status in
[the previous follow-up](ADAPTIVE_VALIDATION_FOLLOWUP.md). It records completed
work and explicit gaps; overall feature acceptance is incomplete.

## Audited source and checks

Production source: 77eefacf3d54a24b7a639f06ac3e339422cc39eb
(functional optimization commit 5f277f508dda14145e2ddea4a07cf3a39570f7fc).
Later concurrency and downgrade checkpoints through
ae6472966f4dc791068dd0fa2750cfeec3f60489 change only fork test harnesses.

[Formatting, three Clippy profiles and 1091 passing tests](https://github.com/OllieinCanada/sashiko/actions/runs/39311023519)
passed; two tests remain ignored.
The same source passed:
[mutation controls](https://github.com/OllieinCanada/sashiko/actions/runs/39311023419),
[SQLite recovery/pruning/source-selection](https://github.com/OllieinCanada/sashiko/actions/runs/39311023353),
[maximum series/history fault/process restart](https://github.com/OllieinCanada/sashiko/actions/runs/39311023530),
and [natural expiry/worker restart/slow transport/replay](https://github.com/OllieinCanada/sashiko/actions/runs/39311023501).

[Source-only preparation](https://github.com/OllieinCanada/sashiko/actions/runs/39311023425/artifacts/12216560674)
passed both make check-pr stages and sign-off checks. Its bundled source-only
head is ecf8f138dac130324b88119eec19c87623c0cbe7, tree
5ac95fc07ae13f90a0d8fb59c27959810c1180b8. This is an artifact bundle, not an
upstream branch. Required model review remains pending.

## Performance headroom

The change preserves canonical-key lookup order while checking duplicate keys
once. Patch completion reuses a Legacy binding result within the same immediate
writer transaction; that binding checked both intent and quarantine. Adaptive
completion still runs the admission validator. No guards or threshold were
removed to obtain the result.

[Matched upstream performance](https://github.com/OllieinCanada/sashiko/actions/runs/39311023321/artifacts/12215842045)
uses the existing workload and three alternating-order repetitions, with base
715294a276efee9d39fbb55cf31eef267e96c7b1 and libsql 0.10.0.
The fixed ratio-of-medians budgets remain 1.20 disabled/upstream and 1.50
enabled/disabled. Both states PASS and legacy tuple hashes match.

| Archived owners | Upstream median | Disabled median | Enabled median | Disabled overhead | Enabled overhead |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 16.201590 s | 18.745208 s | 21.121300 s | 15.6998% | 12.6757% |
| 10000 | 16.175259 s | 18.849670 s | 21.657837 s | 16.5340% | 14.8977% |

The prior independent repeat measured 19.6483% fresh and 17.1027% retained
overhead on separate runners. The deterministic SQL reduction corroborates the
optimization, but cross-run wall-clock changes are not controlled causal proof.

Fresh individual paired ratios in this run are 1.244511, 1.141876 and 1.156998.
Retained ratios are 1.163180, 1.160757 and 1.184989. One fresh pair exceeds 1.20.
Do not describe the result as uniformly below the budget or claim production
latency guarantees. The declared aggregate passes with more median headroom;
tail variability remains a material limitation.

[Instrumented diagnostics](https://github.com/OllieinCanada/sashiko/actions/runs/39311023387/artifacts/12216626561)
passed all calibration controls. Each fresh and retained case records:

| Variant | Query API calls | Change from previous source |
| --- | ---: | ---: |
| Upstream disabled | 251778 | 0 |
| Candidate disabled | 260528 | -6000 |
| Candidate enabled mix | 288930 | -3000 |

Disabled incremental query count is now 8750, down from 14750 (40.68% fewer
additional calls). Execute calls and transaction counts are unchanged. These are
attempted libsql API calls, not physical statements, rows visited, or SQL VM
operations; fixture source lookups are included. Diagnostic timers add overhead
and are not substituted into acceptance timing. Enabled transaction-hold p99 is
1.277–1.384 ms in these serial traces, with a 14.840 ms fresh maximum. This does
not establish an absolute writer hold bound.

## OS write faults and process recovery

[Five recovery cases](https://github.com/OllieinCanada/sashiko/actions/runs/39311023488/artifacts/12216685425)
PASS on the optimized source:

- ENOSPC and EIO injected at POSIX writes to the fixture database/WAL.
- A partial WAL write followed by SIGKILL.
- SIGKILL immediately before COMMIT.
- SIGKILL immediately after successful COMMIT.

The first four preserve the prior committed event and omit the failed target
admission. The post-COMMIT case preserves both admissions. Fresh processes verify
SQLite integrity and foreign keys, retry the target, and verify exactly two
events and unchanged frozen state on replay.

LD_PRELOAD supplies the OS-boundary failure and torn-write simulation. It does
not reproduce physical device exhaustion or electrical power failure. The writer
uses synchronous=FULL for the commit-boundary fixture. No production files or
running services are involved.

## Independent concurrent writers

[The 16-writer control](https://github.com/OllieinCanada/sashiko/actions/runs/39311179413/artifacts/12216100956)
PASS: 16 independent Database handles share a file-backed SQLite database,
admitting 128 revisions over eight author/list scopes. All 128 context-free
replays preserve frozen/live release snapshots; 64 release markers persist.
Each scope has exactly 16 events and the expected saturated prior-count
distribution (one each at 0, 1, 2 and thirteen at 3).

This is bounded DB-API concurrency coverage, not a full concurrent ingestion,
network, fairness or production throughput guarantee.

## Old-version access rehearsal

[The native old/new version rehearsal](https://github.com/OllieinCanada/sashiko/actions/runs/39311353746/artifacts/12215806606)
PASS through preparation, unsafe-copy negative control, quiescence, safe old-code
access and new-code verification.

The unsafe copy demonstrates that old publication claim code can claim fixture
outboxes which the new guard withholds. The supported rehearsal stops creating
new work and cancels all waiting/held fixture revisions and unsent outboxes.
Native old-version code then observes no review/release/email/Patchwork claims.
Reopening with current code preserves schema version 15, all three intent
tombstones and both committed events, with integrity checks passing.

These are native test executables containing the actual old/new database code.
The test does not deploy or start a downgraded production daemon and does not
authorize live rollback or schema removal. It exercises an isolated
cancellation path; other operational rollback paths require their own evidence.

## Incomplete work and blockers

1. Original 64-row acceptance reconciliation remains BLOCKED. Uploaded files are
   present by path, but ordinary reads fail during sandbox startup with no space
   left on device. The read-only escalated requests did not execute and were
   aborted. No further local approval/read attempts are planned. A readable copy
   of the Markdown text in chat or in the fork is needed to map the exact rows.
2. A real historical shadow replay has NOT been performed. The existing seeded
   trace and concurrency corpus are generated fixtures; they must not be relabeled
   as historical replay. A defined historical corpus and required coverage must
   be established and checked against the original requirements.
3. Physical power-loss validation, remote SMTP acceptance/acknowledgement crash
   behavior and a full production-daemon downgrade remain unverified.
4. The documented indivisible multiowner quarantine limitation remains. Model
   self-review and upstream submission approval are separate pending steps.

No upstream PR, deployment, real mail delivery or paid model review occurred.
GitHub artifacts retain evidence for 14 days; preserve them before expiry.
