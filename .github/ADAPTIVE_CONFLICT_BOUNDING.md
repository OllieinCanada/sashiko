> **Current validation (2026-10-20).** Review head d7f7a5516cc805444f23c534199af7e65d51e551
> has the identical source tree as tested a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9.
> 1126 native tests, eleven scoped phases, maximum-series and performance
> median budgets passed. Model review timed out; maintainer agreement absent.
> [Current evidence](ADAPTIVE_UPSTREAM_REFRESH.md) supersedes current-status
> claims below. Historical 55/8/1 counts are preserved, not recertified.

# Bounded conflict quarantine

This change addresses SQLite writer work during adaptive canonical conflicts.
It does not declare the adaptive feature ready for an upstream PR.

## Implementation

The matcher keeps every canonical owner; there is no truncated match list.
Adaptive conflict detection uses an explicit deferred read transaction, since
both pre-existing transaction helpers reserve the writer immediately.
Membership is staged in transactions of at most 64 owners. One indexed update
activates the complete group's publication guard atomically. Bounded batches
then transfer protection to the existing owner blocks before deleting temporary
membership. SQL triggers prevent premature activation or a gap during handoff.

Direct source binding, admission, ownership lookup, and early release also honor
active groups. Startup and reviewer polling resume active transfers and clean
expired preparations. Preparations carry a renewable one-hour lease, so one
process cannot clean another process's live work. Group IDs are never reused.
Ownership tombstones and frozen accounting are retained.

## Reproducible checks

Native audit checkpoint: a34b3e366ed06fff98ca9784fcd7a343cc73942e
Native checked source commit: b24d9e05094ccfcf7609a46bb254608a3177dea1
Native checked tree: 618c4b54b7eaabfae517bc5f3b302b10612bd86c
Native run: https://github.com/OllieinCanada/sashiko/actions/runs/39353773252/artifacts/12233813964
Required suite: 1,115 passed, 0 failed, 2 ignored; fmt and all three Clippy profiles passed.

Four new native fixtures cover exact membership with an unrelated owner inside
the ID range, active protection in all three publication queues and their
insertion triggers, direct binding/admission/early release, bounded handoff,
reopen/recovery, overlapping groups, failed-stage rollback, expired cleanup,
independent writers, and rejection of a stale legacy write snapshot.
Two separately compiled semantic mutations fail their intended assertions.
The restored candidate passes make check-pr, including fmt and all three Clippy
profiles. A native signed-off source commit is created only after checks pass.

The exact migration's SQL probe passed on SQLite 3.45.1:
[run 39353861254](https://github.com/OllieinCanada/sashiko/actions/runs/39353861254).

| Representative SQL operation | 128 owners | 4,096 owners | 32,768 owners |
| --- | ---: | ---: | ---: |
| Stage 64 members, VM steps | 3977 | 3977 | 3977 |
| Activate, VM steps | 112 | 112 | 112 |
| Handoff 64 members, VM steps | 11767 | 11767 | 11767 |

These are Python SQLite VM counts over the candidate migration, not native
libsql instruction counts, disk I/O, or elapsed writer latency.

## Limits and remaining gates

- Canonical scanning, total history/storage, and total preparation work remain
  proportional to group size. The deferred read holds this handle's transaction
  mutex; independent database connections can write during detection, but this
  is not a universal latency bound for tasks sharing that mutex. D06 is not
  silently upgraded to fully verified.
- Legacy merge writes after a deferred snapshot can fail closed if another
  connection commits first; the regression verifies that stale snapshots
  cannot upgrade to writes.
- New queue claims and inserts honor activation. A delivery claimed before
  activation can still finish afterwards. External delivery is not atomic
  with SQLite quarantine.
- Cleanup of abandoned preparation happens on subsequent startup or reviewer
  polling; paused workers do not provide continuous garbage collection.
- This adds schema version 16. Refresh feature-specific fault/replay, performance,
  clock and stopped-system rollback evidence on the new source before an
  upstream PR. The old 55/8/1 acceptance counts describe the bd59059 baseline,
  not full certification of this new candidate.
- Required completed model review and maintainer policy agreement remain open.
  The model workflow stays disabled; no provider calls, real email, deployment
  or upstream PR are part of these checks.
- Upstream PR 685 may require migration renumbering and revalidation if it lands.

## Negative results preserved

- 39352557122 / 434233ce: harness rejected bytecode created by its own syntax
  preflight. Fixed by AST parsing without generating an untracked cache.
- 39352675388 / d8d17a42: new fixture owner IDs needed explicit i64 typing.
- 39352801673 / 39362275: new fixtures violated actual message foreign keys.
  Real messages and patches are now seeded; foreign-key enforcement stays on.
- 39353015323 / 36f8b3df: new native fixtures, both semantic mutants, fmt and
  Clippy passed. Full suite found one pre-existing migration test expecting 15
  rather than the new 16; 1,035 other library tests passed. Its schema
  expectation was updated; this was not labeled an upstream failure.

The saved source is verified against the bundled native commit by comparing
all tracked production paths; only .github audit files are excluded.
The source-only upstream series still needs refreshing before submission.

## Saved source and supplemental outcomes

Saved source commit: **54a5abc1894bd0fcba1ebbfd7acf20044d7e5091**.
[Exact production-tree verification passed](https://github.com/OllieinCanada/sashiko/actions/runs/39354526665/artifacts/12234921096).
It confirms that every production path equals the checked native bundle,
excluding only .github audit material.

Two automatic existing-admission regressions also completed on this source:
[16 writers / 128 admissions / 128 replays / 64 releases](https://github.com/OllieinCanada/sashiko/actions/runs/39354526733/artifacts/12234648775)
and [ENOSPC, EIO, torn WAL and pre/post-commit SIGKILL](https://github.com/OllieinCanada/sashiko/actions/runs/39354526702/artifacts/12234319196).
These do not cover every new conflict-group crash phase or real storage failure.

Saving src changes triggered older src/** audit workflows. Nine older jobs and
one redundant SQL job were stopped at this exact source SHA. The SQL job's
diff-aware preflight had selected another full Rust build, while the same
migration probe had already passed. Three older jobs completed successfully.
The old rollback harness exited with **frozen production source changed**
([run](https://github.com/OllieinCanada/sashiko/actions/runs/39354526657)).
It did not test rollback of schema 16 and is not an upstream failure.
The final exact-source verification was retained and passed.

At 2026-10-20 01:42:00 UTC, upstream had advanced by three benchmark/CLI commits
to **026195ab58e2099e81017adbc6b97f33c509c8ba**.
Those changes also touch Cargo.toml, main, fetcher, reviewer and review prompts.
The checked candidate is based on f6e2e172e1e669b6767a4c74fe91d062b41fd71c;
refresh against the new upstream and repeat applicable checks before a PR.
PR 685 remains open and unmerged. No upstream PR or provider call was made.
