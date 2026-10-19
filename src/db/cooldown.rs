// Copyright 2026 The Sashiko Authors
// SPDX-License-Identifier: Apache-2.0

//! Transaction-level admission. No external I/O, payload decompression or waits.
use super::*;
use crate::cooldown::{CooldownContext, CooldownPolicy, MAX_SERIES_PARTS, message_key};

const COOLDOWN_OWNER_QUERY: &str =
    "SELECT patchset_id FROM review_cooldown_messages WHERE message_id = ?
UNION ALL
SELECT p.id FROM patchsets p WHERE p.cover_letter_message_id = ?
AND (EXISTS (SELECT 1 FROM review_cooldown_intents WHERE patchset_id = p.id)
 OR EXISTS (SELECT 1 FROM review_cooldown_blocks WHERE patchset_id = p.id))
UNION ALL
SELECT p.patchset_id FROM patches p WHERE p.message_id = ?
AND (EXISTS (SELECT 1 FROM review_cooldown_intents WHERE patchset_id = p.patchset_id)
 OR EXISTS (SELECT 1 FROM review_cooldown_blocks WHERE patchset_id = p.patchset_id))
LIMIT 1";

impl Database {
    pub fn with_cooldown_context(&self, context: Option<CooldownContext>) -> Self {
        let mut handle =
            self.with_bug_actor(&self.bug_actor, &self.bug_tool, self.bug_model.clone());
        handle.cooldown_context = context;
        handle.cooldown_cross_post = false;
        handle
    }

    pub fn with_cooldown_selection(&self, selection: crate::cooldown::CooldownSelection) -> Self {
        match selection {
            crate::cooldown::CooldownSelection::Enabled(context) => {
                self.with_cooldown_context(Some(context))
            }
            crate::cooldown::CooldownSelection::Legacy => self.with_cooldown_context(None),
            crate::cooldown::CooldownSelection::CrossPost => {
                let mut handle = self.with_cooldown_context(None);
                handle.cooldown_cross_post = true;
                handle
            }
        }
    }

    pub(super) fn cooldown_now() -> Result<i64> {
        i64::try_from(
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)?
                .as_secs(),
        )
        .context("adaptive cooldown clock overflow")
    }

    pub(super) async fn cooldown_owner(
        conn: &libsql::Connection,
        message: &str,
    ) -> Result<Option<i64>> {
        // Legacy quarantines may own IDs outside the opt-in grammar. Look them
        // up exactly; creation/accounting still validates with message_key.
        let key = message_key(message).unwrap_or_else(|_| message.to_owned());
        let mut rows = conn
            .query(
                COOLDOWN_OWNER_QUERY,
                libsql::params![key.clone(), key.clone(), key],
            )
            .await?;
        rows.next()
            .await?
            .map(|r| r.get(0))
            .transpose()
            .map_err(Into::into)
    }

    pub(super) async fn block_cooldown(
        conn: &libsql::Connection,
        id: i64,
        reason: &str,
    ) -> Result<()> {
        conn.execute("UPDATE review_cooldown_intents SET state = 'blocked', reason = ? WHERE patchset_id = ?", libsql::params![reason, id]).await?;
        conn.execute("INSERT INTO review_cooldown_blocks(patchset_id, reason) SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM review_cooldown_intents WHERE patchset_id = ?) ON CONFLICT(patchset_id) DO NOTHING", libsql::params![id, reason, id]).await?;
        conn.execute("UPDATE patchsets SET status = 'Cooldown blocked', failed_reason = ? WHERE id = ? AND status != 'Cancelled'", libsql::params![reason, id]).await?;
        Ok(())
    }

    /// Does not enroll existing legacy rows. On a conflict quarantine is committed
    /// before the caller receives the error, so a retry cannot publish old state.
    pub(super) async fn bind_cooldown_message(&self, id: i64, message: &str) -> Result<()> {
        let tx = self.begin_immediate_transaction().await?;
        let mut rows = tx
            .query(
                "SELECT list, author, state FROM review_cooldown_intents WHERE patchset_id = ?",
                libsql::params![id],
            )
            .await?;
        if let Some(row) = rows.next().await? {
            let list: String = row.get(0)?;
            let author: String = row.get(1)?;
            let state: String = row.get(2)?;
            let changed_list = self
                .cooldown_context
                .as_ref()
                .is_some_and(|c| c.list != list && c.author == author);
            if state == "waiting" && (self.cooldown_cross_post || changed_list) {
                // No event exists yet. Restore the single shared legacy policy;
                // retain an explicit exclusion reason without ownership locks.
                tx.execute("INSERT INTO review_cooldown_exclusions(patchset_id, reason, released_at) SELECT patchset_id, 'cross-post', released_at FROM review_cooldown_intents WHERE patchset_id = ? ON CONFLICT(patchset_id) DO NOTHING", libsql::params![id]).await?;
                tx.execute(
                    "DELETE FROM review_cooldown_messages WHERE patchset_id = ?",
                    libsql::params![id],
                )
                .await?;
                tx.execute("DELETE FROM review_cooldown_intents WHERE patchset_id = ? AND state = 'waiting'", libsql::params![id]).await?;
                tx.commit().await?;
                return Ok(());
            }
        }
        let result =
            Self::bind_cooldown_message_tx(&tx, id, message, self.cooldown_context.as_ref()).await;
        match result {
            Ok(()) => tx.commit().await,
            Err(error) => {
                Self::block_cooldown(&tx, id, "conflicting adaptive ingestion context").await?;
                tx.commit().await?;
                Err(error)
            }
        }
    }

    /// Subject display can lose a version when a lower-index unversioned part
    /// arrives. Recover only explicit versions of this owned adaptive revision.
    pub(super) async fn cooldown_canonical_version(
        &self,
        id: i64,
        displayed: Option<u32>,
        frozen: Option<String>,
    ) -> Result<Option<u32>> {
        let Some(frozen) = frozen else {
            return Ok(displayed);
        };
        let (state, version): (String, Option<u32>) = serde_json::from_str(&frozen)?;
        if state == "decided" || version.is_some() {
            return Ok(version.or(displayed));
        }
        if displayed.is_some() {
            return Ok(displayed);
        }
        let mut parts=self.conn.query("SELECT m.cooldown_facts FROM patches p JOIN messages m ON m.message_id = p.message_id WHERE p.patchset_id = ? LIMIT ?",libsql::params![id,MAX_SERIES_PARTS+1]).await?;
        let mut version = None;
        let mut count = 0;
        while let Some(part) = parts.next().await? {
            count += 1;
            if count > MAX_SERIES_PARTS {
                bail!("adaptive series exceeds supported part bound");
            }
            let facts: crate::cooldown::SourceFacts =
                serde_json::from_str(&part.get::<String>(0)?)?;
            if let Some(explicit) = facts.version {
                if version.is_some_and(|old| old != explicit) {
                    bail!("adaptive series has conflicting explicit versions");
                }
                version = Some(explicit);
            }
        }
        Ok(version)
    }

    pub(super) async fn bind_cooldown_message_tx(
        conn: &libsql::Connection,
        id: i64,
        message: &str,
        context: Option<&CooldownContext>,
    ) -> Result<()> {
        Self::bind_cooldown_source_tx(conn, id, message, context, false).await
    }

    async fn bind_cooldown_source_tx(
        conn: &libsql::Connection,
        id: i64,
        message: &str,
        context: Option<&CooldownContext>,
        late_cover: bool,
    ) -> Result<()> {
        let mut rows = conn.query("SELECT list, author, policy, state FROM review_cooldown_intents WHERE patchset_id = ?", libsql::params![id]).await?;
        let Some(row) = rows.next().await? else {
            let mut blocked = conn.query("SELECT 1 FROM review_cooldown_guards WHERE patchset_id = ? AND state != 'decided'", libsql::params![id]).await?;
            if blocked.next().await?.is_some() {
                bail!("canonical series is quarantined");
            }
            return Ok(());
        };
        let list: String = row.get(0)?;
        let author: String = row.get(1)?;
        let policy: CooldownPolicy = serde_json::from_str(&row.get::<String>(2)?)?;
        policy.validate()?;
        let state: String = row.get(3)?;
        if state == "blocked" {
            bail!("adaptive cooldown is quarantined");
        }
        let key = message_key(message)?;
        let mut aliases = conn.query("SELECT patchset_id, source_hash FROM review_cooldown_messages WHERE message_id = ?", libsql::params![key.clone()]).await?;
        let alias = aliases.next().await?;
        let frozen: Option<String> = if let Some(alias) = &alias {
            if alias.get::<i64>(0)? != id {
                bail!("adaptive message belongs to another canonical series");
            }
            alias.get(1)?
        } else {
            if state == "decided" && !late_cover {
                bail!("cannot append to an admitted adaptive revision");
            }
            None
        };
        let mut sources = conn
            .query(
                "SELECT cooldown_source_hash, subject = '(placeholder)' FROM messages WHERE message_id = ?",
                libsql::params![key.clone()],
            )
            .await?;
        let current: Option<String> = match sources.next().await? {
            Some(source) if source.get::<i64>(1)? == 0 => source.get(0)?,
            Some(_) => None,
            None => None,
        };
        if frozen.is_some() && frozen != current {
            bail!("adaptive source changed after ownership was established");
        }
        if let Some(context) = context {
            if context.list != list
                || context.author != author
                || (state != "decided" && context.policy != policy)
            {
                bail!("adaptive scope or policy changed during ingestion");
            }
        } else if state != "decided" || frozen.is_none() {
            bail!("adaptive series requires matching mail policy");
        }
        let incoming = context
            .and_then(|c| c.source_snapshot.as_ref())
            .filter(|source| message_key(&source.message_id).ok().as_ref() == Some(&key));
        let verified = if let Some(incoming) = incoming {
            if current.as_deref() != Some(incoming.fingerprint.as_str()) {
                bail!("mail policy source changed before canonical binding");
            }
            Some(incoming.fingerprint.clone())
        } else if frozen.is_some() {
            frozen
        } else if current.is_none()
            && state == "waiting"
            && context.is_some_and(|c| c.source_snapshot.is_some())
        {
            // Reserve an unseen cover ID. It must acquire its own immutable
            // source snapshot before it can participate in admission.
            None
        } else {
            bail!("adaptive source snapshot is missing");
        };
        conn.execute("INSERT INTO review_cooldown_messages(message_id, patchset_id, source_hash) VALUES (?, ?, ?) ON CONFLICT(message_id) DO UPDATE SET source_hash = COALESCE(review_cooldown_messages.source_hash, excluded.source_hash)", libsql::params![key, id, verified]).await?;
        Ok(())
    }

    /// The canonical matcher establishes this revision's own late cover before
    /// this helper validates and binds its source. It never adds an event.
    pub(super) async fn bind_cooldown_late_cover(&self, id: i64, message: &str) -> Result<()> {
        let tx = self.begin_immediate_transaction().await?;
        let result = async {
            let mut rows = tx.query("SELECT verified_parts FROM review_cooldown_intents WHERE patchset_id = ? AND state = 'decided'", libsql::params![id]).await?;
            if let Some(row) = rows.next().await? {
                let verified: u32 = row.get(0)?;
                let key = message_key(message)?;
                let mut cover = tx.query("SELECT cooldown_facts FROM messages WHERE message_id = ?", libsql::params![key]).await?;
                let facts:crate::cooldown::SourceFacts = serde_json::from_str(&cover.next().await?.context("late cover has no stored source")?.get::<String>(0)?)?;
                if (facts.index,facts.total) != (0, verified) {
                    bail!("late cover contradicts admitted size");
                }
            }
            Self::bind_cooldown_source_tx(&tx, id, message, self.cooldown_context.as_ref(), true).await
        }.await;
        if let Err(error) = result {
            Self::block_cooldown(&tx, id, "conflicting late cover source").await?;
            tx.commit().await?;
            return Err(error);
        }
        tx.commit().await
    }

    pub(super) async fn insert_cooldown_intent(
        &self,
        id: i64,
        message: &str,
        cover: Option<&str>,
    ) -> Result<()> {
        let Some(context) = &self.cooldown_context else {
            return Ok(());
        };
        context.policy.validate()?;
        self.execute("INSERT INTO review_cooldown_intents(patchset_id, list, author, policy, state, created_at) VALUES (?, ?, ?, ?, 'waiting', ?)", libsql::params![id, context.list.clone(), context.author.clone(), serde_json::to_string(&context.policy)?, Self::cooldown_now()?]).await?;
        if let Some(until) = context.legacy_deadline {
            self.execute(
                "UPDATE patchsets SET embargo_until = ? WHERE id = ?",
                libsql::params![until, id],
            )
            .await?;
        }
        Self::bind_cooldown_message_tx(&self.conn, id, message, Some(context)).await?;
        if let Some(cover) = cover {
            Self::bind_cooldown_message_tx(&self.conn, id, cover, Some(context)).await?;
        }
        Ok(())
    }

    /// Runs inside the existing immediate writer transaction. The same operation
    /// handles final-part arrival and a late cover correcting the denominator.
    pub(super) async fn complete_patchset_tx(
        conn: &libsql::Connection,
        id: i64,
        now: i64,
        context: Option<&CooldownContext>,
    ) -> Result<()> {
        let mut rows = conn.query("SELECT c.list, c.author, c.policy, c.state, c.released_at, p.total_parts, p.embargo_until, p.status, p.cover_letter_message_id FROM review_cooldown_intents c JOIN patchsets p ON p.id = c.patchset_id WHERE c.patchset_id = ?", libsql::params![id]).await?;
        if let Some(row) = rows.next().await? {
            let state: String = row.get(3)?;
            if state == "blocked" {
                bail!("adaptive cooldown is quarantined");
            }
            if state == "waiting" {
                let Some(context) = context else {
                    bail!("adaptive admission disabled while intent remains unresolved");
                };
                let list: String = row.get(0)?;
                let author: String = row.get(1)?;
                let policy: CooldownPolicy = serde_json::from_str(&row.get::<String>(2)?)?;
                policy.validate()?;
                if context.list != list || context.author != author || context.policy != policy {
                    bail!("adaptive admission policy changed before completion");
                }
                let released = get_optional_integer(&row, 4)?;
                let total: u32 = row.get(5)?;
                let legacy = get_optional_integer(&row, 6)?;
                let status: String = row.get(7)?;
                if !matches!(status.as_str(), "Incomplete" | "Fetching") {
                    return Ok(());
                }
                if total == 0 || total > MAX_SERIES_PARTS {
                    bail!("adaptive series exceeds supported part bound");
                }
                let mut parts = conn.query("SELECT p.part_index, p.message_id, m.cooldown_facts, c.patchset_id, p.cooldown_content_hash, m.cooldown_body_hash, c.source_hash, m.cooldown_source_hash FROM patches p LEFT JOIN messages m ON m.message_id = p.message_id LEFT JOIN review_cooldown_messages c ON c.message_id = p.message_id WHERE p.patchset_id = ? ORDER BY p.part_index, p.id LIMIT ?", libsql::params![id, MAX_SERIES_PARTS + 1]).await?;
                let mut count = 0;
                let mut verified_version = None;
                while let Some(part) = parts.next().await? {
                    count += 1;
                    let index: u32 = part.get(0)?;
                    let message: String = part.get(1)?;
                    let facts: crate::cooldown::SourceFacts =
                        serde_json::from_str(&part.get::<String>(2)?)?;
                    let owner: Option<i64> = part.get(3)?;
                    let content_hash: Option<String> = part.get(4)?;
                    let body_hash: Option<String> = part.get(5)?;
                    let frozen_source: Option<String> = part.get(6)?;
                    let current_source: Option<String> = part.get(7)?;
                    if let Some(version) = facts.version {
                        if verified_version.is_some_and(|old| old != version) {
                            bail!("adaptive series has conflicting explicit versions");
                        }
                        verified_version = Some(version);
                    }
                    if count > total
                        || index == 0
                        || index > total
                        || facts.author.as_deref() != Some(author.as_str())
                        || facts.index != index
                        || facts.total != total
                        || message_key(&message)? != message
                        || content_hash.is_none()
                        || content_hash != body_hash
                        || frozen_source.is_none()
                        || frozen_source != current_source
                        || owner != Some(id)
                    {
                        bail!("adaptive series has inconsistent parts or ownership");
                    }
                }
                if count < total {
                    return Ok(());
                }
                // A real adopted cover contributes metadata and scope even
                // when a different ingestion has only stored its raw message.
                // Do not promote Pending until its own policy binding finishes.
                if let Some(cover_id) = row.get::<Option<String>>(8)? {
                    let mut cover = conn.query("SELECT m.subject = '(placeholder)', m.cooldown_source_hash, c.source_hash, c.patchset_id, m.cooldown_facts FROM messages m LEFT JOIN review_cooldown_messages c ON c.message_id = m.message_id WHERE m.message_id = ? AND NOT EXISTS (SELECT 1 FROM patches p WHERE p.patchset_id = ? AND p.message_id = m.message_id)",libsql::params![cover_id,id]).await?;
                    if let Some(cover) = cover.next().await?
                        && cover.get::<i64>(0)? == 0
                    {
                        let current: Option<String> = cover.get(1)?;
                        let frozen: Option<String> = cover.get(2)?;
                        let facts: crate::cooldown::SourceFacts =
                            serde_json::from_str(&cover.get::<String>(4)?)?;
                        if current.is_none()
                            || current != frozen
                            || cover.get::<Option<i64>>(3)? != Some(id)
                            || facts.author.as_deref() != Some(author.as_str())
                            || (facts.index, facts.total) != (0, total)
                            || facts
                                .version
                                .zip(verified_version)
                                .is_some_and(|(a, b)| a != b)
                        {
                            bail!("adopted adaptive cover lacks verified policy provenance");
                        }
                    }
                }
                let mut unique = conn
                    .query(
                        "SELECT COUNT(DISTINCT part_index) FROM patches WHERE patchset_id = ?",
                        libsql::params![id],
                    )
                    .await?;
                if unique
                    .next()
                    .await?
                    .context("missing part count")?
                    .get::<u32>(0)?
                    != total
                {
                    bail!("adaptive series has duplicate part indices");
                }
                if now < 0 {
                    bail!("adaptive admission clock is invalid");
                }
                let mut clock = conn
                    .query(
                        "SELECT last_admitted_at FROM review_cooldown_clock WHERE singleton = 1",
                        (),
                    )
                    .await?;
                if clock
                    .next()
                    .await?
                    .context("missing adaptive clock state")?
                    .get::<i64>(0)?
                    > now
                {
                    bail!("adaptive admission clock moved backwards");
                }
                let activation_key = format!("cooldown.history_since:{list}");
                let mut coverage = conn
                    .query(
                        "SELECT value FROM meta WHERE key = ?",
                        libsql::params![activation_key.clone()],
                    )
                    .await?;
                let activation: i64 = if let Some(boundary) = coverage.next().await? {
                    boundary
                        .get::<String>(0)?
                        .parse()
                        .context("invalid cooldown history boundary")?
                } else {
                    let mut existing = conn
                        .query(
                            "SELECT 1 FROM review_cooldown_events WHERE list = ? LIMIT 1",
                            libsql::params![list.clone()],
                        )
                        .await?;
                    if existing.next().await?.is_some() {
                        bail!("cooldown history boundary missing for existing events");
                    }
                    conn.execute(
                        "INSERT INTO meta(key,value) VALUES (?, ?)",
                        libsql::params![activation_key, now.to_string()],
                    )
                    .await?;
                    now
                };
                if activation < 0 || activation > now {
                    bail!("invalid cooldown history coverage");
                }
                let history_since = activation
                    .max(now.saturating_sub(i64::from(crate::cooldown::MAX_WINDOW_SECONDS)));
                let mut latest = conn.query("SELECT admitted_at FROM review_cooldown_events WHERE list = ? AND author = ? ORDER BY admitted_at DESC LIMIT 1", libsql::params![list.clone(), author.clone()]).await?;
                if let Some(latest) = latest.next().await?
                    && latest.get::<i64>(0)? > now
                {
                    bail!("adaptive admission clock moved backwards");
                }
                let mut history = conn.query("SELECT COUNT(*) FROM (SELECT 1 FROM review_cooldown_events INDEXED BY idx_cooldown_history WHERE list = ? AND author = ? AND admitted_at > ? AND admitted_at <= ? ORDER BY admitted_at DESC LIMIT ?)", libsql::params![list.clone(), author.clone(), now.saturating_sub(i64::from(policy.window_seconds)), now, policy.history_limit()?]).await?;
                let prior: u32 = history
                    .next()
                    .await?
                    .context("missing adaptive count")?
                    .get(0)?;
                let extra = policy.extra_seconds(prior)?;
                let deadline = if released.is_some() {
                    legacy
                } else {
                    policy.deadline(now, legacy, prior)?
                };
                conn.execute("INSERT INTO review_cooldown_events(patchset_id, list, author, admitted_at) VALUES (?, ?, ?, ?)", libsql::params![id, list, author, now]).await?;
                conn.execute(
                    "UPDATE patchsets SET embargo_until = ? WHERE id = ?",
                    libsql::params![deadline, id],
                )
                .await?;
                conn.execute("UPDATE review_cooldown_intents SET state = 'decided', admitted_at = ?, prior_count = ?, extra_seconds = ?, decided_deadline = ?, verified_parts = ?, verified_version = ?, history_since = ? WHERE patchset_id = ? AND state = 'waiting'", libsql::params![now, prior, extra, deadline, total, verified_version, history_since, id]).await?;
                conn.execute(
                    "UPDATE review_cooldown_clock SET last_admitted_at = ? WHERE singleton = 1",
                    libsql::params![now],
                )
                .await?;
                // Expensive history never accumulates on the hot counting path.
                // Intent and message ownership remain dedup tombstones. Pruning
                // is indexed and bounded independently of historical volume.
                conn.execute("DELETE FROM review_cooldown_events WHERE patchset_id IN (SELECT patchset_id FROM review_cooldown_events WHERE admitted_at < ? ORDER BY admitted_at LIMIT 16)", libsql::params![now.saturating_sub(i64::from(crate::cooldown::MAX_WINDOW_SECONDS))]).await?;
            }
        }
        conn.execute("UPDATE patchsets SET status = 'Pending' WHERE id = ? AND received_parts >= total_parts AND status IN ('Incomplete', 'Fetching')", libsql::params![id]).await?;
        Ok(())
    }

    pub(super) async fn complete_patchset(&self, id: i64) -> Result<()> {
        let tx = self.begin_immediate_transaction().await?;
        Self::complete_patchset_tx(
            &tx,
            id,
            Self::cooldown_now()?,
            self.cooldown_context.as_ref(),
        )
        .await?;
        tx.commit().await
    }

    pub async fn cooldown_publication_blocked(&self, id: i64) -> Result<bool> {
        let mut rows = self
            .conn
            .query(
                "SELECT 1 FROM review_cooldown_guards WHERE patchset_id = ? AND state != 'decided'",
                libsql::params![id],
            )
            .await?;
        Ok(rows.next().await?.is_some())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    async fn database() -> Result<Database> {
        let db = Database::new(&DatabaseSettings {
            url: ":memory:".into(),
            token: String::new(),
        })
        .await?;
        db.migrate().await?;
        Ok(db)
    }

    fn context(list: &str, author: &str) -> CooldownContext {
        CooldownContext {
            list: list.into(),
            author: author.into(),
            policy: CooldownPolicy {
                window_seconds: 100,
                burst: 2,
                step_seconds: 10,
                max_extra_seconds: 30,
            },
            legacy_deadline: None,
            source_snapshot: None,
        }
    }

    async fn seed(db: &Database, token: &str, total: u32) -> Result<(i64, i64, String)> {
        let author = db
            .cooldown_context
            .as_ref()
            .map_or("dev@example.test", |c| c.author.as_str());
        let message = format!("{token}-1@example.test");
        let subject = format!("[PATCH 1/{total}] {token}");
        let thread = db.create_thread(&message, &subject, 1).await?;
        db.create_message(
            &message,
            thread,
            None,
            author,
            &subject,
            1,
            if total == 1 { "diff" } else { "diff1" },
            "list@example.test",
            "",
            None,
            None,
        )
        .await?;
        let scoped = fixture_source_handle(db, &message).await?;
        let db = &scoped;
        let id = db
            .create_patchset(
                thread,
                Some(&message),
                &message,
                &subject,
                author,
                1,
                total,
                3,
                "list@example.test",
                "",
                None,
                1,
                None,
                true,
                None,
                None,
            )
            .await?
            .context("missing fixture series")?;
        Ok((id, thread, message))
    }

    async fn fixture_source_handle(db: &Database, message: &str) -> Result<Database> {
        let mut context = db.cooldown_context.clone();
        if let Some(context) = &mut context {
            let mut rows = db
                .conn
                .query(
                    "SELECT cooldown_source_hash FROM messages WHERE message_id = ?",
                    libsql::params![message],
                )
                .await?;
            let fingerprint: String = rows
                .next()
                .await?
                .context("missing fixture source")?
                .get(0)?;
            context.source_snapshot = Some(crate::cooldown::SourceSnapshot {
                message_id: message.into(),
                fingerprint,
            });
        }
        Ok(db.with_cooldown_context(context))
    }

    async fn admit_at(db: &Database, id: i64, message: &str, now: i64) -> Result<()> {
        let tx = db.begin_immediate_transaction().await?;
        tx.execute(
            "INSERT INTO patches(patchset_id,message_id,part_index,diff,cooldown_content_hash) VALUES (?, ?, 1, 'diff', ?)",
            libsql::params![id, message, crate::cooldown::content_fingerprint(b"diff")],
        )
        .await?;
        tx.execute(
            "UPDATE patchsets SET received_parts = 1 WHERE id = ?",
            libsql::params![id],
        )
        .await?;
        Database::complete_patchset_tx(&tx, id, now, db.cooldown_context.as_ref()).await?;
        tx.commit().await
    }

    async fn scalar(db: &Database, sql: &str) -> Result<i64> {
        Ok(db
            .conn
            .query(sql, ())
            .await?
            .next()
            .await?
            .context("missing scalar")?
            .get(0)?)
    }

    #[tokio::test]
    async fn test_cooldown_owner_lookup_uses_point_guards() -> Result<()> {
        let db = database().await?;
        let (legacy, _, message) = seed(&db, "owner-legacy", 1).await?;
        assert_eq!(Database::cooldown_owner(&db.conn, &message).await?, None);
        let tx = db.begin_immediate_transaction().await?;
        Database::block_cooldown(&tx, legacy, "owner lookup fixture").await?;
        tx.commit().await?;
        assert_eq!(
            Database::cooldown_owner(&db.conn, &message).await?,
            Some(legacy)
        );
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (adaptive, _, message) = seed(&active, "owner-adaptive", 1).await?;
        assert_eq!(
            Database::cooldown_owner(&db.conn, &message).await?,
            Some(adaptive)
        );
        let sql = format!("EXPLAIN QUERY PLAN {COOLDOWN_OWNER_QUERY}");
        let mut rows = db
            .conn
            .query(
                &sql,
                libsql::params![message.clone(), message.clone(), message],
            )
            .await?;
        let mut plan = String::new();
        while let Some(row) = rows.next().await? {
            plan.push_str(&row.get::<String>(3)?);
            plan.push('\n');
        }
        for table in ["review_cooldown_intents", "review_cooldown_blocks"] {
            assert!(!plan.contains(&format!("SCAN {table}")), "{plan}");
            assert!(
                plan.contains(&format!("SEARCH {table} USING INTEGER PRIMARY KEY")),
                "{plan}"
            );
        }
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_interim_version14_upgrade_preserves_decision() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, _, message) = seed(&active, "interim-upgrade", 1).await?;
        active.create_patch(id, &message, 1, "diff").await?;
        db.execute_batch("DROP INDEX idx_patchsets_held_series; PRAGMA user_version = 14;")
            .await?;
        db.migrate().await?;
        assert_eq!(scalar(&db, "PRAGMA user_version").await?, 15);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name='idx_patchsets_held_series'").await?,
            1
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        db.create_patch(id, &message, 1, "diff").await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_hand_trace_scope_and_window() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        // Independent oracle: burst=2, step=10, cap=30; window excludes t-100.
        for (token, now, prior, extra) in [
            ("a", 1000, 0, 0),
            ("b", 1001, 1, 0),
            ("c", 1002, 2, 10),
            ("d", 1003, 3, 20),
            ("e", 1004, 4, 30),
            ("f", 1005, 4, 30),
            ("g", 1105, 0, 0),
        ] {
            let (id, _, message) = seed(&active, token, 1).await?;
            admit_at(&active, id, &message, now).await?;
            let mut rows = db.conn.query("SELECT prior_count, extra_seconds, admitted_at, embargo_until FROM review_cooldown_intents c JOIN patchsets p ON p.id = c.patchset_id WHERE p.id = ?", libsql::params![id]).await?;
            let row = rows.next().await?.context("missing decision")?;
            assert_eq!(row.get::<u32>(0)?, prior);
            assert_eq!(row.get::<u32>(1)?, extra);
            assert_eq!(row.get::<i64>(2)?, now);
            assert_eq!(
                row.get::<Option<i64>>(3)?,
                (extra > 0).then_some(now + i64::from(extra))
            );
        }
        let other_list =
            db.with_cooldown_context(Some(context("other@example.test", "dev@example.test")));
        let (id, _, message) = seed(&other_list, "separate", 1).await?;
        admit_at(&other_list, id, &message, 1105).await?;
        assert_eq!(
            scalar(
                &db,
                "SELECT prior_count FROM review_cooldown_intents WHERE list = 'other@example.test'"
            )
            .await?,
            0
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_incomplete_out_of_order_and_duplicate() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, thread, first) = seed(&active, "multipart", 2).await?;
        assert!(!db.claim_patchset_for_review(id).await?);
        assert!(db.update_patchset_status(id, "Pending").await.is_err());
        let second = "multipart-2@example.test";
        active
            .create_message(
                second,
                thread,
                Some(&first),
                "DEV@EXAMPLE.TEST",
                "[PATCH 2/2] second",
                1,
                "diff2",
                "list@example.test",
                "",
                None,
                None,
            )
            .await?;
        fixture_source_handle(&active, second)
            .await?
            .bind_cooldown_message(id, second)
            .await?;
        active.create_patch(id, second, 2, "diff2").await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            0
        );
        assert_eq!(
            db.get_patchset_status(id).await?.as_deref(),
            Some("Incomplete")
        );
        active.create_patch(id, &first, 1, "diff1").await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        active.create_patch(id, &first, 1, "diff1").await?;
        // Replay without opt-in context (configuration removed after admission).
        db.create_patch(id, second, 2, "diff2").await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
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
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM patchsets WHERE embargo_until IS NOT NULL"
            )
            .await?,
            0
        );
        db.set_patchset_embargo_until(id, 9999).await?;
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM patchsets WHERE embargo_until IS NOT NULL"
            )
            .await?,
            0
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_history_failure_rolls_back_and_retries() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, _, msg) = seed(&active, "retry", 1).await?;
        db.execute_batch("CREATE TRIGGER fail_cooldown_event BEFORE INSERT ON review_cooldown_events BEGIN SELECT RAISE(ABORT, 'fixture failure'); END;").await?;
        assert!(active.create_patch(id, &msg, 1, "diff").await.is_err());
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 0);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            0
        );
        assert_eq!(
            db.get_patchset_status(id).await?.as_deref(),
            Some("Incomplete")
        );
        db.execute_batch("DROP TRIGGER fail_cooldown_event;")
            .await?;
        active.create_patch(id, &msg, 1, "diff").await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_source_correction_quarantine_survives_expiry() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, thread, msg) = seed(&active, "immutable", 1).await?;
        active.create_patch(id, &msg, 1, "diff").await?;
        assert!(
            db.create_message(
                &msg,
                thread,
                None,
                "victim@example.test",
                "[PATCH] altered",
                1,
                "changed",
                "list@example.test",
                "",
                None,
                None
            )
            .await
            .is_err()
        );
        assert_eq!(
            db.get_patchset_status(id).await?.as_deref(),
            Some("Cooldown blocked")
        );
        assert!(db.cooldown_publication_blocked(id).await?);
        assert!(!db.release_patchset_embargo(id, i64::MAX).await?);
        assert!(!db.claim_patchset_for_review(id).await?);
        assert!(
            db.insert_email_outbox(
                1,
                "Pending",
                "sink@example.test",
                "",
                "review",
                &msg,
                "",
                "result"
            )
            .await
            .is_err()
        );
        let details = db
            .get_patchset_details(id, None, None)
            .await?
            .context("missing details")?;
        assert_eq!(details["status"], "Embargoed");
        assert_eq!(
            details["reviews"]
                .as_array()
                .context("missing reviews")?
                .len(),
            0
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_legacy_has_no_intent_or_events() -> Result<()> {
        let db = database().await?;
        let (id, _, msg) = seed(&db, "legacy", 1).await?;
        db.create_patch(id, &msg, 1, "diff").await?;
        assert!(db.claim_patchset_for_review(id).await?);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?,
            0
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            0
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_restart_preserves_decision_and_release() -> Result<()> {
        let directory = tempfile::tempdir()?;
        let settings = DatabaseSettings {
            url: directory
                .path()
                .join("fixture.db")
                .to_string_lossy()
                .into_owned(),
            token: String::new(),
        };
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
        drop(active);
        drop(db);
        let reopened = Database::new(&settings).await?;
        reopened.migrate().await?;
        reopened.create_patch(id, &msg, 1, "diff").await?;
        assert_eq!(
            scalar(&reopened, "SELECT MAX(embargo_until) FROM patchsets").await?,
            before
        );
        reopened.release_patchset_embargo(id, 1).await?;
        reopened
            .set_patchset_embargo_until_if_non_terminal(id, before + 500)
            .await?;
        assert_eq!(
            scalar(&reopened, "SELECT MAX(embargo_until) FROM patchsets").await?,
            1
        );
        assert_eq!(
            scalar(&reopened, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            2
        );
        Ok(())
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn test_cooldown_two_connections_own_opposite_parts_once() -> Result<()> {
        let directory = tempfile::tempdir()?;
        let settings = DatabaseSettings {
            url: directory
                .path()
                .join("race.db")
                .to_string_lossy()
                .into_owned(),
            token: String::new(),
        };
        let first = Database::new(&settings).await?;
        first.migrate().await?;
        let second = Database::new(&settings).await?;
        let first =
            first.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let second =
            second.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let thread = first
            .create_thread("race-cover@example.test", "race", 1)
            .await?;
        first
            .create_message(
                "race-cover@example.test",
                thread,
                None,
                "unknown",
                "(placeholder)",
                1,
                "",
                "",
                "",
                None,
                None,
            )
            .await?;
        for index in [1, 2] {
            first
                .create_message(
                    &format!("race-{index}@example.test"),
                    thread,
                    Some("race-cover@example.test"),
                    "dev@example.test",
                    &format!("[PATCH {index}/2] race {index}"),
                    1,
                    "diff",
                    "list@example.test",
                    "",
                    None,
                    None,
                )
                .await?;
        }
        let barrier = Arc::new(tokio::sync::Barrier::new(2));
        let mut tasks = Vec::new();
        for (db, index) in [(first, 1), (second, 2)] {
            let barrier = barrier.clone();
            tasks.push(tokio::spawn(async move {
                barrier.wait().await;
                let message = format!("race-{index}@example.test");
                let db = fixture_source_handle(&db, &message).await?;
                let id = db
                    .create_patchset(
                        thread,
                        Some("race-cover@example.test"),
                        &message,
                        &format!("[PATCH {index}/2] race {index}"),
                        "dev@example.test",
                        1,
                        2,
                        3,
                        "list@example.test",
                        "",
                        None,
                        index,
                        None,
                        true,
                        None,
                        None,
                    )
                    .await?
                    .context("missing race owner")?;
                db.create_patch(id, &message, index, "diff")
                    .await
                    .context("racing patch persistence")?;
                Ok::<i64, anyhow::Error>(id)
            }));
        }
        let a =
            tokio::time::timeout(std::time::Duration::from_secs(15), tasks.remove(0)).await???;
        let b =
            tokio::time::timeout(std::time::Duration::from_secs(15), tasks.remove(0)).await???;
        assert_eq!(a, b);
        let reopened = Database::new(&settings).await?;
        assert_eq!(
            scalar(&reopened, "SELECT COUNT(*) FROM patchsets").await?,
            1
        );
        assert_eq!(scalar(&reopened, "SELECT COUNT(*) FROM patches").await?, 2);
        assert_eq!(
            scalar(&reopened, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        assert_eq!(
            scalar(&reopened, "SELECT COUNT(*) FROM review_cooldown_messages").await?,
            3
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_crosspost_before_admission_is_legacy() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, thread, first) = seed(&active, "crosspost", 2).await?;
        active.create_patch(id, &first, 1, "diff1").await?;
        let other =
            db.with_cooldown_context(Some(context("other@example.test", "dev@example.test")));
        let second = "crosspost-2@example.test";
        other
            .create_message(
                second,
                thread,
                Some(&first),
                "dev@example.test",
                "[PATCH 2/2] second",
                1,
                "diff2",
                "other@example.test",
                "",
                None,
                None,
            )
            .await?;
        fixture_source_handle(&other, second)
            .await?
            .bind_cooldown_message(id, second)
            .await?;
        other.create_patch(id, second, 2, "diff2").await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            0
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?,
            0
        );
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM review_cooldown_exclusions WHERE reason = 'cross-post'"
            )
            .await?,
            1
        );
        assert!(db.claim_patchset_for_review(id).await?);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_owned_content_cannot_change_without_context() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, _, msg) = seed(&active, "immutablepatch", 1).await?;
        active.create_patch(id, &msg, 1, "diff").await?;
        assert!(
            db.create_patch(id, &msg, 1, "different diff")
                .await
                .is_err()
        );
        assert!(db.cooldown_publication_blocked(id).await?);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM patches WHERE diff = 'diff'").await?,
            1
        );
        assert!(db.update_patchset_status(id, "Pending").await.is_err());
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_live_claims_and_null_patch_notification() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, _, msg) = seed(&active, "claimed", 1).await?;
        let patch = active.create_patch(id, &msg, 1, "diff").await?;
        db.insert_email_outbox(
            patch,
            "Pending",
            "sink@example.test",
            "",
            "review",
            &msg,
            "",
            "result",
        )
        .await?;
        db.insert_patchwork_notification(
            "Pending",
            "sink@example.test",
            "patchwork",
            &format!("<{msg}>"),
            "",
            "result",
        )
        .await?;
        let tx = db.begin_immediate_transaction().await?;
        Database::block_cooldown(&tx, id, "fixture race after enqueue").await?;
        tx.commit().await?;
        assert!(db.lock_pending_email().await?.is_none());
        assert!(
            db.insert_patchwork_notification(
                "Pending",
                "other@example.test",
                "new patchwork",
                &format!("<{msg}>"),
                "",
                "result"
            )
            .await
            .is_err()
        );
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM email_outbox WHERE status = 'Sending'"
            )
            .await?,
            0
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_policy_reload_preserves_decided_but_blocks_waiting() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (decided, _, msg) = seed(&active, "decidedreload", 1).await?;
        active.create_patch(decided, &msg, 1, "diff").await?;
        let mut changed = context("list@example.test", "dev@example.test");
        changed.policy.step_seconds = 15;
        let reloaded = db.with_cooldown_context(Some(changed));
        reloaded.bind_cooldown_message(decided, &msg).await?;
        reloaded.create_patch(decided, &msg, 1, "diff").await?;
        assert!(!db.cooldown_publication_blocked(decided).await?);
        let (waiting, _, msg) = seed(&active, "waitingreload", 1).await?;
        db.execute_batch("CREATE TRIGGER fail_cooldown_event BEFORE INSERT ON review_cooldown_events BEGIN SELECT RAISE(ABORT, 'fixture failure'); END;").await?;
        assert!(active.create_patch(waiting, &msg, 1, "diff").await.is_err());
        db.execute_batch("DROP TRIGGER fail_cooldown_event;")
            .await?;
        assert!(db.create_patch(waiting, &msg, 1, "diff").await.is_err());
        assert_eq!(
            db.get_patchset_status(waiting).await?.as_deref(),
            Some("Cooldown blocked")
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_crosspost_preserves_early_release() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, _, msg) = seed(&active, "crossrelease", 1).await?;
        assert!(db.release_patchset_embargo(id, 1).await?);
        let cross = db.with_cooldown_selection(crate::cooldown::CooldownSelection::CrossPost);
        cross.bind_cooldown_message(id, &msg).await?;
        db.set_patchset_embargo_until_if_non_terminal(id, i64::MAX)
            .await?;
        db.create_patch(id, &msg, 1, "diff").await?;
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM patchsets WHERE embargo_until IS NOT NULL"
            )
            .await?,
            0
        );
        assert_eq!(
            scalar(&db, "SELECT released_at FROM review_cooldown_exclusions").await?,
            1
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_legacy_quarantine_is_durable_and_cancellable() -> Result<()> {
        let directory = tempfile::tempdir()?;
        let settings = DatabaseSettings {
            url: directory
                .path()
                .join("legacy-block.db")
                .to_string_lossy()
                .into_owned(),
            token: String::new(),
        };
        let db = Database::new(&settings).await?;
        db.migrate().await?;
        let (id, thread, msg) = seed(&db, "legacyblock", 1).await?;
        let patch = db.create_patch(id, &msg, 1, "diff").await?;
        db.insert_email_outbox(
            patch,
            "Pending",
            "sink@example.test",
            "",
            "ordinary",
            &msg,
            "",
            "body",
        )
        .await?;
        db.insert_patchwork_notification(
            "Pending",
            "sink@example.test",
            "patchwork",
            &format!("<{msg}>"),
            "",
            "body",
        )
        .await?;
        let tx = db.begin_immediate_transaction().await?;
        Database::block_cooldown(&tx, id, "mixed merge fixture").await?;
        tx.commit().await?;
        drop(db);
        let db = Database::new(&settings).await?;
        assert!(!db.claim_patchset_for_review(id).await?);
        assert!(db.update_patchset_status(id, "Pending").await.is_err());
        assert!(db.lock_pending_email().await?.is_none());
        assert!(db.cancel_patchset(id, false).await?);
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM email_outbox WHERE status = 'Cancelled'"
            )
            .await?,
            2
        );
        assert!(
            db.create_message(
                &msg,
                thread,
                None,
                "victim@example.test",
                "changed",
                1,
                "changed",
                "list@example.test",
                "",
                None,
                None
            )
            .await
            .is_err()
        );
        assert_eq!(
            db.get_patchset_status(id).await?.as_deref(),
            Some("Cancelled")
        );
        assert!(db.lock_pending_email().await?.is_none());
        Ok(())
    }
    #[allow(clippy::too_many_arguments)]
    async fn mail_part(
        db: &Database,
        thread: i64,
        cover: &str,
        message: &str,
        subject: &str,
        author: &str,
        index: u32,
        total: u32,
    ) -> Result<i64> {
        if message != cover && db.get_message_id_by_msg_id(cover).await?.is_none() {
            db.create_message(
                cover,
                thread,
                None,
                "unknown",
                "(placeholder)",
                1,
                "",
                "",
                "",
                None,
                None,
            )
            .await?;
        }
        db.create_message(
            message,
            thread,
            Some(cover),
            author,
            subject,
            1,
            "diff",
            "list@example.test",
            "",
            None,
            None,
        )
        .await?;
        let handle = fixture_source_handle(db, message).await?;
        let id = handle
            .create_patchset(
                thread,
                Some(cover),
                message,
                subject,
                author,
                1,
                total,
                3,
                "list@example.test",
                "",
                crate::patch::parse_subject_version(subject),
                index,
                None,
                true,
                None,
                None,
            )
            .await?
            .context("missing mail owner")?;
        if index > 0 {
            handle.create_patch(id, message, index, "diff").await?;
        }
        Ok(id)
    }

    #[tokio::test]
    async fn test_cooldown_real_versions_and_late_cover_remain_separate() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let root = "versions-cover@example.test";
        let thread = db.create_thread(root, "versions", 1).await?;
        let v1 = mail_part(
            &active,
            thread,
            root,
            "versions-v1-1@example.test",
            "[PATCH v1 1/2] first",
            "dev@example.test",
            1,
            2,
        )
        .await?;
        assert_eq!(
            mail_part(
                &active,
                thread,
                root,
                "versions-v1-2@example.test",
                "[PATCH v1 2/2] second",
                "dev@example.test",
                2,
                2
            )
            .await?,
            v1
        );
        let v2 = mail_part(
            &active,
            thread,
            root,
            "versions-v2-1@example.test",
            "[PATCH v2 1/2] first",
            "dev@example.test",
            1,
            2,
        )
        .await?;
        assert_ne!(v1, v2);
        assert_eq!(
            mail_part(
                &active,
                thread,
                root,
                "versions-v2-2@example.test",
                "[PATCH v2 2/2] second",
                "dev@example.test",
                2,
                2
            )
            .await?,
            v2
        );
        assert_eq!(
            mail_part(
                &active,
                thread,
                root,
                root,
                "[PATCH v1 0/2] series",
                "dev@example.test",
                0,
                2
            )
            .await?,
            v1
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            2
        );
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM review_cooldown_intents WHERE state = 'blocked'"
            )
            .await?,
            0
        );
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 4);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_policy_source_race_cannot_bind_changed_recipients() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let msg = "source-race@example.test";
        let thread = db.create_thread(msg, "race", 1).await?;
        db.create_message(
            msg,
            thread,
            None,
            "dev@example.test",
            "[PATCH 1/1] race",
            1,
            "diff",
            "list@example.test",
            "",
            None,
            None,
        )
        .await?;
        let stale = fixture_source_handle(&active, msg).await?;
        // Another unowned ingestion wins before canonical binding.
        db.create_message(
            msg,
            thread,
            None,
            "dev@example.test",
            "[PATCH 1/1] race",
            1,
            "diff",
            "other@example.test",
            "",
            None,
            None,
        )
        .await?;
        assert!(
            stale
                .create_patchset(
                    thread,
                    Some(msg),
                    msg,
                    "[PATCH 1/1] race",
                    "dev@example.test",
                    1,
                    1,
                    3,
                    "list@example.test",
                    "",
                    None,
                    1,
                    None,
                    true,
                    None,
                    None
                )
                .await
                .is_err()
        );
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets").await?, 0);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            0
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_mixed_canonical_merge_blocks_before_moving_rows() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let root = "merge-cover@example.test";
        let thread = db.create_thread(root, "merge", 1).await?;
        let a = mail_part(
            &active,
            thread,
            "merge-first@example.test",
            "merge-first@example.test",
            "[PATCH 1/2] first",
            "dev@example.test",
            1,
            2,
        )
        .await?;
        // Reproduce two existing canonical owners from legacy ingestion.
        db.create_message(
            "merge-second@example.test",
            thread,
            Some(root),
            "dev@example.test",
            "[PATCH 2/2] second",
            1,
            "diff",
            "list@example.test",
            "",
            None,
            None,
        )
        .await?;
        let b = db.query_returning_i64("INSERT INTO patchsets(thread_id,cover_letter_message_id,subject,author,date,total_parts,received_parts,status,subject_index) VALUES (?, 'merge-second@example.test', '[PATCH 2/2] second', 'dev@example.test', 1, 2, 0, 'Incomplete', 2) RETURNING id",libsql::params![thread]).await?.context("missing legacy owner")?;
        db.create_patch(b, "merge-second@example.test", 2, "diff")
            .await?;
        assert!(
            mail_part(
                &active,
                thread,
                root,
                root,
                "[PATCH 0/2] merge",
                "dev@example.test",
                0,
                2
            )
            .await
            .is_err()
        );
        assert!(db.cooldown_publication_blocked(a).await?);
        assert!(db.cooldown_publication_blocked(b).await?);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 2);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets").await?, 2);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            0
        );
        assert!(db.cancel_patchset(a, false).await?);
        assert!(db.cancel_patchset(b, false).await?);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_coverage_and_backward_clock_fail_closed() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (a, _, msg) = seed(&active, "clock-first", 1).await?;
        admit_at(&active, a, &msg, 1000).await?;
        assert_eq!(
            db.get_meta("cooldown.history_since:list@example.test")
                .await?
                .as_deref(),
            Some("1000")
        );
        assert_eq!(
            scalar(
                &db,
                "SELECT history_since FROM review_cooldown_intents WHERE admitted_at = 1000"
            )
            .await?,
            1000
        );
        let (b, _, msg) = seed(&active, "clock-backward", 1).await?;
        assert!(admit_at(&active, b, &msg, 999).await.is_err());
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 1);
        admit_at(&active, b, &msg, 1001).await?;
        let (c, _, msg) = seed(&active, "clock-corrupt", 1).await?;
        db.set_meta("cooldown.history_since:list@example.test", "bad")
            .await?;
        assert!(admit_at(&active, c, &msg, 1002).await.is_err());
        db.execute(
            "DELETE FROM meta WHERE key = 'cooldown.history_since:list@example.test'",
            (),
        )
        .await?;
        assert!(admit_at(&active, c, &msg, 1002).await.is_err());

        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            2
        );
        Ok(())
    }
    #[tokio::test]
    async fn test_cooldown_same_version_extension_cannot_escape_frozen_owner() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let root = "frozen-cover@example.test";
        let thread = db.create_thread(root, "frozen", 1).await?;
        let a = mail_part(
            &active,
            thread,
            root,
            "frozen-1@example.test",
            "[PATCH v1 1/2] first",
            "dev@example.test",
            1,
            2,
        )
        .await?;
        mail_part(
            &active,
            thread,
            root,
            "frozen-2@example.test",
            "[PATCH v1 2/2] second",
            "dev@example.test",
            2,
            2,
        )
        .await?;
        assert!(
            mail_part(
                &active,
                thread,
                root,
                "frozen-new@example.test",
                "[PATCH v1 1/2] replacement",
                "dev@example.test",
                1,
                2
            )
            .await
            .is_err()
        );
        assert!(db.cooldown_publication_blocked(a).await?);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets").await?, 1);
        Ok(())
    }
    #[tokio::test]
    async fn test_cooldown_late_cover_recovers_explicit_part_version() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let root = "late-version-cover@example.test";
        let thread = db.create_thread(root, "late version", 1).await?;
        let a = mail_part(
            &active,
            thread,
            root,
            "late-version-2@example.test",
            "[PATCH v2 2/2] second",
            "dev@example.test",
            2,
            2,
        )
        .await?;
        assert_eq!(
            mail_part(
                &active,
                thread,
                root,
                "late-version-1@example.test",
                "[PATCH 1/2] first",
                "dev@example.test",
                1,
                2
            )
            .await?,
            a
        );
        assert!(db.claim_patchset_for_review(a).await?);
        assert_eq!(
            mail_part(
                &active,
                thread,
                root,
                root,
                "[PATCH v2 0/2] series",
                "dev@example.test",
                0,
                2
            )
            .await?,
            a
        );
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets").await?, 1);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        assert!(!db.cooldown_publication_blocked(a).await?);
        Ok(())
    }
    async fn completed_fixture(db: &Database, id: i64, findings: bool) -> Result<()> {
        let mut rows = db
            .conn
            .query(
                "SELECT id FROM patches WHERE patchset_id = ?",
                libsql::params![id],
            )
            .await?;
        let patch: i64 = rows
            .next()
            .await?
            .context("missing fixture patch")?
            .get(0)?;
        let review = db
            .create_review(id, Some(patch), "fixture", "no-model", None, None)
            .await?;
        db.complete_review(
            review,
            "Reviewed",
            "completed",
            Some("result"),
            None,
            None,
            None,
        )
        .await?;
        if findings {
            db.create_finding(Finding {
                review_id: review,
                severity: Severity::High,
                severity_explanation: None,
                problem: "fixture finding".into(),
                preexisting: Some(false),
                locations: None,
            })
            .await?;
        }
        db.update_patch_status(patch, "Reviewed").await?;
        db.update_patchset_status(id, "Reviewed").await?;
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_deadline_boundary_clean_exception_and_isolation() -> Result<()> {
        let db = database().await?;
        let mut ctx = context("list@example.test", "dev@example.test");
        ctx.policy.burst = 1;
        let active = db.with_cooldown_context(Some(ctx));
        let (a, _, msg) = seed(&active, "boundary-prior", 1).await?;
        admit_at(&active, a, &msg, 1000).await?;
        let (held, _, msg) = seed(&active, "boundary-held", 1).await?;
        admit_at(&active, held, &msg, 1001).await?;
        completed_fixture(&db, held, true).await?;
        assert!(
            !db.get_releasable_embargoed_patchsets(1010, 100)
                .await?
                .iter()
                .any(|p| p.id == held)
        );
        assert!(!db.claim_patchset_embargo_release(held, 1010).await?);
        assert!(
            db.get_releasable_embargoed_patchsets(1011, 100)
                .await?
                .iter()
                .any(|p| p.id == held)
        );
        assert!(db.claim_patchset_embargo_release(held, 1011).await?);
        let (clean, _, msg) = seed(&active, "boundary-clean", 1).await?;
        admit_at(&active, clean, &msg, 1002).await?;
        completed_fixture(&db, clean, false).await?;
        assert!(
            db.get_releasable_embargoed_patchsets(1002, 100)
                .await?
                .iter()
                .any(|p| p.id == clean)
        );
        let other =
            db.with_cooldown_context(Some(context("list@example.test", "other@example.test")));
        let (id, _, msg) = seed(&other, "other-author", 1).await?;
        admit_at(&other, id, &msg, 1003).await?;
        assert_eq!(scalar(&db,"SELECT prior_count FROM review_cooldown_intents WHERE author = 'other@example.test'").await?,0);
        // Later admissions cannot move the already committed held decision.
        assert_eq!(
            scalar(
                &db,
                "SELECT embargo_until FROM patchsets WHERE subject LIKE '%boundary-held%'"
            )
            .await?,
            1011
        );
        Ok(())
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 4)]
    async fn test_cooldown_distinct_connections_serialize_author_history() -> Result<()> {
        let directory = tempfile::tempdir()?;
        let settings = DatabaseSettings {
            url: directory
                .path()
                .join("distinct.db")
                .to_string_lossy()
                .into_owned(),
            token: String::new(),
        };
        let first = Database::new(&settings).await?;
        first.migrate().await?;
        let second = Database::new(&settings).await?;
        let first =
            first.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let second =
            second.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (a, _, a_msg) = seed(&first, "distinct-first", 1).await?;
        let (b, _, b_msg) = seed(&second, "distinct-second", 1).await?;
        let barrier = Arc::new(tokio::sync::Barrier::new(2));
        let mut tasks = Vec::new();
        for (db, id, msg) in [(first, a, a_msg), (second, b, b_msg)] {
            let barrier = barrier.clone();
            tasks.push(tokio::spawn(async move {
                barrier.wait().await;
                admit_at(&db, id, &msg, 1000).await
            }));
        }
        for task in tasks {
            tokio::time::timeout(std::time::Duration::from_secs(15), task).await???;
        }
        let db = Database::new(&settings).await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            2
        );
        assert_eq!(
            scalar(&db, "SELECT MIN(prior_count) FROM review_cooldown_intents").await?,
            0
        );
        assert_eq!(
            scalar(&db, "SELECT MAX(prior_count) FROM review_cooldown_intents").await?,
            1
        );
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(DISTINCT prior_count) FROM review_cooldown_intents"
            )
            .await?,
            2
        );
        Ok(())
    }
    async fn main_style_part(
        db: &Database,
        thread: i64,
        root: &str,
        message: &str,
        index: u32,
    ) -> Result<i64> {
        let subject = format!("[PATCH {index}/2] item");
        db.create_message(
            message,
            thread,
            Some(root),
            "dev@example.test",
            &subject,
            1,
            "diff",
            "list@example.test",
            "",
            None,
            None,
        )
        .await?;
        let handle = fixture_source_handle(db, message).await?;
        let cover = if db
            .message_is_cover_letter_for(root, "dev@example.test", 2, None)
            .await?
        {
            root
        } else {
            message
        };
        let owner = handle
            .create_patchset(
                thread,
                Some(cover),
                message,
                &subject,
                "dev@example.test",
                1,
                2,
                3,
                "list@example.test",
                "",
                None,
                index,
                None,
                true,
                None,
                None,
            )
            .await?
            .context("missing main-style owner")?;
        handle.create_patch(owner, message, index, "diff").await?;
        Ok(owner)
    }

    #[tokio::test]
    async fn test_cooldown_unbound_adopted_cover_cannot_admit() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let root = "unbound-cover@example.test";
        let thread = db.ensure_thread_for_message(root, 1).await?;
        let owner = main_style_part(&active, thread, root, "unbound-first@example.test", 1).await?;
        // Reproduce another ingestion stopping after storing the raw cover.
        db.create_message(
            root,
            thread,
            None,
            "dev@example.test",
            "[PATCH 0/2] item",
            1,
            "cover",
            "other@example.test",
            "",
            None,
            None,
        )
        .await?;
        assert!(
            main_style_part(&active, thread, root, "unbound-second@example.test", 2)
                .await
                .is_err()
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            0
        );
        assert_eq!(
            scalar(
                &db,
                "SELECT COUNT(*) FROM patchsets WHERE status = 'Pending'"
            )
            .await?,
            0
        );
        assert!(db.cooldown_publication_blocked(owner).await?);
        assert!(!db.claim_patchset_for_review(owner).await?);
        Ok(())
    }

    #[tokio::test]
    async fn test_cooldown_large_source_metadata_is_compact_during_admission() -> Result<()> {
        let db = database().await?;
        let active =
            db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let subject = format!("[PATCH 1/1] {}", "x".repeat(1024 * 1024));
        let msg = "large-header@example.test";
        let thread = db.create_thread(msg, &subject, 1).await?;
        active
            .create_message(
                msg,
                thread,
                None,
                "dev@example.test",
                &subject,
                1,
                "diff",
                "list@example.test",
                "",
                None,
                None,
            )
            .await?;
        let handle = fixture_source_handle(&active, msg).await?;
        let owner = handle
            .create_patchset(
                thread,
                Some(msg),
                msg,
                &subject,
                "dev@example.test",
                1,
                1,
                3,
                "list@example.test",
                "",
                None,
                1,
                None,
                true,
                None,
                None,
            )
            .await?
            .context("missing large-header owner")?;
        handle.create_patch(owner, msg, 1, "diff").await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        assert!(scalar(&db, "SELECT MAX(length(cooldown_facts)) FROM messages").await? < 512);
        Ok(())
    }
    #[tokio::test]
    async fn test_cooldown_seeded_restart_replay_trace() -> Result<()> {
        for seed_value in [1_u64, 42, 7331] {
            let directory = tempfile::tempdir()?;
            let settings = DatabaseSettings {
                url: directory
                    .path()
                    .join("trace.db")
                    .to_string_lossy()
                    .into_owned(),
                token: String::new(),
            };
            let mut db = Database::new(&settings).await?;
            db.migrate().await?;
            let mut rng = fastrand::Rng::with_seed(seed_value);
            let mut events: Vec<(String, String, i64)> = Vec::new();
            let mut now = 1000_i64;
            for iteration in 0..96 {
                now += rng.i64(0..=5);
                let list = format!("list{}@example.test", rng.u32(0..2));
                let author = format!("dev{}@example.test", rng.u32(0..3));
                let prior = events
                    .iter()
                    .filter(|(l, a, t)| *l == list && *a == author && *t > now - 100 && *t <= now)
                    .count()
                    .min(4) as u32;
                // Independent small-state oracle, separate from the calculator.
                let extra = match prior {
                    0 | 1 => 0,
                    2 => 10,
                    3 => 20,
                    _ => 30,
                };
                let expected = (extra > 0).then_some(now + extra);
                let active = db.with_cooldown_context(Some(context(&list, &author)));
                let (id, _, msg) =
                    seed(&active, &format!("trace-{seed_value}-{iteration}"), 1).await?;
                admit_at(&active, id, &msg, now).await?;
                let mut decision=db.conn.query("SELECT prior_count,extra_seconds,decided_deadline FROM review_cooldown_intents WHERE patchset_id = ?",libsql::params![id]).await?;
                let row = decision
                    .next()
                    .await?
                    .context("missing generated decision")?;
                assert_eq!(
                    row.get::<u32>(0)?,
                    prior,
                    "seed {seed_value}, event {iteration}"
                );
                assert_eq!(
                    row.get::<i64>(1)?,
                    extra,
                    "seed {seed_value}, event {iteration}"
                );
                assert_eq!(
                    row.get::<Option<i64>>(2)?,
                    expected,
                    "seed {seed_value}, event {iteration}"
                );
                drop(decision);
                drop(active);
                events.push((list, author, now));
                if iteration % 8 == 0 {
                    drop(db);
                    db = Database::new(&settings).await?;
                    db.migrate().await?;
                }
                if extra > 0 && iteration % 10 == 0 {
                    assert!(db.release_patchset_embargo(id, now).await?);
                }
                let snapshot_sql = "SELECT json_array(c.admitted_at,c.prior_count,c.extra_seconds,c.decided_deadline,c.released_at,p.embargo_until) FROM review_cooldown_intents c JOIN patchsets p ON p.id = c.patchset_id WHERE c.patchset_id = ?";
                let before: String = db
                    .conn
                    .query(snapshot_sql, libsql::params![id])
                    .await?
                    .next()
                    .await?
                    .context("missing replay snapshot")?
                    .get(0)?;
                // Context-free replay after disable or a reconstructed process.
                db.create_patch(id, &msg, 1, "diff").await?;
                let after: String = db
                    .conn
                    .query(snapshot_sql, libsql::params![id])
                    .await?
                    .next()
                    .await?
                    .context("missing replay snapshot")?
                    .get(0)?;
                assert_eq!(before, after, "seed {seed_value}, replay {iteration}");
                assert_eq!(
                    scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
                    i64::from(iteration + 1)
                );
            }
        }
        Ok(())
    }
}
