# Upstream refresh and remaining native validation

Status: rebased source passes native checks; performance blocks readiness.
No upstream PR has been opened. Required model review and maintainer policy
agreement remain open.

## Exact source

- Upstream: 026195ab58e2099e81017adbc6b97f33c509c8ba.
- Rebased four-commit candidate: 0bf683e6eb4ac55ad1338f71f5e8dbda43baa7a4.
- Candidate tree: 1de3c7d27ec93a608838aed9b0d3ff5bd1f63cb5.
- Native source bundle and logs: [run 39359678639](https://github.com/OllieinCanada/sashiko/actions/runs/39359678639/artifacts/12237721302).
- The rebased native commits are in the bundle, not yet on a published branch.
  The audit branch's tracked production snapshot is still 54a5abc1894bd0fcba1ebbfd7acf20044d7e5091.

The source-only series rebased cleanly onto current upstream. Native
make check-pr passed: 1043 library, 50 main, 7 CLI and 23 integration tests;
1123 passed, zero failed, two ignored. Formatting and all three Clippy
profiles passed. Sign-offs and clean final source status were checked.

The deterministic ingestion, routing, clock, cancellation, SQL payload,
malformed-input and private-route fixtures passed. Both ingestion/privacy
mutations were killed.

## Performance failure retained

The original 18-sample file-backed debug trace tested 1000 series and 3750
parts, with zero or 10000 retained owners. Disabled legacy state projections
matched upstream in both cases.

| Retained owners | Disabled / upstream | Enabled / disabled | Result |
| --- | ---: | ---: | --- |
| 0 | 1.2450766802 | 1.2207647121 | FAIL |
| 10000 | 1.3529530939 | 0.9559658378 | FAIL |

The unchanged budgets are 1.20 and 1.50 respectively. The disabled-mode
regression is a candidate problem. The noisy enabled ratio below one is not
evidence of a speedup. These are synthetic debug measurements, not production
latency, fairness, token savings or email savings.

No unchanged-source performance retry was made. The follow-up job refused
to overwrite this failure with a fresh sample. A focused optimization now
combines quarantine checks with existing binding/completion reads, with
new direct regressions and three compiled guard mutations. Its source is
not yet validated or published; see the optimization run in the JSON.

## Refreshed recovery and upstream results

[Remaining validation run 39360690253](https://github.com/OllieinCanada/sashiko/actions/runs/39360690253)
passed all nine other phases on the exact rebased candidate:

- Conflict guards and two compiled guard mutations.
- Process SIGKILL after committed preparation, activation and partial handoff.
- Stopped schema-16 rollback and restore, including live staged membership.
- Wall-clock release under UTC and America/New_York.
- Three restarted read-only replays of the pinned public historical message.
- Actual review cancellation with local child/provider mocks and two mutations.
- Sixteen independent writers, duplicate replays and explicit releases.
- Injected ENOSPC, EIO, torn WAL and pre/post-commit process death.
- Exact upstream comparison: 1073 tests passed, two ignored. Upstream Clippy
  retains four large-response-error failures; the candidate's existing scoped
  compatibility prerequisite handles those. They are separate from the
  candidate performance failure.

The first joined rollback attempt failed before exercising rollback because
shared Cargo output referred to deleted temporary prompt files. Separate
native jobs avoided that contaminated output; the schema-16 rehearsal passed.
Live rollback, physical power loss and remote SMTP acknowledgements remain
outside these tests.

## Still required

Validate the changed optimization, repeat affected checks on its exact source,
meet the original performance budgets, preserve the final signed-off source
and update the PR draft. Model review and maintainer agreement remain open.
Scanning/memory, permanent tombstones, same-handle mutex occupancy, spoofed
identity and previously claimed delivery limits remain documented.

No model calls, real emails, deployment changes or upstream PR were made.
