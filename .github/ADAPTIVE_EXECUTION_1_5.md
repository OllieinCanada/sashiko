# Adaptive cooldown — execution of items 1–5

> Historical snapshot. Current acceptance counts, provider status, upstream,
> bundle identities and final validation are in
> [the deterministic coverage update](ADAPTIVE_DETERMINISTIC_EVIDENCE.md).
> Earlier performance samples and negative outcomes below remain preserved.


**Not ready for submission.** Implementation and required deterministic checks are prepared. Maintainer policy agreement and authenticated Sashiko self-review remain absent; historical archive replay is blocked. The acceptance matrix records **50 VERIFIED / 12 PARTIAL / 2 BLOCKED**, with the scope of every row retained.

This report uses the user's pasted 64 acceptance scenarios and ten completion gates. It does not claim the original inaccessible attachment was recovered. No upstream PR, deployment, real email or model call was made.

## Exact revisions and environment

- Upstream: `7f92f869a960a20f7d395550b4879d897ebdf4ea`, observed unchanged at 20:39 UTC, 2026-10-19. The adaptive configuration/accounting feature is absent in the inspected upstream files; existing fixed embargoes remain present.
- Final production checkpoint: `bd59059f1864aea81b11b5de0eb97e5d2ec53667`.
- Required-suite checkout: `dbe259abb32b5f585f020ce7faee96694e8869c4`; only two fork workflow files differ from that production checkpoint. Production source is identical.
- Checked source-only bundle HEAD: `fa8a32646362a11ce00b7a90a14df3af828465d3`; tree: `178107288293535d3adeaf180ba0328b9da6714a`. These commits exist in the downloadable bundle, not a published remote branch.
- Hosted Ubuntu 24.04.5; stable Rust 1.99.1 (58cf8f9c3); Git 2.55.0; two Cargo build jobs. Local workspace execution remained unavailable, so validation used isolated fork Actions runners and temporary state.

[Machine-readable analytical evidence](adaptive-execution-1-5.json) preserves commands, exact revisions, environment, raw timing samples, counters, patch hashes and outcomes. Raw logs and bundles in Actions artifacts have 14-day retention; preserve downloads if needed beyond that period. No raw log files or credentials are committed.

## 1. Upstream refresh and required checks

Refreshed the previous base across 16 upstream commits. Overlapping main/server edits preserve the upstream authorization-before-body and recipient-safety protections. Exact patch application was checked against the refreshed files.

Untouched upstream produces four stable-Rust 1.99.1 `result_large_err` lint errors in concrete Axum extractor rejections; the pinned older toolchain does not reproduce them. A separate prerequisite adds four function-scoped lint allowances while preserving response status/body and authentication order. No global warning relaxation was introduced.

[Required native run](https://github.com/OllieinCanada/sashiko/actions/runs/39320690309): formatting, Clippy all-features/minimal/minimal+cache, and all-feature tests pass. **1,032 library + 49 main + 7 CLI + 23 integration = 1,111 passed, two ignored.** No ignored test is described as passed.

## 2. Regression gaps and careful review

A genuine stale-snapshot race was fixed: another writer could admit an identical message between the optimistic read and writer acquisition, causing an otherwise valid replay to be quarantined. A bounded under-lock identity check now retries the stale snapshot; newly appended parts and changed owned content still quarantine.

[Focused validation](https://github.com/OllieinCanada/sashiko/actions/runs/39320285627) covers independent identical submissions plus deterministic stale snapshots, failed/partial/missing/skipped and mixed Reviewed+Failed outputs, eligible work behind a held queue head, and competing independent release/email/Patchwork claims with one winner. The enabled-adaptive endpoint fixture reuses the existing release ACL/visibility matrix.

[Eight-mutant run](https://github.com/OllieinCanada/sashiko/actions/runs/39320285657) compiles and kills author-scope, frozen-replay, deadline, release-marker, NNTP-enablement, stale-identical-replay, source-correction and snapshot-quarantine mutants. Targeted positive controls, an unrelated legacy control under every mutant, and restored replay pass. [Independent artifact inspection](https://github.com/OllieinCanada/sashiko/actions/runs/39321984128) checked the actual negative assertion/error contexts: all fail for the intended semantic change rather than infrastructure problems. It also verifies bundle source equivalence, patch hashes, DCO trailers and each source-commit check summary.

Final-source additional evidence:

| Check | Outcome and scope | Run |
| --- | --- | --- |
| Maximum series / history fault / process restart | PASS; actual 1,024 parts, rolled-back injected history failure, separate-process reopen | [39320285829](https://github.com/OllieinCanada/sashiko/actions/runs/39320285829) |
| Natural expiry / restart / slow transport | PASS; recording sendmail and unrelated writer; no external delivery | [39320285605](https://github.com/OllieinCanada/sashiko/actions/runs/39320285605) |
| SQLite recovery / pruning / configuration | PASS; six bounded fixtures, including busy/query-only errors and stale leases | [39320285705](https://github.com/OllieinCanada/sashiko/actions/runs/39320285705) |
| Concurrent accounting/replay/release | PASS; 16 handles, 128 admissions, 128 replays, 64 releases, eight scopes | [39320285821](https://github.com/OllieinCanada/sashiko/actions/runs/39320285821) |
| Filesystem/crash simulation | PASS; ENOSPC, EIO, torn WAL write and SIGKILL before/after COMMIT; software model | [39320285708](https://github.com/OllieinCanada/sashiko/actions/runs/39320285708) |

## 3. Compatibility, dates, rollback and performance

Twelve real-ingestion cases cover absent/false settings, inherited numeric templates, and fixed delay omitted/zero/two hours, with independently expected legacy deadlines and no adaptive events/intents. Eight untrusted Date variants are parsed under UTC and America/New_York, including invalid, extreme, future and DST-offset values; admission uses bounded local UTC time. Actual minimal and minimal+cache `--no-ai --agent` review commands succeed offline, and unknown options reject with exit 2. These commands do not satisfy model self-review.

[Stopped rollback rehearsal](https://github.com/OllieinCanada/sashiko/actions/runs/39320285661) keeps an untouched backup, demonstrates the unsafe old-code negative control, quiesces/cancels scratch state, opens it with the old native DB code, then restores all recorded state across 15 tables and resumes pending candidate work. This requires stopped processes and no intervening new work; it is not a live rolling production-daemon downgrade.

[Matched upstream performance](https://github.com/OllieinCanada/sashiko/actions/runs/39320285590) passes the unchanged median limits of 1.20 disabled/upstream and 1.50 enabled/disabled. Each retained-owner case has three interleaved samples for each variant, with 1,000 series / 3,750 patches, author skew, two lists, 10% duplicate traffic and 5% 64-KiB bodies. File-backed, instrumentation-free debug timing is synthetic, not a production latency promise.

| Archived owners | Upstream median seconds | Disabled median seconds | Enabled median seconds | Disabled/upstream | Enabled/disabled |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 15.7002 | 18.0555 | 20.1091 | 1.1500 | 1.1137 |
| 10,000 | 15.4515 | 17.7468 | 20.4645 | 1.1486 | 1.1531 |

Legacy patch/patchset tuples match upstream in both cases. About 15% disabled overhead remains. The first final fresh pair is approximately 1.2392, above 20%, although the prespecified ratio-of-medians passes. Earlier revisions failed that same median budget: 1.20785 fresh, then 1.22248 fresh / 1.21691 retained. Both prior sets of 18 samples remain in the analytical JSON alongside all 18 final samples; there was no threshold relaxation.

Two defensive point-query consolidations avoid repeated ownership/binding/collision reads while retaining writer snapshot/source/rollback guards. [Calibrated observability](https://github.com/OllieinCanada/sashiko/actions/runs/39320285682) measures 251,778 baseline query API calls, 253,028 final-disabled calls and 281,430 enabled calls in each tested retained-history case. Additional disabled calls fell from 8,750 to 1,250 (85.7%); these are API calls, not physical SQL statements or rows. Separate prior-reference paired checks also pass; that reference is not the upstream baseline.

Final explicit-writer p99 values are roughly 0.7–1.3 ms; observed maxima vary. Preserve the earlier disabled 844.91-ms outlier ([prior instrumented run](https://github.com/OllieinCanada/sashiko/actions/runs/39318442856)) and the final upstream-baseline 150.31-ms outlier. Their causes were not established. Mixed canonical ownership still requires an indivisible, potentially unbounded quarantine transaction; permanent deduplication tombstones are not globally storage-bounded. No blanket writer-bound, email-savings or token-savings claim is made.

[Historical harness](https://github.com/OllieinCanada/sashiko/actions/runs/39320939517) compiles and passes a read-only source-fixture write-negative control. An actual public raw-mail fetch previously returned HTTPS 403 and a bounded 15-second NNTP timeout; those transports were not retried. **No actual historical archive replay occurred.** The harness needs an accessible actual public message/corpus, and its source snapshot fixture is not a production database.

## 4. Maintainer policy agreement

[Ready-to-post RFC](ADAPTIVE_MAINTAINER_POLICY_RFC.md) specifies explicit per-list opt-in, the linear capped sliding-window formula, preserved fixed embargoes, shared-legacy cross-post/opt-out policy, unauthenticated From-mailbox scope, resource ceilings, permanent tombstones and the indivisible quarantine exception. An attempted upstream issue creation returned **403 Resource not accessible by integration**; no issue or maintainer agreement exists. This remains an external completion gate, not an inferred approval.

## 5. Self-review and clean PR preparation

[Source preparation artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39320285692/artifacts/12218764477) contains three clean source-only commits, patches and a Git bundle:

1. `9acaf1cd0b0011a2b8eab0f7f9fab6891f954e16` — narrowly scoped upstream lint compatibility.
2. `e4d6928cfb5830e9e1905481a1905c47a7af49ae` — superseded held-review prerequisite and index.
3. `fa8a32646362a11ce00b7a90a14df3af828465d3` — adaptive feature, operator/design documentation and regressions.

Each passed `make check-pr` before commit creation and `make sob` afterward in an isolated clean clone. The final source checkout is clean. Fork-only workflows, audit fixtures and evidence files are excluded. The initial packaging failure occurred after checks passed because Git's trailing-slash ignore did not cover a validated build symlink; the throwaway clone now excludes exactly that link and still rejects other unexpected dirt.

[PR draft](ADAPTIVE_PR_DRAFT.md) is prepared, not submitted. Required authenticated Sashiko self-review is **BLOCKED**: hosted readiness found no `LLM_API_KEY`, and the user confirms no provider key. Offline budget/proxy tests pass, but no actual provider path, review finding or clean result is claimed. No paid workflow is enabled and spend is zero.

The user may create a free-tier key in [Google AI Studio](https://aistudio.google.com/apikey) without enabling billing and save it as `LLM_API_KEY` in [fork Actions secrets](https://github.com/OllieinCanada/sashiko/settings/secrets/actions). Do not paste it into chat. Account creation cannot be performed on the user's behalf here. GitHub Models is not a keyless alternative: it retired on July 30, 2026. Provider/free-tier availability must be checked when the key is supplied; rate-limit/provider failures must stop, not trigger unbounded retries or a paid fallback. Prepared limits are at most two attempts, $2.25/10 minutes each, total at most $4.50/20 minutes under the existing authorization.

A final fork-checkpoint validation exposed a transport limitation: the GitHub Contents API assigns the authenticated account author, while earlier audit checkpoint trailers named the configured native Git identity. Their historical DCO range therefore fails; it is not represented as passing. History was not rewritten. The current connector checkpoint retains the native-user sign-off and adds the verified account's matching trailer; [Its final check](https://github.com/OllieinCanada/sashiko/actions/runs/39322533101) passes, explicitly scoped to HEAD~1..HEAD plus the evidence workflow YAML; artifact source-equivalence and mutation inspection also pass. The three source-only native commits have matching configured authors and independently verified DCO checks. This distinction does not complete model review or policy agreement.

## Remaining work and negative results

The [full matrix](ADAPTIVE_ACCEPTANCE_MATRIX.md) keeps 12 PARTIAL scenarios: omitted/false policy agreement, adaptive-zero semantics, cross-post precedence, full clock-jump matrix, writer fairness/atomic ownership exception, complete enabled routing/ignored-author integrations, forged-identity fairness, global resource bounds, malformed-input fuzz/allocation coverage, in-flight cancellation, comprehensive diagnostic secret/private-content audit, and full operational dry-run/rollback rehearsal. Historical replay and required model review remain BLOCKED.

Earlier faulty date fixtures advanced a live SQLite Row before reading its values; the test now captures each row first. The fixed-delay fixture initially omitted required subsystem mapping, which was added without changing production policy. These negative results, the packaging failure, failed performance revisions, archive denial and missing-key outcome are not counted as feature passes.

Before submission: resolve applicable coverage/policy limitations with maintainers, complete the authenticated Sashiko review and fix valid findings, rerun required checks on any resulting source changes, recheck upstream, and obtain separate approval to publish. No upstream PR has been opened.
