Bursts of complete mail revisions can produce clustered publication of review results. I am preparing an opt-in per-author publication cooldown and would like agreement on its policy before submitting a code PR. This delays publication, not review computation; I am not claiming fewer emails or lower token cost.

The current draft and its limitations are in the fork:
- [Design](https://github.com/OllieinCanada/sashiko/blob/161687343e4955df44ebd803914d1b200d808c04/designs/ADAPTIVE_PUBLICATION_COOLDOWN.md)
- [Acceptance evidence and remaining gaps](https://github.com/OllieinCanada/sashiko/blob/161687343e4955df44ebd803914d1b200d808c04/.github/ADAPTIVE_ACCEPTANCE_MATRIX.md)

Proposed v1 semantics:

1. **Explicit per-list opt-in.** Omitted/disabled lists retain legacy behavior. Global numeric templates cannot enable a list. Existing fixed-embargo zero/NULL meanings are preserved; enabled adaptive parameters must be positive and internally consistent.
2. **One event per complete canonical revision.** Covers, parts, duplicate delivery and replays do not add activity. Attribution is project DB + configured list + normalized ASCII bare From address. There is no size multiplier, authenticated identity claim, or automatic merging of malformed/unknown identities.
3. **Cross-post fallback.** If actual To/Cc plus configured NNTP source identify multiple configured lists, use the existing shared legacy publication policy, including when one of those lists opts out. Non-NNTP sources remain legacy.
4. **Frozen linear delay.** For prior admissions p in (t-W,t], extra=min(C,s*max(0,p+1-B)); publication deadline is max(legacy,t+extra). Admission uses local UTC, not email Date. A zero extra leaves the exact legacy value unchanged. Later traffic never moves an existing deadline. Existing successful-clean-review and authorized early-release exceptions stay in place.
5. **Fail-closed ownership and bounded hot accounting.** Conflicting sources or ambiguous canonical ownership are quarantined. The draft rejects automatic multiowner reconciliation and atomically quarantines the affected ownership group. That indivisible group is currently an explicit exception to a general bounded-writer guarantee; permanent dedup/release tombstones also need retention planning. Supported resource ceilings are W<=31 days, C<=7 days, <=1024 parts and <=4096 history rows to saturation, not deployment defaults.

Would you accept these semantics for a v1 PR, especially the cross-post/opt-out behavior, positive-only adaptive parameters, unauthenticated author scope, no size penalty, and the indivisible ownership-group limitation? If the ownership exception is unacceptable, I will treat redesign as required rather than claiming that the current draft is resource-bounded.

Deterministic validation and additional compatibility/publication tests are still in progress, as is the required Sashiko self-review. No rollout or upstream code PR is being requested here.