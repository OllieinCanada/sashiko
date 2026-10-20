// Copyright 2026 The Sashiko Authors
// SPDX-License-Identifier: Apache-2.0

//! Bounded writer transactions with atomic visibility of canonical conflicts.
use super::*;

const CONFLICT_BATCH: usize = 64;
const CONFLICT_LEASE_SECONDS: i64 = 3600;

#[derive(Clone, Copy)]
pub(super) struct CooldownConflictId(i64);

enum ConflictPhase {
    Preparing,
    Active,
    Abandoned,
}

impl ConflictPhase {
    fn parse(value: &str) -> Result<Self> {
        match value {
            "preparing" => Ok(Self::Preparing),
            "active" => Ok(Self::Active),
            "abandoned" => Ok(Self::Abandoned),
            _ => bail!("invalid canonical conflict state"),
        }
    }
}

impl Database {
    /// This read snapshot holds no SQLite writer reservation. A concurrent
    /// writer makes any later legacy write upgrade fail rather than go stale.
    pub(super) async fn begin_canonical_read_transaction(&self) -> Result<DatabaseTransaction> {
        let guard = self.tx_lock.clone().lock_owned().await;
        let tx = self
            .tx_conn
            .transaction_with_behavior(libsql::TransactionBehavior::Deferred)
            .await?;
        Ok(DatabaseTransaction {
            tx: Some(tx),
            _guard: guard,
        })
    }

    pub(super) async fn cooldown_quarantined(conn: &libsql::Connection, id: i64) -> Result<bool> {
        let mut rows = conn
            .query(
                "SELECT 1 FROM review_cooldown_guards
                 WHERE patchset_id = ? AND state = 'blocked' LIMIT 1",
                libsql::params![id],
            )
            .await?;
        Ok(rows.next().await?.is_some())
    }

    pub(super) async fn ensure_cooldown_unblocked(
        conn: &libsql::Connection,
        id: i64,
    ) -> Result<()> {
        if Self::cooldown_quarantined(conn, id).await? {
            bail!("adaptive cooldown is quarantined");
        }
        Ok(())
    }

    async fn prepare_cooldown_conflict(
        &self,
        count: usize,
        reason: &str,
    ) -> Result<CooldownConflictId> {
        let expected = i64::try_from(count).context("conflict owner count overflow")?;
        if expected == 0 {
            bail!("empty canonical conflict");
        }
        let now = Self::cooldown_now()?;
        let lease = now
            .checked_add(CONFLICT_LEASE_SECONDS)
            .context("conflict lease overflow")?;
        let tx = self.begin_immediate_transaction().await?;
        let mut rows = tx
            .query(
                "INSERT INTO review_cooldown_conflicts(expected, reason, created_at, lease_until)
                 VALUES (?, ?, ?, ?) RETURNING id",
                libsql::params![expected, reason, now, lease],
            )
            .await?;
        let id = rows
            .next()
            .await?
            .context("missing conflict group")?
            .get(0)?;
        drop(rows);
        tx.commit().await?;
        Ok(CooldownConflictId(id))
    }

    async fn stage_cooldown_conflict(
        &self,
        group: CooldownConflictId,
        owners: &[i64],
    ) -> Result<()> {
        if owners.is_empty() || owners.len() > CONFLICT_BATCH {
            bail!("invalid conflict batch size");
        }
        let count = i64::try_from(owners.len())?;
        let now = Self::cooldown_now()?;
        let lease = now
            .checked_add(CONFLICT_LEASE_SECONDS)
            .context("conflict lease overflow")?;
        let tx = self.begin_immediate_transaction().await?;
        let changed = tx
            .execute(
                "UPDATE review_cooldown_conflicts SET staged = staged + ?, lease_until = ?
                 WHERE id = ? AND state = 'preparing' AND lease_until >= ?",
                libsql::params![count, lease, group.0, now],
            )
            .await?;
        if changed != 1 {
            bail!("canonical conflict preparation expired");
        }
        for &owner in owners {
            tx.execute(
                "INSERT INTO review_cooldown_conflict_members(patchset_id, group_id)
                 VALUES (?, ?)",
                libsql::params![owner, group.0],
            )
            .await?;
        }
        tx.commit().await
    }

    async fn activate_cooldown_conflict(&self, group: CooldownConflictId) -> Result<()> {
        let now = Self::cooldown_now()?;
        let tx = self.begin_immediate_transaction().await?;
        let changed = tx
            .execute(
                "UPDATE review_cooldown_conflicts SET state = 'active'
                 WHERE id = ? AND state = 'preparing' AND staged = expected
                   AND lease_until >= ?",
                libsql::params![group.0, now],
            )
            .await?;
        if changed != 1 {
            bail!("canonical conflict is incomplete or expired");
        }
        tx.commit().await
    }

    /// Every publication guard observes all owners at the activation commit.
    /// Cancellation afterwards leaves durable protection for recovery to drain.
    pub(super) async fn quarantine_cooldown_conflict(
        &self,
        owners: &[i64],
        reason: &str,
    ) -> Result<()> {
        let group = self.prepare_cooldown_conflict(owners.len(), reason).await?;
        for batch in owners.chunks(CONFLICT_BATCH) {
            self.stage_cooldown_conflict(group, batch).await?;
            tokio::task::yield_now().await;
        }
        self.activate_cooldown_conflict(group).await?;
        while !self.drain_cooldown_conflict_batch(group).await? {
            tokio::task::yield_now().await;
        }
        Ok(())
    }

    /// Transfers at most 64 exact members to existing durable owner blocks.
    /// Expired, unactivated preparation has no publication effect to preserve.
    async fn drain_cooldown_conflict_batch(&self, group: CooldownConflictId) -> Result<bool> {
        let now = Self::cooldown_now()?;
        let tx = self.begin_immediate_transaction().await?;
        let mut rows = tx
            .query(
                "SELECT state, reason, lease_until FROM review_cooldown_conflicts WHERE id = ?",
                libsql::params![group.0],
            )
            .await?;
        let Some(row) = rows.next().await? else {
            drop(rows);
            tx.commit().await?;
            return Ok(true);
        };
        let state = ConflictPhase::parse(&row.get::<String>(0)?)?;
        let reason: String = row.get(1)?;
        let lease: i64 = row.get(2)?;
        drop(rows);
        let active = match state {
            ConflictPhase::Active => true,
            ConflictPhase::Preparing if lease >= now => {
                tx.commit().await?;
                return Ok(true);
            }
            ConflictPhase::Preparing => {
                tx.execute(
                    "UPDATE review_cooldown_conflicts SET state = 'abandoned' WHERE id = ?",
                    libsql::params![group.0],
                )
                .await?;
                false
            }
            ConflictPhase::Abandoned => false,
        };
        let mut rows = tx
            .query(
                "SELECT patchset_id FROM review_cooldown_conflict_members
                 WHERE group_id = ? ORDER BY patchset_id LIMIT ?",
                libsql::params![group.0, CONFLICT_BATCH as i64],
            )
            .await?;
        let mut owners = Vec::with_capacity(CONFLICT_BATCH);
        while let Some(row) = rows.next().await? {
            owners.push(row.get::<i64>(0)?);
        }
        drop(rows);
        for owner in owners {
            if active {
                Self::block_cooldown(&tx, owner, &reason).await?;
            }
            tx.execute(
                "DELETE FROM review_cooldown_conflict_members
                 WHERE patchset_id = ? AND group_id = ?",
                libsql::params![owner, group.0],
            )
            .await?;
        }
        let mut remaining = tx
            .query(
                "SELECT 1 FROM review_cooldown_conflict_members WHERE group_id = ? LIMIT 1",
                libsql::params![group.0],
            )
            .await?;
        let done = remaining.next().await?.is_none();
        drop(remaining);
        if done {
            tx.execute(
                "DELETE FROM review_cooldown_conflicts WHERE id = ?",
                libsql::params![group.0],
            )
            .await?;
        }
        tx.commit().await?;
        Ok(done)
    }

    pub(super) async fn recover_cooldown_conflicts(&self) -> Result<()> {
        loop {
            let now = Self::cooldown_now()?;
            let mut rows = self
                .conn
                .query(
                    "SELECT id FROM review_cooldown_conflicts
                     WHERE state IN ('active', 'abandoned')
                        OR (state = 'preparing' AND lease_until < ?)
                     ORDER BY id LIMIT 1",
                    libsql::params![now],
                )
                .await?;
            let group = rows
                .next()
                .await?
                .map(|row| row.get::<i64>(0))
                .transpose()?;
            drop(rows);
            let Some(group) = group else {
                return Ok(());
            };
            self.drain_cooldown_conflict_batch(CooldownConflictId(group))
                .await?;
            tokio::task::yield_now().await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    async fn database(path: &std::path::Path) -> Result<Database> {
        let db = Database::new(&DatabaseSettings {
            url: path.to_string_lossy().into_owned(),
            token: String::new(),
        })
        .await?;
        db.migrate().await?;
        Ok(db)
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

    async fn seed(db: &Database, count: usize) -> Result<Vec<i64>> {
        let thread = db
            .create_thread("conflict-root@example.test", "conflict", 1)
            .await?;
        let tx = db.begin_immediate_transaction().await?;
        let mut ids: Vec<i64> = Vec::new();
        for index in 0..count {
            let message = format!("conflict-{index}@example.test");
            tx.execute(
                "INSERT INTO messages(message_id,thread_id,author,subject,date,body)
                 VALUES (?, ?, 'dev@example.test', '[PATCH 1/1] conflict', 1, 'diff')",
                libsql::params![message.clone(), thread],
            )
            .await?;
            let mut rows = tx
                .query(
                    "INSERT INTO patchsets(thread_id,cover_letter_message_id,subject,author,date,
                 total_parts,received_parts,status,subject_index,embargo_until)
                 VALUES (?, ?, '[PATCH 1/1] conflict', 'dev@example.test', 1, 1, 1, 'Pending', 1, 1)
                 RETURNING id",
                    libsql::params![thread, message.clone()],
                )
                .await?;
            let id = rows.next().await?.context("missing owner")?.get::<i64>(0)?;
            drop(rows);
            ids.push(id);
            tx.execute(
                "INSERT INTO patches(patchset_id,message_id,part_index,diff) VALUES(?,?,1,'diff')",
                libsql::params![id, message],
            )
            .await?;
        }
        let policy = crate::cooldown::CooldownPolicy {
            window_seconds: 100,
            burst: 2,
            step_seconds: 10,
            max_extra_seconds: 30,
        };
        policy.validate()?;
        tx.execute(
            "INSERT INTO review_cooldown_intents
             (patchset_id,list,author,policy,state,created_at,admitted_at,prior_count,extra_seconds)
             VALUES (?, 'list@example.test', 'dev@example.test', ?, 'decided', 1, 1, 0, 0)",
            libsql::params![ids[0], serde_json::to_string(&policy)?],
        )
        .await?;
        tx.execute(
            "INSERT INTO review_cooldown_messages VALUES ('conflict-0@example.test', ?, 'frozen')",
            libsql::params![ids[0]],
        )
        .await?;
        tx.execute(
            "INSERT INTO review_cooldown_events VALUES (?, 'list@example.test', 'dev@example.test', 1)",
            libsql::params![ids[0]],
        ).await?;
        tx.commit().await?;
        Ok(ids)
    }

    async fn patch_id(db: &Database, owner: i64) -> Result<i64> {
        Ok(db
            .conn
            .query(
                "SELECT id FROM patches WHERE patchset_id = ?",
                libsql::params![owner],
            )
            .await?
            .next()
            .await?
            .context("missing patch")?
            .get(0)?)
    }

    async fn queue_fixture(db: &Database, owner: i64, index: usize) -> Result<i64> {
        let patch = patch_id(db, owner).await?;
        let message = format!("conflict-{index}@example.test");
        db.insert_email_outbox(
            patch,
            "Pending",
            "sink@example.test",
            "",
            "fixture",
            &message,
            "",
            "fixture",
        )
        .await?;
        db.insert_patchwork_outbox(
            &message,
            "https://patchwork.example.test",
            "warning",
            "fixture",
            "https://review.example.test",
            "fixture",
        )
        .await?;
        db.insert_forge_outbox(
            owner,
            "github",
            "fixture/repo",
            1,
            None,
            "fixture",
            "https://review.example.test",
            "Pending",
        )
        .await?;
        Ok(patch)
    }

    async fn assert_blocked(db: &Database, ids: &[i64]) -> Result<()> {
        for &id in ids {
            assert!(
                db.cooldown_publication_blocked(id).await?,
                "group owner escaped quarantine"
            );
            assert!(
                Database::ensure_cooldown_unblocked(&db.conn, id)
                    .await
                    .is_err()
            );
            assert!(!db.claim_patchset_for_review(id).await?);
            assert!(!db.release_patchset_embargo(id, 0).await?);
        }
        Ok(())
    }

    #[tokio::test]
    async fn test_conflict_atomic_activation_and_bounded_restart_handoff() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let path = dir.path().join("conflict.db");
        let db = database(&path).await?;
        let ids = seed(&db, 132).await?;
        let members: Vec<i64> = ids
            .iter()
            .enumerate()
            .filter_map(|(index, &id)| (index != 1).then_some(id))
            .collect();
        let owners = members.as_slice();
        let group = db
            .prepare_cooldown_conflict(owners.len(), "fixture conflict")
            .await?;
        assert!(db.activate_cooldown_conflict(group).await.is_err());
        assert!(db.stage_cooldown_conflict(group, owners).await.is_err());
        for batch in owners.chunks(CONFLICT_BATCH) {
            db.stage_cooldown_conflict(group, batch).await?;
            assert!(
                !db.cooldown_publication_blocked(ids[0]).await?,
                "preparing conflict became visible"
            );
        }
        let reader = database(&path).await?;
        // Startup cannot steal a live preparation from another daemon.
        assert_eq!(
            scalar(
                &reader,
                "SELECT COUNT(*) FROM review_cooldown_conflict_members"
            )
            .await?,
            131
        );
        queue_fixture(&reader, ids[2], 2).await?;
        let eligible_patch = queue_fixture(&reader, ids[1], 1).await?;
        db.activate_cooldown_conflict(group).await?;
        assert_blocked(&reader, owners).await?;
        assert_eq!(
            reader
                .lock_pending_email()
                .await?
                .context("eligible email starved")?
                .patch_id,
            Some(eligible_patch)
        );
        assert_eq!(
            reader
                .lock_pending_patchwork()
                .await?
                .context("eligible patchwork starved")?
                .patch_msg_id,
            "conflict-1@example.test"
        );
        assert_eq!(
            reader
                .lock_pending_forge_outbox()
                .await?
                .context("eligible forge starved")?
                .patchset_id,
            ids[1]
        );
        assert!(reader.lock_pending_email().await?.is_none());
        assert!(reader.lock_pending_patchwork().await?.is_none());
        assert!(reader.lock_pending_forge_outbox().await?.is_none());
        let held_patch = patch_id(&reader, ids[3]).await?;
        let email = reader
            .insert_email_outbox(
                held_patch,
                "Pending",
                "sink@example.test",
                "",
                "fixture",
                "conflict-3@example.test",
                "",
                "fixture",
            )
            .await;
        assert!(
            matches!(email, Err(error) if error.to_string().contains("adaptive publication unresolved"))
        );
        let patchwork = reader
            .insert_patchwork_outbox(
                "conflict-3@example.test",
                "https://patchwork.example.test",
                "warning",
                "fixture",
                "https://review.example.test",
                "fixture",
            )
            .await;
        assert!(
            matches!(patchwork, Err(error) if error.to_string().contains("adaptive publication unresolved"))
        );
        let forge = reader
            .insert_forge_outbox(
                ids[3],
                "github",
                "fixture/repo",
                1,
                None,
                "fixture",
                "https://review.example.test",
                "Pending",
            )
            .await;
        assert!(
            matches!(forge, Err(error) if error.to_string().contains("adaptive publication unresolved"))
        );
        assert_eq!(
            Database::cooldown_owner(&reader.conn, "conflict-2@example.test").await?,
            Some(ids[2])
        );
        let tx = reader.begin_immediate_transaction().await?;
        let binding =
            Database::bind_cooldown_patch_tx(&tx, ids[0], "conflict-0@example.test", None, Some(1))
                .await;
        assert!(
            matches!(binding, Err(error) if error.to_string() == "adaptive cooldown is quarantined")
        );
        let admission = Database::complete_patchset_tx(&tx, ids[0], 2, None).await;
        assert!(
            matches!(admission, Err(error) if error.to_string() == "adaptive cooldown is quarantined")
        );
        tx.rollback().await?;
        assert_eq!(
            scalar(
                &reader,
                "SELECT COUNT(*) FROM review_cooldown_intents WHERE released_at IS NULL"
            )
            .await?,
            1
        );
        assert!(!reader.cooldown_publication_blocked(ids[1]).await?);
        assert!(reader.release_patchset_embargo(ids[1], 0).await?);
        assert!(db.stage_cooldown_conflict(group, &[ids[1]]).await.is_err());
        assert!(!db.drain_cooldown_conflict_batch(group).await?);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflict_members").await?,
            67
        );
        assert_blocked(&reader, owners).await?;
        drop(reader);
        drop(db);
        let reopened = database(&path).await?;
        assert_blocked(&reopened, owners).await?;
        assert_eq!(
            scalar(&reopened, "SELECT COUNT(*) FROM review_cooldown_conflicts").await?,
            0
        );
        assert_eq!(
            scalar(&reopened, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        assert_eq!(
            scalar(
                &reopened,
                "SELECT COUNT(*) FROM review_cooldown_messages WHERE source_hash='frozen'"
            )
            .await?,
            1
        );
        assert_eq!(
            Database::cooldown_owner(&reopened.conn, "conflict-0@example.test").await?,
            Some(ids[0])
        );
        assert_eq!(
            scalar(&reopened, "SELECT COUNT(*) FROM patchsets").await?,
            132
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_conflict_failed_stage_rolls_back_and_expired_cleanup_is_bounded() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let db = database(&dir.path().join("failed.db")).await?;
        let ids = seed(&db, 130).await?;
        let group = db
            .prepare_cooldown_conflict(ids.len(), "fixture conflict")
            .await?;
        db.stage_cooldown_conflict(group, &ids[..64]).await?;
        assert!(
            db.stage_cooldown_conflict(group, &[ids[63], ids[64]])
                .await
                .is_err()
        );
        assert_eq!(
            scalar(&db, "SELECT staged FROM review_cooldown_conflicts").await?,
            64
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflict_members").await?,
            64
        );
        db.stage_cooldown_conflict(group, &ids[64..128]).await?;
        db.execute(
            "UPDATE review_cooldown_conflicts SET created_at=0, lease_until=0",
            (),
        )
        .await?;
        assert!(!db.drain_cooldown_conflict_batch(group).await?);
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflict_members").await?,
            64
        );
        assert!(db.activate_cooldown_conflict(group).await.is_err());
        db.recover_cooldown_conflicts().await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflicts").await?,
            0
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_blocks").await?,
            0
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_messages").await?,
            1
        );
        Ok(())
    }

    #[tokio::test]
    async fn test_conflict_overlapping_groups_keep_protection() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let db = database(&dir.path().join("overlap.db")).await?;
        let ids = seed(&db, 3).await?;
        let a = db.prepare_cooldown_conflict(2, "first conflict").await?;
        let b = db.prepare_cooldown_conflict(2, "second conflict").await?;
        db.stage_cooldown_conflict(a, &ids[..2]).await?;
        db.stage_cooldown_conflict(b, &ids[1..]).await?;
        db.activate_cooldown_conflict(a).await?;
        db.activate_cooldown_conflict(b).await?;
        assert!(db.drain_cooldown_conflict_batch(a).await?);
        assert_blocked(&db, &ids).await?;
        assert!(db.drain_cooldown_conflict_batch(b).await?);
        assert_blocked(&db, &ids).await?;
        Ok(())
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn test_conflict_read_snapshot_and_batches_allow_independent_writer() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let path = dir.path().join("writers.db");
        let db = database(&path).await?;
        let other = database(&path).await?;
        let ids = seed(&db, 65).await?;
        let read = db.begin_canonical_read_transaction().await?;
        let mut rows = read.query("SELECT id FROM patchsets", ()).await?;
        assert!(rows.next().await?.is_some());
        tokio::time::timeout(
            std::time::Duration::from_secs(3),
            other.set_meta("independent-writer", "read-phase"),
        )
        .await??;
        drop(rows);
        let stale = read
            .execute(
                "UPDATE patchsets SET subject = 'stale snapshot' WHERE id = ?",
                libsql::params![ids[0]],
            )
            .await;
        assert!(stale.is_err(), "stale legacy write snapshot was upgraded");
        read.rollback().await?;
        let group = db
            .prepare_cooldown_conflict(ids.len(), "fixture conflict")
            .await?;
        db.stage_cooldown_conflict(group, &ids[..64]).await?;
        tokio::time::timeout(
            std::time::Duration::from_secs(3),
            other.set_meta("independent-writer", "between-batches"),
        )
        .await??;
        db.stage_cooldown_conflict(group, &ids[64..]).await?;
        db.activate_cooldown_conflict(group).await?;
        assert!(!db.drain_cooldown_conflict_batch(group).await?);
        tokio::time::timeout(
            std::time::Duration::from_secs(3),
            other.set_meta("independent-writer", "during-handoff"),
        )
        .await??;
        assert!(db.drain_cooldown_conflict_batch(group).await?);
        Ok(())
    }

    #[tokio::test]
    async fn test_conflict_binding_snapshots_reject_decided_and_legacy_owners() -> Result<()> {
        let dir = tempfile::tempdir()?;
        let db = database(&dir.path().join("bindings.db")).await?;
        let ids = seed(&db, 3).await?;
        let owners = [ids[0], ids[2]];
        let group = db
            .prepare_cooldown_conflict(2, "binding snapshot fixture")
            .await?;
        db.stage_cooldown_conflict(group, &owners).await?;
        db.activate_cooldown_conflict(group).await?;
        let tx = db.begin_immediate_transaction().await?;
        for (id, index) in [(ids[0], 0), (ids[2], 2)] {
            let message = format!("conflict-{index}@example.test");
            let source = Database::bind_cooldown_message_tx(&tx, id, &message, None).await;
            assert!(
                matches!(source, Err(error) if error.to_string() == "adaptive cooldown is quarantined"),
                "source binding bypassed the active group"
            );
            let patch = Database::bind_cooldown_patch_tx(&tx, id, &message, None, Some(1)).await;
            assert!(
                matches!(patch, Err(error) if error.to_string() == "adaptive cooldown is quarantined"),
                "patch binding bypassed the active group"
            );
            let admission = Database::complete_patchset_tx(&tx, id, 2, None).await;
            assert!(
                matches!(admission, Err(error) if error.to_string() == "adaptive cooldown is quarantined"),
                "completion bypassed the active group"
            );
        }
        tx.rollback().await?;
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?,
            1
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_messages").await?,
            1
        );
        assert_eq!(
            scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflict_members").await?,
            2
        );
        Ok(())
    }
}
