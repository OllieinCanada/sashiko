
    mod hosted_downgrade {
        use super::*;
        #[tokio::test]
        #[ignore = "hosted quiesce before old-version native access"]
        async fn test_cooldown_downgrade_candidate_phases() -> Result<()> {
            let settings = DatabaseSettings {
                url: std::env::var("COOLDOWN_DOWNGRADE_DB")?, token: String::new(),
            };
            let phase = std::env::var("COOLDOWN_DOWNGRADE_PHASE")?;
            let db = Database::new(&settings).await?;
            db.migrate().await?;
            if phase == "prepare" {
                db.ensure_project_stamp(crate::project::ProjectId::Sashiko).await?;
                let mut ctx = context("list@example.test", "dev@example.test");
                ctx.policy.burst = 1;
                ctx.policy.window_seconds = 86400;
                ctx.policy.step_seconds = 3600;
                ctx.policy.max_extra_seconds = 3600;
                let active = db.with_cooldown_context(Some(ctx));
                let (prior, _, msg) = seed(&active, "rollback-prior", 1).await?;
                active.create_patch(prior, &msg, 1, "diff").await?;
                let (held, _, msg) = seed(&active, "rollback-held", 1).await?;
                let patch = active.create_patch(held, &msg, 1, "diff").await?;
                let (waiting, _, message) = seed(&active, "rollback-waiting", 2).await?;
                active.create_patch(waiting, &message, 1, "diff1").await?;
                assert_eq!(db.get_patchset_status(waiting).await?.as_deref(), Some("Incomplete"));
                assert_eq!(scalar(&db, "SELECT received_parts FROM patchsets WHERE total_parts=2").await?, 1);
                db.insert_email_outbox(patch, "Pending", "sink@example.test", "", "held", &msg, "", "fixture").await?;
                db.insert_patchwork_notification("Pending", "sink@example.test", "held notification", &format!("<{msg}>"), "", "fixture").await?;
                db.insert_patchwork_outbox(&msg, "https://patchwork.example.test", "warning", "fixture", "https://review.example.test", "review").await?;
                assert!(db.lock_pending_email().await?.is_none());
                assert!(db.lock_pending_patchwork().await?.is_none());
                let now = chrono::Utc::now().timestamp();
                let tx = db.begin_immediate_transaction().await?;
                let mut rows = tx.query(
                    "INSERT INTO review_cooldown_conflicts
                     (expected,staged,reason,created_at,lease_until)
                     VALUES (2,2,'rollback preparation',?,?) RETURNING id",
                    libsql::params![now, now + 3600],
                ).await?;
                let group: i64 = rows.next().await?.context("missing staged group")?.get(0)?;
                drop(rows);
                for owner in [prior, held] {
                    tx.execute(
                        "INSERT INTO review_cooldown_conflict_members(patchset_id,group_id)
                         VALUES (?,?)", libsql::params![owner, group],
                    ).await?;
                }
                tx.commit().await?;
                return Ok(());
            }
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflicts WHERE state='preparing'").await?, 1);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflict_members").await?, 2);
            if phase == "resume" {
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets WHERE status='Pending'").await?, 2);
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets WHERE status='Incomplete'").await?, 1);
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?, 3);
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM email_outbox WHERE status='Pending'").await?, 2);
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchwork_outbox WHERE status='Pending'").await?, 1);
                assert!(db.lock_pending_email().await?.is_none());
                assert!(db.lock_pending_patchwork().await?.is_none());
                let pending = db.get_pending_patchsets(10).await?;
                assert_eq!(pending.len(), 2);
                return Ok(());
            }
            if phase == "quiesce" {
                let mut rows = db.conn.query("SELECT id FROM patchsets ORDER BY id", ()).await?;
                let mut ids = Vec::new();
                while let Some(row) = rows.next().await? { ids.push(row.get::<i64>(0)?); }
                drop(rows);
                assert_eq!(ids.len(), 3);
                for id in ids { assert!(db.cancel_patchset(id, false).await?); }
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchsets WHERE status='Cancelled'").await?, 3);
            } else {
                anyhow::ensure!(phase == "verify", "unknown downgrade phase");
            }
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?, 3);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM email_outbox WHERE status IN ('Pending','Embargoed','Sending')").await?, 0);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchwork_outbox WHERE status IN ('Pending','Sending')").await?, 0);
            assert_eq!(scalar(&db, "PRAGMA user_version").await?, 16);
            let result: String = db.conn.query("PRAGMA integrity_check", ()).await?.next().await?
                .context("missing integrity result")?.get(0)?;
            assert_eq!(result, "ok");
            Ok(())
        }
    }
