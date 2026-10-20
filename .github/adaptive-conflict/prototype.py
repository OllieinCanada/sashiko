#!/usr/bin/env python3
"""Isolated SQL design checks, not native Rust integration evidence."""
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import time

ROOT = Path.cwd()
OUT = ROOT / "adaptive-conflict-results"
OUT.mkdir(exist_ok=True)
BATCH = 64
BASE_VIEW = """CREATE VIEW review_cooldown_guards AS
SELECT patchset_id,state FROM review_cooldown_intents
UNION ALL SELECT patchset_id,'blocked' FROM review_cooldown_blocks"""
SCHEMA = (ROOT / ".github/adaptive-conflict/guard.sql").read_text()
REPORT = {"status": "RUNNING", "scope": "SQL prototype only",
          "sqlite": sqlite3.sqlite_version, "batch": BATCH, "checks": [],
          "activation_vm_steps": {}, "mutants": [],
          "production_rust_changed": False, "provider_calls": 0}
REPORT["schema_sha256"] = hashlib.sha256(SCHEMA.encode()).hexdigest()


def connect(path):
    db = sqlite3.connect(path, isolation_level=None, timeout=1)
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    return db


def seed(path, count):
    db = connect(path)
    db.executescript("""
    CREATE TABLE patchsets(id INTEGER PRIMARY KEY, status TEXT,
        failed_reason TEXT, embargo_until INTEGER, cover_letter_message_id TEXT,
        author TEXT, total_parts INTEGER);
    CREATE TABLE patches(id INTEGER PRIMARY KEY, patchset_id INTEGER,
        message_id TEXT);
    CREATE TABLE email_outbox(id INTEGER PRIMARY KEY, patch_id INTEGER,
        in_reply_to TEXT);
    CREATE TABLE patchwork_outbox(id INTEGER PRIMARY KEY, patch_msg_id TEXT);
    CREATE TABLE forge_outbox(id INTEGER PRIMARY KEY, patchset_id INTEGER);
    CREATE TABLE unrelated(id INTEGER PRIMARY KEY, n INTEGER);
    INSERT INTO unrelated VALUES(1,0);
    """)
    db.executescript((ROOT / "src/migrations/015_publication_cooldown.sql").read_text())
    db.execute("BEGIN IMMEDIATE")
    db.executemany("INSERT INTO patchsets VALUES(?,'Pending',NULL,NULL,?,?,1)",
                   [(i, str(i) + "@example.test", "author@example.test")
                    for i in range(1, count + 2)])
    db.execute("""INSERT INTO review_cooldown_intents
               (patchset_id,list,author,policy,state,created_at,
                admitted_at,prior_count,extra_seconds)
               VALUES(1,'list@example.test','author@example.test',
                      '{}','decided',1,1,0,0)""")
    db.execute("INSERT INTO review_cooldown_messages VALUES('one@example.test',1,'frozen')")
    db.execute("INSERT INTO review_cooldown_events VALUES(1,'list@example.test','author@example.test',1)")
    db.execute("COMMIT")
    db.executescript(SCHEMA)
    return db


def new_group(db, expected):
    db.execute("BEGIN IMMEDIATE")
    group = db.execute("INSERT INTO conflict_groups(expected) VALUES(?)",
                       (expected,)).lastrowid
    db.execute("COMMIT")
    return group


def stage(db, group, owners):
    assert 0 < len(owners) <= BATCH
    db.execute("BEGIN IMMEDIATE")
    try:
        db.executemany("INSERT INTO conflict_members VALUES(?,?)",
                       [(owner, group) for owner in owners])
        changed = db.execute("""UPDATE conflict_groups SET staged=staged+?
                            WHERE id=? AND state='preparing'""",
                             (len(owners), group)).rowcount
        assert changed == 1
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def activate(db, group):
    db.execute("BEGIN IMMEDIATE")
    try:
        changed = db.execute("""UPDATE conflict_groups SET state='active'
                            WHERE id=? AND state='preparing' AND staged=expected""",
                             (group,)).rowcount
        assert changed == 1, "incomplete group activated"
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise


def blocked(db):
    return {row[0] for row in db.execute(
        "SELECT patchset_id FROM review_cooldown_guards WHERE state='blocked'")}


def frozen(db):
    return (list(db.execute("SELECT * FROM review_cooldown_messages")),
            list(db.execute("SELECT * FROM review_cooldown_events")),
            list(db.execute("SELECT id,cover_letter_message_id FROM patchsets")))


def handoff(db, group):
    owners = [r[0] for r in db.execute(
        "SELECT patchset_id FROM conflict_members WHERE group_id=? ORDER BY patchset_id LIMIT ?",
        (group, BATCH))]
    db.execute("BEGIN IMMEDIATE")
    try:
        for owner in owners:
            db.execute("""UPDATE review_cooldown_intents SET state='blocked',
                       reason='prototype conflict' WHERE patchset_id=?""", (owner,))
            db.execute("""INSERT INTO review_cooldown_blocks
                       SELECT ?, 'prototype conflict' WHERE NOT EXISTS
                       (SELECT 1 FROM review_cooldown_intents WHERE patchset_id=?)
                       ON CONFLICT(patchset_id) DO NOTHING""", (owner, owner))
            db.execute("""UPDATE patchsets SET status='Cooldown blocked',
                       failed_reason='prototype conflict'
                       WHERE id=? AND status!='Cancelled'""", (owner,))
            db.execute("DELETE FROM conflict_members WHERE patchset_id=? AND group_id=?",
                       (owner, group))
        if not db.execute("SELECT 1 FROM conflict_members WHERE group_id=? LIMIT 1",
                          (group,)).fetchone():
            db.execute("DELETE FROM conflict_groups WHERE id=?", (group,))
        db.execute("COMMIT")
    except BaseException:
        db.execute("ROLLBACK")
        raise
    return len(owners)


def expect_failure(action, message):
    try:
        action()
    except (AssertionError, sqlite3.IntegrityError):
        return
    raise AssertionError(message)


def check(name):
    REPORT["checks"].append(name)
    print("PASS " + name, flush=True)


def run(directory):
    path = directory / "main.db"
    count = 1025
    db = seed(path, count)
    reader = connect(path)
    original = frozen(db)
    group = new_group(db, count)
    expect_failure(lambda: activate(db, group), "premature activation allowed")
    for start in range(1, count + 1, BATCH):
        batch = list(range(start, min(start + BATCH, count + 1)))
        stage(db, group, batch)
        assert blocked(reader) == set(), "preparing group became visible"
        reader.execute("BEGIN IMMEDIATE")
        reader.execute("UPDATE unrelated SET n=n+1 WHERE id=1")
        reader.execute("COMMIT")
    check("exact staging; unrelated writer succeeds between every batch")
    db.close()
    db = connect(path)
    assert blocked(db) == set()
    check("restart before activation preserves invisible preparation")
    before = db.execute("SELECT staged FROM conflict_groups WHERE id=?", (group,)).fetchone()
    expect_failure(lambda: stage(db, group, [count, count + 1]),
                   "duplicate membership was not rejected")
    assert db.execute("SELECT staged FROM conflict_groups WHERE id=?", (group,)).fetchone() == before
    assert db.execute("SELECT 1 FROM conflict_members WHERE patchset_id=?",
                      (count + 1,)).fetchone() is None
    check("failed stage rolls back count and unrelated membership")
    activate(db, group)
    expected = set(range(1, count + 1))
    assert blocked(reader) == expected, "atomic quarantine missing owners"
    assert count + 1 not in blocked(reader), "unrelated owner quarantined"
    expect_failure(lambda: stage(db, group, [count + 1]), "sealed group accepted a member")
    expect_failure(lambda: db.execute(
        "DELETE FROM conflict_members WHERE patchset_id=2 AND group_id=?", (group,)),
        "active guard removed without durable handoff")
    db.close()
    db = connect(path)
    assert blocked(db) == expected
    check("atomic activation; sealed exact set; restart retains complete quarantine")
    # A separate group can overlap without changing or removing the first group.
    overlap = new_group(db, 2)
    stage(db, overlap, [2, 3])
    activate(db, overlap)
    assert blocked(reader) == expected
    assert handoff(db, overlap) == 2
    assert blocked(reader) == expected
    check("overlapping groups cannot remove each other's guards")
    transferred = 0
    while db.execute("SELECT 1 FROM conflict_groups WHERE id=?", (group,)).fetchone():
        transferred += handoff(db, group)
        assert blocked(reader) == expected, "handoff exposed an owner"
        reader.execute("UPDATE unrelated SET n=n+1 WHERE id=1")
        db.close()
        db = connect(path)
        assert blocked(db) == expected, "restart lost quarantine during handoff"
    assert transferred == count
    assert frozen(db) == original, "ownership or accounting changed"
    check("bounded handoff and restart preserve every guard, tombstone and frozen event")
    assert db.execute("SELECT COUNT(*) FROM conflict_groups").fetchone()[0] == 0
    check("empty groups removed without cascading membership deletion")
    db.close()
    reader.close()

    # Preparing work abandoned by an owner is cleaned explicitly in bounded batches.
    db = seed(directory / "abandoned.db", 257)
    group = new_group(db, 257)
    stage(db, group, list(range(1, 65)))
    db.close()
    db = connect(directory / "abandoned.db")
    db.execute("BEGIN IMMEDIATE")
    db.execute("""DELETE FROM conflict_members WHERE group_id=? AND patchset_id IN
               (SELECT patchset_id FROM conflict_members WHERE group_id=? LIMIT ?)""",
               (group, group, BATCH))
    db.execute("DELETE FROM conflict_groups WHERE id=?", (group,))
    db.execute("COMMIT")
    assert not blocked(db)
    assert db.execute("SELECT COUNT(*) FROM review_cooldown_events").fetchone()[0] == 1
    check("abandoned preparation cleanup preserves original ownership")
    db.close()

    # Test an independent activation-size oracle using SQLite's VM step callback.
    for size in (1, 64, 4096, 32768):
        db = seed(directory / ("vm-" + str(size) + ".db"), size)
        group = new_group(db, size)
        for start in range(1, size + 1, BATCH):
            stage(db, group, list(range(start, min(start + BATCH, size + 1))))
        steps = [0]
        def progress():
            steps[0] += 1
            return 0
        db.set_progress_handler(progress, 1)
        activate(db, group)
        db.set_progress_handler(None, 0)
        REPORT["activation_vm_steps"][str(size)] = steps[0]
        assert len(blocked(db)) == size
        db.close()
    values = list(REPORT["activation_vm_steps"].values())
    assert max(values) < 500 and max(values) - min(values) <= 10, values
    check("activation VM work independent of member count through 32768 owners")

    for mutation in ("expose-preparing", "drop-active-guard"):
        db = seed(directory / (mutation + ".db"), 2)
        group = new_group(db, 2)
        stage(db, group, [1, 2])
        if mutation == "expose-preparing":
            db.execute("DROP VIEW review_cooldown_guards")
            db.executescript(BASE_VIEW + """
                UNION ALL SELECT patchset_id,'blocked' FROM conflict_members;""")
            try:
                assert blocked(db) == set(), "preparing group became visible"
            except AssertionError as error:
                assert str(error) == "preparing group became visible"
            else:
                raise AssertionError("preparation mutant survived")
        else:
            activate(db, group)
            db.execute("DROP VIEW review_cooldown_guards")
            db.execute(BASE_VIEW)
            try:
                assert blocked(db) == {1, 2}, "atomic quarantine missing owners"
            except AssertionError as error:
                assert str(error) == "atomic quarantine missing owners"
            else:
                raise AssertionError("activation mutant survived")
        REPORT["mutants"].append({"name": mutation, "status": "KILLED"})
        db.close()
    check("two SQL semantic mutants fail their intended independent oracle")


try:
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="adaptive-conflict-") as temporary:
        run(Path(temporary))
    REPORT["seconds"] = time.monotonic() - started
    REPORT["status"] = "PASS"
except BaseException as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    raise
finally:
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
    print(json.dumps(REPORT, indent=2), flush=True)
