# Adaptive validation follow-up

This report supersedes the open observability and scheduling rows in the earlier
[validation audit](adaptive-validation/VALIDATION_AUDIT.md). It does not close the
unreconciled original acceptance matrix or authorize an upstream PR.

Production source remains 006076c04a4a544ab0f9d53c8a48b898e34e1e0a.
A Git compare against checkpoint 472305bc7ebcec2c0bdf27ebf74d62796cb0217b
confirmed every intervening change is under .github/. Instrumentation and
additional fixtures are injected into ephemeral hosted checkouts and restored
after each run; they are not production code.

## Independent unchanged performance repeat

[Repeat evidence](https://github.com/OllieinCanada/sashiko/actions/runs/39304071684/artifacts/12214220403)
and [previous evidence](https://github.com/OllieinCanada/sashiko/actions/runs/39297399851/artifacts/12210160323)
use the same upstream base 715294a276efee9d39fbb55cf31eef267e96c7b1,
libsql 0.10.0, workload, three alternating-order repetitions and frozen limits:
disabled/upstream <= 1.20, enabled/disabled <= 1.50. No instrumentation is
enabled in these acceptance runs.

| State | Repeat upstream median | Repeat disabled median | Repeat enabled median | Disabled/upstream | Enabled/disabled |
| --- | ---: | ---: | ---: | ---: | ---: |
| Fresh | 16.500595 s | 19.742682 s | 21.993904 s | 1.196483 | 1.114028 |
| 10000 archived owners | 16.596132 s | 19.434520 s | 22.067200 s | 1.171027 | 1.135464 |

Both cases PASS the declared ratio-of-medians metric; legacy patch and patchset
tuple hashes match. Across the two independent runs there are six repetitions
per case. This is not comfortable performance headroom: the repeat's individual
fresh paired ratios are 1.231453, 1.196483 and 1.211189. Two individual pairs
exceed 1.20 even though the predeclared aggregate passes. Preserve that spread
rather than calling the result stable or changing aggregation after seeing data.
The previous fresh aggregate was 1.194844.

The workload remains serial, file-backed debug ingestion of 1000 series / 3750
parts, with two lists, author skew, duplicate parts and occasional 64 KiB bodies.
Archived owners are synthetic retained tombstones, not an archive replay.
Legacy differential equality is limited to this no-fixed-deadline trace.

## Calibrated SQL and writer measurements

[Diagnostic evidence](https://github.com/OllieinCanada/sashiko/actions/runs/39304882731/artifacts/12214176797)
contains three passing controls and six diagnostic workload samples.

The SQL counter control executes exactly one query, one update and one rollback;
it records one query and two execute API calls. A deliberate 100 ms held
transaction produces a 100.20 ms mutex wait and 100.22 ms hold measurement.
A paused pre-write collaborator allows an independent same-author admission to
finish before the pause is released; resumed admission observes the first event.

| Archived owners | Variant | Query API calls | Execute API calls | Explicit transactions | Hold p50 | Hold p99 | Hold maximum |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | baseline disabled | 251778 | 19250 | 7750 | 0.3214 ms | 1.0275 ms | 4.2175 ms |
| 0 | candidate disabled | 266528 | 19250 | 7750 | 0.3988 ms | 1.1456 ms | 14.3762 ms |
| 0 | candidate enabled | 291930 | 27252 | 8550 | 0.4647 ms | 1.3999 ms | 12.0900 ms |
| 10000 | baseline disabled | 251778 | 19250 | 7750 | 0.3252 ms | 1.2486 ms | 218.3016 ms |
| 10000 | candidate disabled | 266528 | 19250 | 7750 | 0.4048 ms | 1.1339 ms | 14.3223 ms |
| 10000 | candidate enabled | 291930 | 27252 | 8550 | 0.4577 ms | 1.5345 ms | 104.2025 ms |

Disabled ingestion adds 14750 query API calls with no additional explicit
transaction or execute calls. Counts are identical between fresh and retained
cases for each variant. That shows no additional API-call count caused by these
10000 archived owners; it does not prove equal rows visited or a global bound.

Explicit transaction mutex-wait p99 is 2.51–3.42 microseconds, and SQLite BEGIN
acquisition p99 is 13.10–18.21 microseconds in these serial diagnostic traces.
These are not contested production-load measurements. Full percentile
distributions and serialized write-call lane measurements are in the artifact.

The hold timer spans successful BEGIN IMMEDIATE to successful COMMIT/ROLLBACK
or drop-time rollback. The serialized-call timer includes statement execution
and row draining; it is not an exact SQLite lock timestamp. The counter wraps
query/execute/execute_batch calls on conn, tx_conn, tx and stmt in db.rs and
db/cooldown.rs. It records attempted API calls; one batch is one call, and
implicit driver SQL and SQLite VM operations are excluded. Workload fixture
source lookups are included. Do not describe these values as physical statement
or row counts. Instrumentation overhead is present, so diagnostic timings are
not substituted into the uninstrumented acceptance comparison.

## Natural expiry, restarted workers, slow transport and replay

[Expanded end-to-end evidence](https://github.com/OllieinCanada/sashiko/actions/runs/39305715541/artifacts/12212554816)
PASS on checkpoint 472305bc7ebcec2c0bdf27ebf74d62796cb0217b. The fixture:
 
1. Ingests real parsed NNTP mail under an explicitly enabled list policy.
2. Supplies a completed review containing a finding, preventing the clean-review
   early-release exception from masking the deadline.
3. Verifies held results are hidden and unclaimable, starts a release worker
   before expiry, then stops it and reopens the file-backed database.
4. Waits for the actual 30-second admission deadline, with no manual release or
   deadline rewrite, and starts a fresh release worker.
5. Restarts the release worker again and asserts exactly one queued email.
6. Gates a real local recording sendmail child, completes an unrelated serialized
   database write while delivery is paused, then permits recorded delivery.
7. Replays the original held message through parsed-article ingestion three
   times; frozen decision fields and the live release remain byte-for-byte equal.
8. Restarts release and email workers; asserts one outbox row, one transport
   invocation and two total original admission events.

The original no-replay variant also
[passed](https://github.com/OllieinCanada/sashiko/actions/runs/39305349058/artifacts/12213023224).
Completed review output is supplied as a fixture; no model or external mail
service is called. Worker instances and database handles reopen within one
process. Separate process termination immediately after admission was validated
by the earlier native restart job. This fixture does not prove exactly-once
delivery across an SMTP server's remote acceptance and local acknowledgement.

## Remaining limits

The requested repeat, observability and expanded scheduling/fault work does not
complete the overall feature acceptance process. The original 64-row checklist
is still inaccessible because this chat's local workspace is full. It must be
reconciled separately.

Filesystem I/O/power-loss faults, remote SMTP acceptance/acknowledgement crash
windows, broad concurrent-load/fairness measurements, full historical shadow
replay and a binary downgrade rehearsal remain unverified. The indivisible
multiowner quarantine limitation remains documented; no absolute writer hold
bound is claimed. Required Sashiko model review is still separate and pending.
No deployment or upstream PR submission was performed.

GitHub artifacts have 14-day retention; preserve them before expiry.
