// Copyright 2026 The Sashiko Authors
// SPDX-License-Identifier: Apache-2.0

//! Transaction-level admission. No external I/O, payload decompression or waits.
use super::*;
use crate::cooldown::{CooldownContext, CooldownPolicy, MAX_SERIES_PARTS, author_key, message_key};

impl Database {
    pub fn with_cooldown_context(&self, context: Option<CooldownContext>) -> Self {
        let mut handle = self.with_bug_actor(&self.bug_actor, &self.bug_tool, self.bug_model.clone());
        handle.cooldown_context = context;
        handle
    }

    pub(super) fn cooldown_now() -> Result<i64> {
        i64::try_from(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_secs())
            .context("adaptive cooldown clock overflow")
    }

    pub(super) async fn cooldown_owner(conn: &libsql::Connection, message: &str) -> Result<Option<i64>> {
        let key = message_key(message)?;
        let mut rows = conn.query("SELECT patchset_id FROM review_cooldown_messages WHERE message_id = ?", libsql::params![key]).await?;
        rows.next().await?.map(|r| r.get(0)).transpose().map_err(Into::into)
    }

    pub(super) async fn block_cooldown(conn: &libsql::Connection, id: i64, reason: &str) -> Result<()> {
        conn.execute("UPDATE review_cooldown_intents SET state = 'blocked', reason = ? WHERE patchset_id = ?", libsql::params![reason, id]).await?;
        conn.execute("UPDATE patchsets SET status = 'Cooldown blocked', failed_reason = ? WHERE id = ? AND EXISTS (SELECT 1 FROM review_cooldown_intents WHERE patchset_id = ?)", libsql::params![reason, id, id]).await?;
        Ok(())
    }

    /// Does not enroll existing legacy rows. On a conflict quarantine is committed
    /// before the caller receives the error, so a retry cannot publish old state.
    pub(super) async fn bind_cooldown_message(&self, id: i64, message: &str) -> Result<()> {
        let tx = self.begin_immediate_transaction().await?;
        let result = Self::bind_cooldown_message_tx(&tx, id, message, self.cooldown_context.as_ref()).await;
        match result {
            Ok(()) => tx.commit().await,
            Err(error) => {
                Self::block_cooldown(&tx, id, "conflicting adaptive ingestion context").await?;
                tx.commit().await?;
                Err(error)
            }
        }
    }

    pub(super) async fn bind_cooldown_message_tx(conn: &libsql::Connection, id: i64, message: &str, context: Option<&CooldownContext>) -> Result<()> {
        let mut rows = conn.query("SELECT list, author, policy, state FROM review_cooldown_intents WHERE patchset_id = ?", libsql::params![id]).await?;
        let Some(row) = rows.next().await? else { return Ok(()); };
        let list: String = row.get(0)?;
        let author: String = row.get(1)?;
        let policy: CooldownPolicy = serde_json::from_str(&row.get::<String>(2)?)?;
        let state: String = row.get(3)?;
        if state == "blocked" { bail!("adaptive cooldown is quarantined"); }
        let key = message_key(message)?;
        if let Some(owner) = Self::cooldown_owner(conn, &key).await? {
            if owner != id { bail!("adaptive message belongs to another canonical series"); }
            // Frozen input can be retried after policy disable/reload.
            if context.is_none() { return Ok(()); }
        } else if state == "decided" {
            bail!("cannot append to an admitted adaptive revision");
        }
        let Some(context) = context else { bail!("adaptive series requires matching mail policy"); };
        if context.list != list || context.author != author || context.policy != policy {
            bail!("adaptive scope or policy changed during ingestion");
        }
        conn.execute("INSERT INTO review_cooldown_messages(message_id, patchset_id) VALUES (?, ?) ON CONFLICT(message_id) DO NOTHING", libsql::params![key, id]).await?;
        Ok(())
    }

    pub(super) async fn insert_cooldown_intent(&self, id: i64, message: &str, cover: Option<&str>) -> Result<()> {
        let Some(context) = &self.cooldown_context else { return Ok(()); };
        context.policy.validate()?;
        self.conn.execute("INSERT INTO review_cooldown_intents(patchset_id, list, author, policy, state, created_at) VALUES (?, ?, ?, ?, 'waiting', ?)", libsql::params![id, context.list.clone(), context.author.clone(), serde_json::to_string(&context.policy)?, Self::cooldown_now()?]).await?;
        if let Some(until) = context.legacy_deadline {
            self.conn.execute("UPDATE patchsets SET embargo_until = ? WHERE id = ?", libsql::params![until, id]).await?;
        }
        Self::bind_cooldown_message_tx(&self.conn, id, message, Some(context)).await?;
        if let Some(cover) = cover { Self::bind_cooldown_message_tx(&self.conn, id, cover, Some(context)).await?; }
        Ok(())
    }

    /// Runs inside the existing immediate writer transaction. The same operation
    /// handles final-part arrival and a late cover correcting the denominator.
    pub(super) async fn complete_patchset_tx(conn: &libsql::Connection, id: i64, now: i64) -> Result<()> {
        let mut rows = conn.query("SELECT c.list, c.author, c.policy, c.state, c.released_at, p.total_parts, p.embargo_until, p.status FROM review_cooldown_intents c JOIN patchsets p ON p.id = c.patchset_id WHERE c.patchset_id = ?", libsql::params![id]).await?;
        if let Some(row) = rows.next().await? {
            let state: String = row.get(3)?;
            if state == "blocked" { bail!("adaptive cooldown is quarantined"); }
            if state == "waiting" {
                let list: String = row.get(0)?;
                let author: String = row.get(1)?;
                let policy: CooldownPolicy = serde_json::from_str(&row.get::<String>(2)?)?;
                policy.validate()?;
                let released = get_optional_integer(&row, 4)?;
                let total: u32 = row.get(5)?;
                let legacy = get_optional_integer(&row, 6)?;
                let status: String = row.get(7)?;
                if !matches!(status.as_str(), "Incomplete" | "Fetching") { return Ok(()); }
                if total == 0 || total > MAX_SERIES_PARTS { bail!("adaptive series exceeds supported part bound"); }
                let mut parts = conn.query("SELECT p.part_index, p.message_id, m.author, m.subject, c.patchset_id FROM patches p LEFT JOIN messages m ON m.message_id = p.message_id LEFT JOIN review_cooldown_messages c ON c.message_id = p.message_id WHERE p.patchset_id = ? ORDER BY p.part_index, p.id LIMIT ?", libsql::params![id, MAX_SERIES_PARTS + 1]).await?;
                let mut count = 0;
                while let Some(part) = parts.next().await? {
                    count += 1;
                    let index: u32 = part.get(0)?;
                    let message: String = part.get(1)?;
                    let stored_author: String = part.get(2)?;
                    let subject: String = part.get(3)?;
                    let owner: Option<i64> = part.get(4)?;
                    let (subject_index, subject_total) = crate::patch::parse_subject_index(&subject);
                    if count > total || index == 0 || index > total || author_key(&stored_author)? != author
                        || subject_index != index || subject_total != total
                        || message_key(&message)? != message || owner != Some(id)
                    { bail!("adaptive series has inconsistent parts or ownership"); }
                }
                if count < total { return Ok(()); }
                let mut unique = conn.query("SELECT COUNT(DISTINCT part_index) FROM patches WHERE patchset_id = ?", libsql::params![id]).await?;
                if unique.next().await?.context("missing part count")?.get::<u32>(0)? != total {
                    bail!("adaptive series has duplicate part indices");
                }
                if now < 0 { bail!("adaptive admission clock is invalid"); }
                let mut clock = conn.query("SELECT last_admitted_at FROM review_cooldown_clock WHERE singleton = 1", ()).await?;
                if clock.next().await?.context("missing adaptive clock state")?.get::<i64>(0)? > now {
                    bail!("adaptive admission clock moved backwards");
                }
                let mut latest = conn.query("SELECT admitted_at FROM review_cooldown_events WHERE list = ? AND author = ? ORDER BY admitted_at DESC LIMIT 1", libsql::params![list.clone(), author.clone()]).await?;
                if let Some(latest) = latest.next().await? && latest.get::<i64>(0)? > now {
                    bail!("adaptive admission clock moved backwards");
                }
                let mut history = conn.query("SELECT COUNT(*) FROM (SELECT 1 FROM review_cooldown_events INDEXED BY idx_cooldown_history WHERE list = ? AND author = ? AND admitted_at > ? AND admitted_at <= ? ORDER BY admitted_at DESC LIMIT ?)", libsql::params![list.clone(), author.clone(), now.saturating_sub(i64::from(policy.window_seconds)), now, policy.history_limit()?]).await?;
                let prior: u32 = history.next().await?.context("missing adaptive count")?.get(0)?;
                let extra = policy.extra_seconds(prior)?;
                let deadline = if released.is_some() { legacy } else { policy.deadline(now, legacy, prior)? };
                conn.execute("INSERT INTO review_cooldown_events(patchset_id, list, author, admitted_at) VALUES (?, ?, ?, ?)", libsql::params![id, list, author, now]).await?;
                conn.execute("UPDATE patchsets SET embargo_until = ? WHERE id = ?", libsql::params![deadline, id]).await?;
                conn.execute("UPDATE review_cooldown_intents SET state = 'decided', admitted_at = ?, prior_count = ?, extra_seconds = ? WHERE patchset_id = ? AND state = 'waiting'", libsql::params![now, prior, extra, id]).await?;
                conn.execute("UPDATE review_cooldown_clock SET last_admitted_at = ? WHERE singleton = 1", libsql::params![now]).await?;
                // Expensive history never accumulates on the hot counting path.
                // Intent and message ownership remain dedup tombstones. Pruning
                // is indexed and bounded independently of historical volume.
                conn.execute("DELETE FROM review_cooldown_events WHERE patchset_id IN (SELECT patchset_id FROM review_cooldown_events WHERE admitted_at < ? ORDER BY admitted_at LIMIT 64)", libsql::params![now.saturating_sub(i64::from(crate::cooldown::MAX_WINDOW_SECONDS))]).await?;
            }
        }
        conn.execute("UPDATE patchsets SET status = 'Pending' WHERE id = ? AND received_parts >= total_parts AND status IN ('Incomplete', 'Fetching')", libsql::params![id]).await?;
        Ok(())
    }

    pub(super) async fn complete_patchset(&self, id: i64) -> Result<()> {
        let tx = self.begin_immediate_transaction().await?;
        Self::complete_patchset_tx(&tx, id, Self::cooldown_now()?).await?;
        tx.commit().await
    }

    pub async fn cooldown_publication_blocked(&self, id: i64) -> Result<bool> {
        let mut rows = self.conn.query("SELECT 1 FROM review_cooldown_intents WHERE patchset_id = ? AND state != 'decided'", libsql::params![id]).await?;
        Ok(rows.next().await?.is_some())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    async fn database() -> Result<Database> {
        let db = Database::new(&DatabaseSettings { url: ":memory:".into(), token: String::new() }).await?;
        db.migrate().await?;
        Ok(db)
    }

    fn context(list: &str, author: &str) -> CooldownContext {
        CooldownContext { list: list.into(), author: author.into(), policy: CooldownPolicy { window_seconds: 100, burst: 2, step_seconds: 10, max_extra_seconds: 30 }, legacy_deadline: None }
    }

    async fn seed(db: &Database, token: &str, total: u32) -> Result<(i64, i64, String)> {
        let message = format!("{token}-1@example.test");
        let subject = format!("[PATCH 1/{total}] {token}");
        let thread = db.create_thread(&message, &subject, 1).await?;
        db.create_message(&message, thread, None, "Dev <dev@example.test>", &subject, 1, "body", "list@example.test", "", None, None).await?;
        let id = db.create_patchset(thread, Some(&message), &message, &subject, "Dev <dev@example.test>", 1, total, 3, "list@example.test", "", None, 1, None, true, None, None).await?.context("missing fixture series")?;
        Ok((id, thread, message))
    }

    async fn admit_at(db: &Database, id: i64, message: &str, now: i64) -> Result<()> {
        let tx = db.begin_immediate_transaction().await?;
        tx.execute("INSERT INTO patches(patchset_id,message_id,part_index,diff) VALUES (?, ?, 1, 'diff')", libsql::params![id, message]).await?;
        tx.execute("UPDATE patchsets SET received_parts = 1 WHERE id = ?", libsql::params![id]).await?;
        Database::complete_patchset_tx(&tx, id, now).await?;
        tx.commit().await
    }

    async fn scalar(db: &Database, sql: &str) -> Result<i64> {
        Ok(db.conn.query(sql, ()).await?.next().await?.context("missing scalar")?.get(0)?)
    }

    #[tokio::test]
    async fn test_cooldown_hand_trace_scope_and_window() -> Result<()> {
        let db = database().await?;
        let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        // Independent oracle: burst=2, step=10, cap=30; window excludes t-100.
        for (token, now, prior, extra) in [("a", 1000, 0, 0), ("b", 1001, 1, 0), ("c", 1002, 2, 10), ("d", 1003, 3, 20), ("e", 1004, 4, 30), ("f", 1005, 4, 30), ("g", 1105, 0, 0)] {
            let (id, _, message) = seed(&active, token, 1).await?;
            admit_at(&active, id, &message, now).await?;
            let mut rows = db.conn.query("SELECT prior_count, extra_seconds, admitted_at, embargo_until FROM review_cooldown_intents c JOIN patchsets p ON p.id = c.patchset_id WHERE p.id = ?", libsql::params![id]).await?;
            let row = rows.next().await?.context("missing decision")?;
            assert_eq!(row.get::<u32>(0)?, prior);
            assert_eq!(row.get::<u32>(1)?, extra);
            assert_eq!(row.get::<i64>(2)?, now);
            assert_eq!(row.get::<Option<i64>>(3)?, (extra > 0).then_some(now + i64::from(extra)));
        }
        let other_list = db.with_cooldown_context(Some(context("other@example.test", "dev@example.test")));
        let (id, _, message) = seed(&other_list, "separate", 1).await?;
        admit_at(&other_list, id, &message, 1105).await?;
        assert_eq!(scalar(&db, "SELECT prior_count FROM review_cooldown_intents WHERE list = 'other@example.test'").await?, 0);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_incomplete_out_of_order_and_duplicate() -> Result<()> {
        let db = database().await?;
        let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, thread, first) = seed(&active, "multipart", 2).await?;
        assert!(!db.claim_patchset_for_review(id).await?);
        assert!(db.update_patchset_status(id, "Pending").await.is_err());
        let second = "multipart-2@example.test";
        active.create_message(second, thread, Some(&first), "DEV@EXAMPLE.TEST", "[PATCH 2/2] second", 1, "body2", "list@example.test", "", None, None).await?;
        active.bind_cooldown_message(id, second).await?;
        active.create_patch(id, second, 2, "diff2").await?;
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 0);
        assert_eq!(db.get_patchset_status(id).await?.as_deref(), Some("Incomplete"));
        active.create_patch(id, &first, 1, "diff1").await?;
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
        active.create_patch(id, &first, 1, "diff1").await?;
        // Replay without opt-in context (configuration removed after admission).
        db.create_patch(id, second, 2, "diff2").await?;
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
        assert!(db.claim_patchset_for_review(id).await?);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_release_before_admission_and_no_rehold() -> Result<()> {
        let db = database().await?;
        let mut ctx = context("list@example.test", "dev@example.test");
        ctx.policy.burst = 1;
        let active = db.with_cooldown_context(Some(ctx));
        let (first, _, msg) = seed(&active, "prior", 1).await?;
        admit_at(&active, first, &msg, 1000).await?;
        let (id, _, msg) = seed(&active, "released", 1).await?;
        assert!(db.release_patchset_embargo(id, 1001).await?);
        assert!(!db.claim_patchset_for_review(id).await?);
        admit_at(&active, id, &msg, 1002).await?;
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets WHERE embargo_until IS NOT NULL").await?, 0);
        db.set_patchset_embargo_until(id, 9999).await?;
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets WHERE embargo_until IS NOT NULL").await?, 0);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_history_failure_rolls_back_and_retries() -> Result<()> {
        let db = database().await?;
        let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, _, msg) = seed(&active, "retry", 1).await?;
        db.execute_batch("CREATE TRIGGER fail_cooldown_event BEFORE INSERT ON review_cooldown_events BEGIN SELECT RAISE(ABORT, 'fixture failure'); END;").await?;
        assert!(active.create_patch(id, &msg, 1, "diff").await.is_err());
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 0);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 0);
        assert_eq!(db.get_patchset_status(id).await?.as_deref(), Some("Incomplete"));
        db.execute_batch("DROP TRIGGER fail_cooldown_event;").await?;
        active.create_patch(id, &msg, 1, "diff").await?;
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_source_correction_quarantine_survives_expiry() -> Result<()> {
        let db = database().await?;
        let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, thread, msg) = seed(&active, "immutable", 1).await?;
        active.create_patch(id, &msg, 1, "diff").await?;
        assert!(db.create_message(&msg, thread, None, "victim@example.test", "[PATCH] altered", 1, "changed", "list@example.test", "", None, None).await.is_err());
        assert_eq!(db.get_patchset_status(id).await?.as_deref(), Some("Cooldown blocked"));
        assert!(db.cooldown_publication_blocked(id).await?);
        assert!(!db.release_patchset_embargo(id, i64::MAX).await?);
        assert!(!db.claim_patchset_for_review(id).await?);
        assert!(db.insert_email_outbox(1, "Pending", "sink@example.test", "", "review", &msg, "", "result").await.is_err());
        let details = db.get_patchset_details(id, None, None).await?.context("missing details")?;
        assert_eq!(details["status"], "Embargoed");
        assert_eq!(details["reviews"].as_array().context("missing reviews")?.len(), 0);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_legacy_has_no_intent_or_events() -> Result<()> {
        let db = database().await?;
        let (id, _, msg) = seed(&db, "legacy", 1).await?;
        db.create_patch(id, &msg, 1, "diff").await?;
        assert!(db.claim_patchset_for_review(id).await?);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?, 0);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 0);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_restart_preserves_decision_and_release() -> Result<()> {
        let directory = tempfile::tempdir()?;
        let settings = DatabaseSettings { url: directory.path().join("fixture.db").to_string_lossy().into_owned(), token: String::new() };
        let db = Database::new(&settings).await?;
        db.migrate().await?;
        let mut ctx = context("list@example.test", "dev@example.test");
        ctx.policy.burst = 1;
        let active = db.with_cooldown_context(Some(ctx));
        let (first, _, msg) = seed(&active, "restartprior", 1).await?;
        active.create_patch(first, &msg, 1, "diff").await?;
        let (id, _, msg) = seed(&active, "restartheld", 1).await?;
        active.create_patch(id, &msg, 1, "diff").await?;
        let before = scalar(&db, "SELECT MAX(embargo_until) FROM patchsets").await?;
        drop(active); drop(db);
        let reopened = Database::new(&settings).await?;
        reopened.migrate().await?;
        reopened.create_patch(id, &msg, 1, "diff").await?;
        assert_eq!(scalar(&reopened, "SELECT MAX(embargo_until) FROM patchsets").await?, before);
        reopened.release_patchset_embargo(id, 1).await?;
        reopened.set_patchset_embargo_until_if_non_terminal(id, before + 500).await?;
        assert_eq!(scalar(&reopened, "SELECT MAX(embargo_until) FROM patchsets").await?, 1);
        assert_eq!(scalar(&reopened, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
        Ok(())
    }
}
