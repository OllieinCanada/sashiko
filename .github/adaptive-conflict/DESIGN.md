# Bounded canonical-conflict quarantine (proposal)

Status: architecture approved by the user; native candidate validation pending.
The isolated SQL prototype passed; production source is unchanged on the fork.
Base runtime: bd59059f1864aea81b11b5de0eb97e5d2ec53667.

## Problem and invariant

Both ambiguous late-cover and canonical-merge paths iterate every matching
owner under one writer transaction. Merely committing each owner separately
would expose a partially quarantined group. A LIMIT on matches would omit
owners and weaken duplicate protection.

Preserve the complete canonical match set, all message ownership tombstones,
frozen accounting, and all-or-nothing visibility of quarantine. Never move or
merge owners in an adaptive conflict. An already accepted external delivery
cannot be recalled; this change does not redefine that existing boundary.

## Proposed mechanism

Add an indexed conflict-group table and exact member table. A group starts
preparing. Its members are staged in batches of at most 64 owners, using
short immediate transactions with indexed point operations. Preparing rows
do not appear in the publication guard view. Membership references restrict
deletion of owners while staging. No broad author, thread or ID-range block
is introduced.

The caller detects adaptive participation in a deferred read transaction,
using an explicit deferred helper. Both existing transaction helpers open
IMMEDIATE transactions; neither is suitable for detection. Read work is
outside the SQLite writer lock. On detecting an adaptive conflict, roll that transaction back;
do not execute the old per-owner blocking loop. The late-cover path must also
use a deferred read transaction for detection. Pure legacy merge behavior is
outside this replacement and retains its existing transaction semantics.

After every exact member has been staged, activate one group row in a
bounded transaction. A maintained staged count must equal the immutable
expected count. Do not count or update all members during activation.
Extend review_cooldown_guards with an indexed join to active group members.
One commit then makes the entire group blocked to every guard consumer.

Materialize the existing per-owner block/status updates in batches of 64.
For each owner, insert/update its durable block first and delete its temporary
membership in the same transaction. Readers therefore see either the group
guard or the durable owner guard, with no gap. Remove an empty group only
after indexed existence checks. Never cascade-delete an unbounded group.

## Integration review required before Rust implementation

- Migration on fresh and upgraded databases; renumber against upstream if
  overlapping PR 685 lands.
- Publication claims and insertion triggers, release/early release, review
  claims, public visibility, rerun/status writers, and cancellation must all
  honor an active group.
- Direct intent/block reads in source binding and owner lookup must also
  honor active membership. A decided intent must never override a blocked
  group. The view alone is insufficient.
- Recovery drains active groups in bounded batches. Preparing groups abandoned
  by a crashed caller need bounded cleanup, without activating incomplete sets.
  Preparing groups carry a renewable one-hour lease. Startup and reviewer polling
  clean only expired preparations, in bounded batches. Group IDs never reuse.
  Concurrent preparation must use distinct group identities and exact members;
  one preparer cannot remove another's group.
- SQLite serializes activation and claims. A claim committed before activation
  has the existing stale-worker protections; activation cannot retract a
  delivery already accepted by an external system.
- Cancellation before activation has the same externally visible quarantine
  outcome as rolling back the original transaction. Cancellation after
  activation leaves the complete group durably protected.
- Ordinary work between batches must be able to acquire the writer lock.
  The deferred read holds this handle's transaction mutex; independent database
  connections can write during detection. It does not guarantee bounded latency
  for another task sharing that mutex during an unbounded canonical scan.
  Bound database work, not wall-clock duration under arbitrary disk failure.
- All source changes require make check-pr and native regressions. The SQL
  prototype does not replace libsql/Rust integration or required model review.

## Validation plan

An isolated SQLite prototype checks exact membership, atomic activation,
reopen before/after activation and during materialization, overlapping groups,
failure rollback, count/immutability guards, and bounded cleanup. Independently
count VM instructions for activation across increasing group sizes and exercise
an unrelated second-connection writer between batches.

Then implement native Rust paths and test actual ingestion ambiguity, duplicate
replay, concurrent connections, cancelled preparation, restart recovery, all
publication queues and early release. Kill a mutation that exposes preparing
members and a mutation that drops the group guard before durable owner blocks.
Run required feature profiles and the final exact-revision suite. Repeat
enabled/disabled performance checks because every guard lookup gains a branch.

## Tradeoffs and limits

This is a schema/recovery change, not a limit on accepted group size.
Canonical candidate scanning and total storage remain potentially unbounded;
this proposal addresses writer work per transaction only. Staging causes
bounded additional transactions, temporary storage and indexed read overhead.
Abandoned groups must not leak indefinitely. Old binaries do not understand
active group guards, so the stopped-system rollback rehearsal must be updated
before this candidate can be submitted.

No upstream PR, deployment, email or model call is part of this prototype.
