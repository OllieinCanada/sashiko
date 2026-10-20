-- Prototype only. Not installed by the production migration runner.
CREATE TABLE conflict_groups (
    id INTEGER PRIMARY KEY,
    state TEXT NOT NULL DEFAULT 'preparing'
        CHECK (state IN ('preparing','active')),
    expected INTEGER NOT NULL CHECK (expected > 0),
    staged INTEGER NOT NULL DEFAULT 0 CHECK (staged >= 0 AND staged <= expected)
);
CREATE TABLE conflict_members (
    patchset_id INTEGER NOT NULL REFERENCES patchsets(id) ON DELETE RESTRICT,
    group_id INTEGER NOT NULL REFERENCES conflict_groups(id) ON DELETE RESTRICT,
    PRIMARY KEY (patchset_id, group_id)
);
CREATE INDEX conflict_members_group ON conflict_members(group_id, patchset_id);
CREATE TRIGGER conflict_member_prepare BEFORE INSERT ON conflict_members
WHEN NOT EXISTS (SELECT 1 FROM conflict_groups
                 WHERE id = NEW.group_id AND state = 'preparing')
BEGIN SELECT RAISE(ABORT, 'membership is sealed'); END;
CREATE TRIGGER conflict_group_activate BEFORE UPDATE ON conflict_groups
WHEN NEW.expected != OLD.expected
  OR (OLD.state = 'active' AND NEW.state != OLD.state)
  OR (NEW.state = 'active' AND NEW.staged != NEW.expected)
BEGIN SELECT RAISE(ABORT, 'invalid group transition'); END;
CREATE TRIGGER conflict_member_handoff BEFORE DELETE ON conflict_members
WHEN EXISTS (SELECT 1 FROM conflict_groups
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
    FROM conflict_members m JOIN conflict_groups g ON g.id = m.group_id
    WHERE g.state = 'active';
