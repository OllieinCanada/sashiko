-- Empty on upgrade: existing work is never enrolled retroactively.
CREATE TABLE IF NOT EXISTS review_cooldown_intents (
    patchset_id INTEGER PRIMARY KEY REFERENCES patchsets(id) ON DELETE RESTRICT,
    list TEXT NOT NULL,
    author TEXT NOT NULL,
    policy TEXT NOT NULL,
    policy_version INTEGER NOT NULL DEFAULT 1 CHECK (policy_version = 1),
    state TEXT NOT NULL CHECK (state IN ('waiting', 'decided', 'blocked')),
    created_at INTEGER NOT NULL CHECK (created_at >= 0),
    admitted_at INTEGER,
    prior_count INTEGER,
    extra_seconds INTEGER,
    decided_deadline INTEGER,
    verified_parts INTEGER,
    verified_version INTEGER,
    history_since INTEGER,
    released_at INTEGER,
    reason TEXT,
    CHECK ((admitted_at IS NULL AND prior_count IS NULL AND extra_seconds IS NULL)
        OR (admitted_at >= 0 AND prior_count >= 0 AND extra_seconds >= 0))
);
CREATE TABLE IF NOT EXISTS review_cooldown_messages (
    message_id TEXT PRIMARY KEY,
    patchset_id INTEGER NOT NULL REFERENCES review_cooldown_intents(patchset_id) ON DELETE RESTRICT,
    source_hash TEXT
);
CREATE INDEX IF NOT EXISTS idx_cooldown_messages_owner ON review_cooldown_messages(patchset_id);
CREATE TABLE IF NOT EXISTS review_cooldown_exclusions (
    patchset_id INTEGER PRIMARY KEY REFERENCES patchsets(id) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    released_at INTEGER
);
CREATE TABLE IF NOT EXISTS review_cooldown_blocks (
    patchset_id INTEGER PRIMARY KEY REFERENCES patchsets(id) ON DELETE RESTRICT,
    reason TEXT NOT NULL
);
CREATE VIEW IF NOT EXISTS review_cooldown_guards AS
    SELECT patchset_id, state FROM review_cooldown_intents
    UNION ALL SELECT patchset_id, 'blocked' AS state FROM review_cooldown_blocks;
CREATE TABLE IF NOT EXISTS review_cooldown_events (
    patchset_id INTEGER PRIMARY KEY REFERENCES review_cooldown_intents(patchset_id) ON DELETE RESTRICT,
    list TEXT NOT NULL,
    author TEXT NOT NULL,
    admitted_at INTEGER NOT NULL CHECK (admitted_at >= 0)
);
CREATE INDEX IF NOT EXISTS idx_cooldown_history ON review_cooldown_events(list, author, admitted_at DESC);
CREATE INDEX IF NOT EXISTS idx_cooldown_retention ON review_cooldown_events(admitted_at);

-- Defense in depth for generic reset/rerun/status writers. The admission
-- transaction decides first, then exposes Pending. Errors never mean legacy.
CREATE TRIGGER IF NOT EXISTS cooldown_status_gate BEFORE UPDATE OF status ON patchsets
WHEN NEW.status IN ('Pending', 'In Review', 'Reviewed') AND EXISTS (
    SELECT 1 FROM review_cooldown_guards c
    WHERE c.patchset_id = NEW.id AND c.state != 'decided'
)
BEGIN
    SELECT RAISE(ABORT, 'adaptive cooldown admission unresolved');
END;

-- A reviewer/release worker may have captured a row before it was quarantined.
-- Abort insertion rather than allowing its stale snapshot to publish.
CREATE TRIGGER IF NOT EXISTS cooldown_email_insert BEFORE INSERT ON email_outbox
WHEN EXISTS (
    SELECT 1 FROM review_cooldown_guards c
    WHERE c.state IN ('waiting','blocked') AND (
        c.patchset_id = (SELECT patchset_id FROM patches WHERE id = NEW.patch_id)
        OR c.patchset_id IN (SELECT patchset_id FROM review_cooldown_messages WHERE message_id = trim(NEW.in_reply_to, '<> ') UNION SELECT patchset_id FROM patches WHERE message_id = trim(NEW.in_reply_to, '<> ') UNION SELECT id FROM patchsets WHERE cover_letter_message_id = trim(NEW.in_reply_to, '<> ')))
)
BEGIN SELECT RAISE(ABORT, 'adaptive publication unresolved'); END;

CREATE TRIGGER IF NOT EXISTS cooldown_patchwork_insert BEFORE INSERT ON patchwork_outbox
WHEN EXISTS (
    SELECT 1 FROM review_cooldown_guards c WHERE c.state IN ('waiting','blocked') AND c.patchset_id IN (SELECT patchset_id FROM review_cooldown_messages WHERE message_id = trim(NEW.patch_msg_id, '<> ') UNION SELECT patchset_id FROM patches WHERE message_id = trim(NEW.patch_msg_id, '<> ') UNION SELECT id FROM patchsets WHERE cover_letter_message_id = trim(NEW.patch_msg_id, '<> '))
)
BEGIN SELECT RAISE(ABORT, 'adaptive publication unresolved'); END;

CREATE TRIGGER IF NOT EXISTS cooldown_forge_insert BEFORE INSERT ON forge_outbox
WHEN EXISTS (SELECT 1 FROM review_cooldown_guards c
             WHERE c.patchset_id = NEW.patchset_id AND c.state IN ('waiting','blocked'))
BEGIN SELECT RAISE(ABORT, 'adaptive publication unresolved'); END;

-- An older ingestion/admin path cannot overwrite a stable decision or re-hold
-- a release. The admission helper changes state after setting the deadline.
CREATE TRIGGER IF NOT EXISTS cooldown_deadline_gate BEFORE UPDATE OF embargo_until ON patchsets
WHEN NEW.embargo_until IS NOT OLD.embargo_until AND (EXISTS (
    SELECT 1 FROM review_cooldown_intents c WHERE c.patchset_id = NEW.id
      AND (c.state = 'decided' OR c.released_at IS NOT NULL)
      AND NEW.embargo_until IS NOT NULL
      AND (c.released_at IS NULL OR NEW.embargo_until > c.released_at)
) OR EXISTS (SELECT 1 FROM review_cooldown_exclusions c WHERE c.patchset_id = NEW.id
             AND c.released_at IS NOT NULL AND NEW.embargo_until > c.released_at))
BEGIN
    SELECT RAISE(IGNORE);
END;

CREATE TABLE IF NOT EXISTS review_cooldown_clock (singleton INTEGER PRIMARY KEY CHECK (singleton = 1), last_admitted_at INTEGER NOT NULL);
INSERT OR IGNORE INTO review_cooldown_clock VALUES (1, 0);

CREATE TRIGGER IF NOT EXISTS cooldown_new_owner BEFORE INSERT ON patchsets
WHEN EXISTS (SELECT 1 FROM review_cooldown_messages
             WHERE message_id = trim(NEW.cover_letter_message_id, '<> '))
BEGIN SELECT RAISE(ABORT, 'adaptive canonical identity already owned'); END;

-- Close the gap between a canonical metadata check and its later write.
CREATE TRIGGER IF NOT EXISTS cooldown_metadata_gate BEFORE UPDATE OF author, total_parts ON patchsets
WHEN EXISTS (SELECT 1 FROM review_cooldown_intents c WHERE c.patchset_id = OLD.id
  AND c.state = 'decided' AND (NEW.total_parts != OLD.total_parts OR c.author != lower(trim(
    CASE WHEN instr(NEW.author, '<') > 0 THEN
      substr(NEW.author, instr(NEW.author, '<') + 1, instr(NEW.author, '>') - instr(NEW.author, '<') - 1)
    ELSE NEW.author END))))
BEGIN
    UPDATE review_cooldown_intents SET state = 'blocked', reason = 'admitted canonical metadata changed' WHERE patchset_id = OLD.id;
    UPDATE patchsets SET status = 'Cooldown blocked', failed_reason = 'admitted canonical metadata changed' WHERE id = OLD.id AND status != 'Cancelled';
    SELECT RAISE(IGNORE);
END;
