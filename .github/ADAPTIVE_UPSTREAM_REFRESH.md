> **Latest model investigation:** The resumed review timed out at 120.093
> seconds on its first generation. Metadata and token counting succeeded;
> no review completed. All provider workflows remain disabled.
> [Exact outcome and offline harness correction](ADAPTIVE_MODEL_REVIEW_STATUS.md).

# Upstream refresh and final validation

Rebase and deterministic validation passed. Required completed model review
and maintainer policy agreement remain open. No upstream PR is open.

## Exact source

- Upstream: 026195ab58e2099e81017adbc6b97f33c509c8ba.
- Tested native head: a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9.
- Review branch: codex/adaptive-cooldown-review-20261020.
- Review head: d7f7a5516cc805444f23c534199af7e65d51e551.
- Identical source tree: 9a92a08ab85001d30c037811f4546381e22dbeab.
- Eight signed-off commits, 15 changed paths, zero commits behind upstream.
  No fork-only .github files are included in the source contribution.
- [Review branch](https://github.com/OllieinCanada/sashiko/tree/codex/adaptive-cooldown-review-20261020)
- [Commit/tree equivalence proof](https://github.com/OllieinCanada/sashiko/actions/runs/39373625867/artifacts/12242218962)

The first commit's Fixes/sign-off trailers were joined into one block on a
separate review branch. Every intermediate tree, native author and date is
preserved. The original tested branch is retained; no force push occurred.

## Required checks and final fixtures

[Native run 39370749173](https://github.com/OllieinCanada/sashiko/actions/runs/39370749173)
passed formatting, all-feature/minimal/cache Clippy and the full suite:
1046 library + 50 main + 7 CLI + 23 integration = **1126 passed**,
zero failed, two ignored. Environment: Ubuntu 24.04, rustc
1.99.1 (58cf8f9c3 2026-10-13), Cargo 1.99.1, build jobs 2.
Required checks ran before each independent native commit.

[Final extended run 39370876283](https://github.com/OllieinCanada/sashiko/actions/runs/39370876283)
passed all eleven phases. Evidence records the precise fixture scope:

| Phase | Validated scope |
| --- | --- |
| Deterministic | Complete production ingestion/publication path, duplicate replay, routing, clock cases, admission rollback, malformed/SQL payloads, private held handlers, recording-transport cancellation/reopen; two mutants killed |
| Conflict | Five production fixtures; exact sparse 131-owner membership, preparing invisibility, active guard, all three new-claim paths, direct binding/admission/early release, restart/handoff, overlaps, failed stage and independent writer; two mutants killed |
| Crash | Actual SIGKILL after committed preparing, active and partial handoff states; explicit expiry of live preparation before bounded cleanup |
| Concurrency | 16 handles, 128 admissions across eight scopes, 128 context-free replays and 64 releases |
| Faults | ENOSPC, EIO, torn WAL and pre/post-commit SIGKILL; software fault model |
| Clock | Actual process clock interposition in UTC and America/New_York; exact deadline, backward/forward jumps and no duplicate release |
| Cancellation | Actual stdio RPC cancellation, provider-future/permit cleanup and child reaping; local mock provider; two mutants killed |
| Historical | Pinned real 2005 Gmane email, three restarted read-only shadow replays; source DB/repository hashes unchanged |
| Rollback | Stopped schema-16 candidate/old/candidate daemons, health/startup/SIGINT, complete backup/restore and pending membership preservation; active-group old-code negative control |
| Performance | Eighteen file-backed instrumentation-free debug samples, unchanged median budgets passed |
| Upstream | Reused exact-base evidence from run 39360690253, same Rust: 1073 passed/two ignored; four upstream Clippy failures isolated |

[Maximum-series run 39370876169](https://github.com/OllieinCanada/sashiko/actions/runs/39370876169)
passed 1024 actual parts, history-read rollback, process exit immediately after
committed admission, reopened replay and authorized release.

Final native fingerprint/source-owner mutants were both killed. Three earlier
binding/completion mutants were killed on 7bbbd266c8c9f427a96be9589a003c44922fb3a7;
their three function bodies are byte-identical on the tested source. This is
reused unchanged-function proof, not three freshly compiled final-head mutants.

## Performance and preserved failures

Budgets remain disabled/upstream <=1.20 and enabled/disabled <=1.50, comparing
three-repetition medians for 1000 series / 3750 parts:

| Retained owners | Upstream seconds | Disabled seconds | Enabled seconds | Disabled/upstream | Enabled/disabled |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 16.3557 | 19.1581 | 21.9982 | 1.17134 | 1.14825 |
| 10000 | 16.7351 | 19.3229 | 22.1155 | 1.15463 | 1.14453 |

Disabled legacy patchset/patch projections matched the baseline. The first
fresh-state disabled pair was about 1.304, exceeding 1.20; it remains in the
18 raw samples. Passing the predeclared median criterion is no per-sample or
production latency guarantee. No savings are claimed.

The first rebased candidate failed disabled medians 1.2451/1.3530; the
query-consolidated candidate failed 1.2824/1.2803. Both negative runs remain.
Profiling identified per-byte formatted SHA hex and unconditional source-owner
lookups; two independent fixes preserve exact encoding and conflict checks
before any message/thread reassignment. Tests and mutants cover both.

A first rollback harness failure reused build output referring to a deleted
temporary prompt directory; it exercised no rollback behavior. Diagnostic
instrumentation and mock-counter fixture failures are also retained. The
separate final rollback, diagnostics and free model controls passed.

## Remaining gates and operational limits

The required Sashiko model attempt on the final source dispatched one Gemini
3.8 Flash generation and timed out. It did not complete a review. Its reserved
maximum was $0.0336345, not actual billing. Automatic execution is disabled;
no automatic retry is scheduled.
[Attempt and bounded report](https://github.com/OllieinCanada/sashiko/actions/runs/39372578093/artifacts/12241943006).

Maintainer agreement on the [policy RFC](ADAPTIVE_MAINTAINER_POLICY_RFC.md)
is still absent. The prepared [PR draft](ADAPTIVE_PR_DRAFT.md) requires these
gates and separate publication approval.

Writer owner work is bounded in batches of 64; canonical scan, owner-vector
memory, same-handle mutex occupancy and permanent storage remain unbounded.
From is unauthenticated; identity conflicts can quarantine a victim until
repair. Previously claimed deliveries may finish after activation. Rollback
requires stopped workers and an untouched full backup; no new old-version
work may be overwritten by restoration. See [remaining gates](ADAPTIVE_REMAINING_GATES.md).

Upstream is still 026195ab58e2099e81017adbc6b97f33c509c8ba; adaptive configuration/tables are absent there.
PR #685 remains open and uses migration 014. Rebase/renumber/revalidate if it
lands first. Current candidate migrations are 014/015/016.

## Reproduction and evidence

Clone the review branch, verify HEAD and tree above, then run
make check-pr RANGE=026195ab58e2099e81017adbc6b97f33c509c8ba..HEAD
outside git hooks/rebase commands with no other sashiko process running.
The same source tree was checked at a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9; the review head differs
only through commit-message ancestry.

[Machine-readable evidence](adaptive-upstream-refresh-evidence.json) pins
every source/checkpoint hash, command manifest, runner, artifact and outcome.
Native artifact 12241795319 includes the source bundle and patches; the
published source branch survives artifact expiry. Pinned .github/adaptive-refresh
and .github/adaptive-extended runners reproduce deterministic fixtures.
No production DB was available for the optional live check-db-invariants
command; migration, rollback and fault checks used isolated fixture DBs.
Historical 55/8/1 counts are retained as historical evidence, not all-64
recertification.
