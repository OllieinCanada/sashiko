-- Exact membership is staged before one atomic publication-guard activation.
CREATE TABLE IF NOT EXISTS review_cooldown_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    state TEXT NOT NULL DEFAULT 'preparing'
        CHECK (state IN ('preparing','active','abandoned')),
    reason TEXT NOT NULL,
    created_at INTEGER NOT NULL CHECK (created_at >= 0),
    lease_until INTEGER NOT NULL CHECK (lease_until >= created_at),
    expected INTEGER NOT NULL CHECK (expected > 0),
    staged INTEGER NOT NULL DEFAULT 0 CHECK (staged >= 0 AND staged <= expected)
);
CREATE INDEX IF NOT EXISTS cooldown_conflicts_state ON review_cooldown_conflicts(state, id);
CREATE INDEX IF NOT EXISTS cooldown_conflicts_expiry ON review_cooldown_conflicts(lease_until)
    WHERE state = 'preparing';
CREATE TABLE IF NOT EXISTS review_cooldown_conflict_members (
    patchset_id INTEGER NOT NULL REFERENCES patchsets(id) ON DELETE RESTRICT,
    group_id INTEGER NOT NULL REFERENCES review_cooldown_conflicts(id) ON DELETE RESTRICT,
    PRIMARY KEY (patchset_id, group_id)
);
CREATE INDEX IF NOT EXISTS review_cooldown_conflict_members_group ON review_cooldown_conflict_members(group_id, patchset_id);
CREATE TRIGGER IF NOT EXISTS cooldown_conflict_member_prepare BEFORE INSERT ON review_cooldown_conflict_members
WHEN NOT EXISTS (SELECT 1 FROM review_cooldown_conflicts
                 WHERE id = NEW.group_id AND state = 'preparing')
BEGIN SELECT RAISE(ABORT, 'membership is sealed'); END;
CREATE TRIGGER IF NOT EXISTS cooldown_conflict_group_activate BEFORE UPDATE ON review_cooldown_conflicts
WHEN NEW.expected != OLD.expected OR NEW.reason != OLD.reason
  OR (OLD.state = 'abandoned' AND NEW.state != OLD.state)
  OR (OLD.state = 'active' AND NEW.state != OLD.state)
  OR (NEW.state = 'active' AND NEW.staged != NEW.expected)
BEGIN SELECT RAISE(ABORT, 'invalid group transition'); END;
CREATE TRIGGER IF NOT EXISTS cooldown_conflict_member_handoff BEFORE DELETE ON review_cooldown_conflict_members
WHEN EXISTS (SELECT 1 FROM review_cooldown_conflicts
             WHERE id = OLD.group_id AND state = 'active')
 AND NOT EXISTS (SELECT 1 FROM review_cooldown_intents
                 WHERE patchset_id = OLD.patchset_id AND state = 'blocked')
 AND NOT EXISTS (SELECT 1 FROM review_cooldown_blocks
                 WHERE patchset_id = OLD.patchset_id)
BEGIN SELECT RAISE(ABORT, 'durable owner block required'); END;
DROP VIEW review_cooldown_guards;
CREATE VIEW review_cooldown_guards AS
    SELECT patchset_id, state FROM review_cooldown_intents
    UNION ALL SELECT patchset_id, 'blocked' FROM review_cooldown_blocks
    UNION ALL
    SELECT m.patchset_id, 'blocked'
    FROM review_cooldown_conflict_members m JOIN review_cooldown_conflicts g ON g.id = m.group_id
    WHERE g.state = 'active';
