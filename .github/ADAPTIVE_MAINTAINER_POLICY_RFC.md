Bursts of complete mail revisions can cluster public review notifications.
I am preparing an opt-in per-author publication cooldown and would like
agreement on its policy before submitting a code PR. It delays publication,
not review computation. No email or token savings are claimed.

The source-only candidate is based on upstream
026195ab58e2099e81017adbc6b97f33c509c8ba. Its current checked native head is
a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9.

- [Current source design](https://github.com/OllieinCanada/sashiko/blob/codex/held-series-ci-20261019/.github/adaptive-current-source-design.md)
- [Checked source bundle and native logs](https://github.com/OllieinCanada/sashiko/actions/runs/39370749173/artifacts/12241795319)
- [Validation evidence and retained failures](https://github.com/OllieinCanada/sashiko/blob/codex/held-series-ci-20261019/.github/adaptive-upstream-refresh-evidence.json)

Proposed v1 semantics:

1. **Explicit per-list opt-in.** Omitted and disabled lists retain legacy
   behavior. Numeric templates cannot enable a list. Preserve fixed-embargo
   zero/NULL meanings; enabled adaptive parameters must be positive and valid.
2. **One event per complete canonical revision.** Covers, parts, duplicates
   and replays do not add activity. Scope is project DB, configured list and
   normalized ASCII bare From address. There is no size multiplier or
   authenticated identity claim; malformed authors never share an unknown key.
3. **Cross-post fallback.** Multiple configured To/Cc/NNTP list matches select
   shared legacy publication policy, including an opted-out list.
   Non-NNTP sources remain legacy.
4. **Frozen delay.** For prior admissions p in (t-W,t], extra is
   min(C,s*max(0,p+1-B)); deadline is max(legacy,t+extra). Use local UTC
   admission time, not email Date. Zero extra preserves the exact legacy
   value. Later traffic cannot move an earlier deadline. Keep successful
   clean-review and authorized early-release exceptions.
5. **Exact ownership quarantine.** Reject automatic multiowner reconciliation.
   Stage every exact owner in batches of 64, activate the whole guard in one
   commit, then materialize durable owner blocks in bounded batches.
   Restart recovery preserves committed protection and cleans expired
   preparations. New claims obey activation; previously claimed deliveries
   can still finish.
6. **Explicit operational limits.** Canonical scanning, owner-vector memory,
   same-handle transaction-mutex occupancy and permanent tombstones remain
   unbounded. Batching bounds owner work per writer transaction, not global
   latency or storage. From spoofing or conflicting Message-IDs can quarantine
   a victim until operator repair; the time-delay cap does not cap quarantine.
   Ceilings are W<=31 days, C<=7 days, 1024 parts and 4096 history rows to
   saturation. These are not rollout defaults.

The final Rust code passes formatting, all three Clippy profiles and 1126
tests with two ignored. Fingerprint standard vectors, source-correction
guards, maximum-series and stopped rollback checks pass. The earlier two
candidate revisions failed the unchanged performance budgets; their results
are preserved. All eleven final extended phases, including recovery and performance, pass.
Disabled/upstream median ratios are 1.1713/1.1546 and enabled/disabled ratios
are 1.1482/1.1445 at zero/10000 retained owners. One individual disabled
pair was 1.304; the declared three-repetition median criterion passed. This is not a submission-readiness or production
performance claim. Required model review remains incomplete after a bounded provider timeout;
automatic execution is disabled. The published review head is
d7f7a5516cc805444f23c534199af7e65d51e551, tree-identical to the tested native
head; only commit-message trailer formatting changed.

The candidate uses migrations 014 (held-series index), 015 (accounting) and
016 (conflict groups). Recheck numbering and repeat affected validation if
upstream PR #685 lands first. No deployment configuration has changed.

Would you accept these v1 semantics, especially explicit enablement,
positive-only parameters, cross-post/opt-out fallback, unauthenticated author
scope, no size penalty, and the remaining scan/storage/claimed-delivery
limits? Otherwise I will treat the required policy or architecture change as
outstanding, rather than marking a checklist row complete.

This is a prepared discussion request. The connector's earlier upstream
posting attempt returned 403; no maintainer agreement or upstream code PR
is claimed.
