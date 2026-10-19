-- Keep held-review supersession independent of archived Reviewed volume.
CREATE INDEX IF NOT EXISTS idx_patchsets_held_series
    ON patchsets(date DESC, id DESC)
    WHERE status = 'Reviewed' AND embargo_until IS NOT NULL;
