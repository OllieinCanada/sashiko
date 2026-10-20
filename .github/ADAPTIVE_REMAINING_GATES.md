> **Latest model investigation:** The resumed review timed out at 120.093
> seconds on its first generation. Metadata and token counting succeeded;
> no review completed. All provider workflows remain disabled.
> [Exact outcome and offline harness correction](ADAPTIVE_MODEL_REVIEW_STATUS.md).

# Remaining acceptance decisions

Current source is d7f7a5516cc805444f23c534199af7e65d51e551, tree-identical to
tested a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9. Rebase, native checks,
eleven extended phases, maximum series and unchanged performance median
budgets pass. See [exact evidence](ADAPTIVE_UPSTREAM_REFRESH.md).

The historical matrix has eight partial rows and one blocked row. Those
counts have not been promoted to a fresh all-64 certification. Documentation
does not waive a requirement or invent maintainer agreement.

| Row | Remaining policy, scope or resource limit |
| --- | --- |
| A02 | Per-list explicit enablement is not inherited; global numeric templates do not enable a list. Policy agreement required. |
| A03 | Adaptive window/step/cap must be positive; legacy zero/NULL meanings remain. Policy agreement required. |
| A06 | Multiple configured list matches, including an opt-out, select shared legacy policy. Policy agreement required. |
| D06 | Exact membership writer work is now bounded to 64 owners per batch. Deferred canonical scan, owner-vector allocation and same-handle transaction mutex occupancy remain unbounded; no global fairness/latency guarantee. |
| F02 | From is unauthenticated. Spoofing/conflicting identifiers can penalize another identity or quarantine it until operator repair. Delay cap does not cap quarantine. |
| F04 | Permanent tombstones, total membership storage, canonical scan and owner-vector memory remain unbounded. 1024-part and bounded history reads do not bound lifetime storage. |
| F05 | Malformed identity, SQL payload and bounded input fixtures pass; universal MIME fuzzing/allocation safety is not established. |
| F07 | Tested held-handler/tracing privacy and budget-proxy canaries pass. This is not a whole-provider logging audit; existing provider error-body handling can include private content after credential-pattern redaction. |
| H06 | Required Sashiko review remains incomplete: one bounded final-source generation timed out. Empty findings from an errored agent are not a clean review. Automatic calls disabled. |

Fresh F06 cancellation proof uses actual stdio RPC cancellation, local mock
provider-future/permit cleanup and child reaping, with two killed mutants.
Fresh H07 proves stopped schema-16 candidate/old/candidate startup and pending
membership preservation from an untouched complete backup. It does not prove
live rolling downgrade or remote SMTP acknowledgment recovery. A delivery
claimed before conflict activation may finish afterwards.

Before upstream publication: obtain maintainer policy agreement, complete the
required local Sashiko review and resolve valid findings, confirm upstream and
migration numbering, and obtain separate approval for the prepared PR.
Any policy/source change requires its applicable tests to be repeated.
No upstream PR, deployment, real email or savings claim is made.
