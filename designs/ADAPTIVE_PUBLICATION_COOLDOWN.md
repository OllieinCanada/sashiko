# Opt-in adaptive publication grace period

This is an experimental per-list publication policy, not a deployment default.
The existing fixed embargo, recipient policy, clean exception and external
transport guarantees remain authoritative. No real list configuration is changed.

An explicit per-list enabled=true selects bounded capped-linear activity delay.
Numeric templates alone cannot enable a list. One complete canonical mail-series
revision is counted within (project, configured list, normalized bare author).
Covers, duplicate parts, mirrors, retries and reruns do not add events. Cross-posts
and non-mail sources retain the legacy policy. Size has no multiplier in v1.

Let p be prior distinct admissions in (t-window,t], B the unpenalized burst, s the
step and C the extra cap. extra=min(C,s*max(0,p+1-B)); effective=max(legacy,t+extra).
An extra of zero preserves the legacy deadline, including NULL. t is successful
local admission time, never Date/Received. Later activity never moves a decision.

Durable intent is inserted with a new canonical row, before Pending can become
visible. Existing legacy rows are not retroactively enrolled. A shared transaction
helper handles part, cover and merge completion. Complete means actual unique
indices 1..N with consistent source metadata, not received_parts >= total_parts.
The existing Database writer serializes event uniqueness, bounded history lookup,
decision, embargo_until and Pending transition. Publication stays unresolved on
errors; no zero-history fallback. No lock spans compression, delivery or sleeps.

Canonical merges must reconcile intent before deleting a donor. Waiting intents
may collapse only with compatible scope. A decided record and release marker may
move only when the accounted message/content set is unchanged. Conflicting decided
identities are quarantined durably, not silently deleted. Message corrections and
part rewrites cannot bypass that guard by occurring before canonical resolution.

The single live deadline remains patchsets.embargo_until. Authorized release gets
an irreversible marker, including before admission. Clean successful review keeps
its existing exception. Waiting and blocked intent cannot enter review claims or
publication; retries and reload cannot silently remove intent. Existing claimed
external deliveries have the existing residual cancellation race.

Policy limits are validation/resource ceilings, not production defaults. History
queries stop at the saturation count and use a scope/time index. Compact payloads
in bounded batches beyond the maximum supported window while retaining event and
canonical dedup tombstones. No archive backfill or historical count synthesis.

Before upstream review: validate the configuration-to-publication route, upgrade,
restart, independent writers, overrides, ambiguous identity, source corrections,
mutation sensitivity and matched disabled/enabled load. Report unsupported states
and measured overhead. No adaptive feature claim follows from helper-only tests.
