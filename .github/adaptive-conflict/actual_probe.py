#!/usr/bin/env python3
"""Measure the candidate migration's SQL VM work; not physical I/O latency."""
import hashlib
import json
from pathlib import Path
import runpy
import tempfile

ROOT = Path.cwd()
helpers = runpy.run_path(str(ROOT / ".github/adaptive-conflict/prototype.py"))
seed = helpers["seed"]
spec_bytes = (ROOT / ".github/adaptive-conflict/candidate.json").read_bytes()
candidate = json.loads(spec_bytes)
migration = candidate["files"]["src/migrations/016_cooldown_conflicts.sql"]
report = {
    "status": "RUNNING",
    "scope": "Python SQLite VM work for the exact candidate migration",
    "candidate_sha256": hashlib.sha256(spec_bytes).hexdigest(),
    "migration_sha256": hashlib.sha256(migration.encode()).hexdigest(),
    "batch": 64, "work": {}, "provider_calls": 0,
    "limitations": [
        "VM instructions are not disk I/O, elapsed writer time or native libsql instruction counts.",
        "Total staging work, total storage and canonical scanning remain proportional to group size."
    ]
}
OUT = ROOT / "adaptive-conflict-results"


def measured(db, action):
    steps = [0]
    def progress():
        steps[0] += 1
        return 0
    db.set_progress_handler(progress, 1)
    try:
        action()
    finally:
        db.set_progress_handler(None, 0)
    return steps[0]


def stage(db, group, owners):
    assert len(owners) <= 64
    db.execute("BEGIN IMMEDIATE")
    db.execute("""UPDATE review_cooldown_conflicts SET staged=staged+?
               WHERE id=? AND state='preparing'""", (len(owners), group))
    db.executemany("INSERT INTO review_cooldown_conflict_members VALUES(?,?)",
                   [(owner, group) for owner in owners])
    db.execute("COMMIT")


def activate(db, group):
    db.execute("BEGIN IMMEDIATE")
    changed = db.execute("""UPDATE review_cooldown_conflicts SET state='active'
                         WHERE id=? AND state='preparing' AND staged=expected
                           AND lease_until>=1""", (group,)).rowcount
    assert changed == 1
    db.execute("COMMIT")


def handoff(db, group):
    db.execute("BEGIN IMMEDIATE")
    owners = [r[0] for r in db.execute(
        """SELECT patchset_id FROM review_cooldown_conflict_members
           WHERE group_id=? ORDER BY patchset_id LIMIT 64""", (group,))]
    assert len(owners) == 64
    for owner in owners:
        db.execute("""UPDATE review_cooldown_intents SET state='blocked',
                   reason='candidate VM probe' WHERE patchset_id=?""", (owner,))
        db.execute("""INSERT INTO review_cooldown_blocks
                   SELECT ?, 'candidate VM probe' WHERE NOT EXISTS
                   (SELECT 1 FROM review_cooldown_intents WHERE patchset_id=?)
                   ON CONFLICT(patchset_id) DO NOTHING""", (owner, owner))
        db.execute("""UPDATE patchsets SET status='Cooldown blocked',
                   failed_reason='candidate VM probe'
                   WHERE id=? AND status!='Cancelled'""", (owner,))
        db.execute("""DELETE FROM review_cooldown_conflict_members
                   WHERE patchset_id=? AND group_id=?""", (owner, group))
    assert db.execute("""SELECT 1 FROM review_cooldown_conflict_members
                      WHERE group_id=? LIMIT 1""", (group,)).fetchone()
    db.execute("COMMIT")


try:
    with tempfile.TemporaryDirectory(prefix="actual-conflict-vm-") as temporary:
        for size in (128, 4096, 32768):
            db = seed(Path(temporary) / (str(size) + ".db"), size)
            db.executescript(migration)
            group = db.execute("""INSERT INTO review_cooldown_conflicts
                               (expected,reason,created_at,lease_until)
                               VALUES(?, 'candidate VM probe', 1, 3601)""",
                               (size,)).lastrowid
            first_stage = measured(db, lambda: stage(db, group, list(range(1, 65))))
            for start in range(65, size + 1, 64):
                stage(db, group, list(range(start, min(start + 64, size + 1))))
            activation = measured(db, lambda: activate(db, group))
            first_handoff = measured(db, lambda: handoff(db, group))
            blocked = {r[0] for r in db.execute(
                "SELECT patchset_id FROM review_cooldown_guards WHERE state='blocked'")}
            assert blocked == set(range(1, size + 1)), "handoff lost an exact owner"
            assert db.execute(
                "SELECT COUNT(*) FROM review_cooldown_conflict_members").fetchone()[0] == size - 64
            report["work"][str(size)] = {
                "stage_64": first_stage, "activate": activation,
                "handoff_64": first_handoff}
            db.close()
    for phase in ("stage_64", "activate", "handoff_64"):
        values = [row[phase] for row in report["work"].values()]
        assert max(values) - min(values) <= 10, (phase, values)
        assert max(values) < (500 if phase == "activate" else 50000), (phase, values)
    report["status"] = "PASS"
except BaseException as error:
    report["status"] = "FAIL"
    report["error"] = str(error)
    raise
finally:
    (OUT / "actual-migration-vm.json").write_text(json.dumps(report, indent=2) + "\n")
    print("ACTUAL_MIGRATION_VM_JSON " + json.dumps(report), flush=True)
