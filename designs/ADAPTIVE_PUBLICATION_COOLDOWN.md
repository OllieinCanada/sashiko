# Opt-in adaptive publication grace period

This is a local prototype, not ready for upstream submission. Fresh review has
identified an unresolved unbounded canonical-merge quarantine operation. Batching
that operation would weaken crash recovery unless ownership and durable operation
tracking are redesigned first. No bounded-writer claim is made for that path.

This experimental policy delays publication, not review computation. It changes
no deployed list configuration. The existing fixed embargo, clean-review
exception, recipients, access control, cancellation and delivery retry rules
continue to apply. Maintainers must approve any rollout and policy values.

## Scope and policy

A list must explicitly set adaptive_cooldown.enabled = true. Numeric defaults
are templates and cannot enable a list. Attribution uses configured mailing-list
addresses in actual To/Cc and the configured NNTP source, never file-path labels.
Exactly one configured list must match. Cross-posts and non-NNTP sources use the
existing shared legacy deadline; independent recipient deadlines are unsupported.

One complete canonical revision counts once in the project database, configured
list and normalized bare-author scope. Covers, parts, mirrors, retries and reruns
do not add events. All actual unique indices 1..N, source identities and content
fingerprints must agree before admission. Series size has no multiplier in v1;
this avoids a separate unapproved size penalty. Ordinary ASCII mailbox addresses
are supported; malformed identities fail explicitly, never share an unknown key.
From is unauthenticated. Shared or forged addresses can affect another person's
scope; this feature is not an identity or abuse-prevention system.

For prior admissions p in (t-window,t], burst B, step s and incremental cap C:

    extra = min(C, s * max(0, p + 1 - B))
    deadline = max(legacy_deadline, t + extra)

Zero extra preserves the exact legacy value, including NULL or explicit zero.
The cap bounds the adaptive increment, not an independently longer fixed delay.
t is trusted local UTC admission time, not the mail Date header. Simultaneous
admissions serialize. Later activity never moves an earlier decision. Backward
admission clocks and arithmetic overflow fail closed; arbitrary clock corruption
is outside the guarantee.

## Persistence and canonical ownership

New opt-in canonical rows acquire durable waiting intent before Pending can be
visible. Existing legacy rows are never retroactively enrolled. One existing
Database writer transaction validates compact immutable source snapshots, counts
bounded indexed history, inserts the unique event, persists the decision and live
patchsets.embargo_until, then permits Pending. Compression, hashing, subject parsing, network operations and subprocesses remain
outside the writer lane. Compact source facts are persisted with their fingerprint.
An adopted actual cover must have its own verified policy binding before admission;
a raw cover stored by another unfinished ingestion is insufficient.

The first successful admission records each list's history boundary in meta.
Each decision records available history_since. Cold start counts only locally
admitted revisions; no archive history is fabricated. Retention covers the maximum
supported window so a later longer window can use available local history. Policy
reload does not recalculate decided work. Missing or changed policy for a waiting
intent is an error and blocks progress until restored or explicitly cancelled.

Unseen cover IDs are reservations, not activity. A late own cover is validated
against the frozen size and existing canonical version/author matcher. Exact
post-admission mirror replay preserves frozen attribution; changing actual source
bytes, To/Cc, author, index, denominator or content quarantines the revision.
Before admission, cross-post observation excludes the whole revision and restores
legacy behavior, preserving any early release marker.

Multiowner canonical merges involving adaptive, quarantined or explicitly released
excluded state are unsupported in v1. Every matching owner is durably quarantined
before any patches move or owner is deleted. Compatible-looking waiting owners
are also quarantined. There is no automatic reconciliation command; inspect the
inputs and cancel the affected work. Independent explicit revisions and authors
must not be captured merely because they reply to the same old cover.

## Publication, bounds and rollback

Waiting and quarantined work cannot enter review claims, publication release,
outbox claims or public review endpoints. Authorized users may view held results;
identity quarantine cannot be released through the time-embargo override. A normal
authorized early release is irreversible, including before admission. Completeness
still applies. A completely successful clean review retains its existing release
exception; missing, failed or partial output is not a clean review.

There is one live deadline. The frozen decision is diagnostic evidence, not a
second scheduler. Queue uniqueness does not promise exactly-once SMTP delivery:
remote acceptance followed by a crash before local acknowledgement can retry.
Supersession or quarantine cannot recall a delivery already accepted remotely;
existing claims retain their residual cancellation window.

Resource ceilings are 31 days of history, seven days of adaptive increment,
1,024 actual parts and 4,096 history rows to saturation. They are not deployment
defaults. The covering scope/time index reads at most B-1+ceil(C/s) rows. Each
admission removes at most 16 expired event payloads using the retention index;
that maintenance batch bounds writer work, not accepted policy. Compact intent,
release and message ownership tombstones remain, so storage is not globally
bounded and requires operator retention planning.

Disable stops new enrollment; existing decisions and unresolved guards remain.
Do not drop tables or roll back the binary while adaptive work is waiting or held.
Stop ingestion, inspect and explicitly finish, release eligible time holds or
cancel affected work, then verify all outboxes before rollback. Preserve schema
and tombstones in backups. Production migration or rollout is not authorized by
a passing test suite.

Validation must cover the complete mail-to-recording-transport route, fresh and
upgraded databases, reopened workers, independent writers, source races, version
separation, mutations and matched baseline/disabled/enabled load. The task's
evidence matrix records actual outcomes and limitations separately from this
contract. No performance or effectiveness claim follows from helper-only tests.
