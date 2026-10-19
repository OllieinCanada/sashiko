
    mod hosted_extra_validation {
        use super::*;

        #[tokio::test]
        #[ignore = "hosted read-only writer fault and retry"]
        async fn test_cooldown_hosted_read_only_writer_retry() -> Result<()> {
            let db = database().await?;
            let active =
                db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
            let (id, _, message) = seed(&active, "readonly-retry", 1).await?;
            db.tx_conn.execute("PRAGMA query_only=ON", ()).await?;
            let failed = active.create_patch(id, &message, 1, "diff").await;
            db.tx_conn.execute("PRAGMA query_only=OFF", ()).await?;
            assert!(failed.is_err());
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 0);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 0);
            assert_eq!(db.get_patchset_status(id).await?.as_deref(), Some("Incomplete"));
            active.create_patch(id, &message, 1, "diff").await?;
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
            Ok(())
        }

        #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
        #[ignore = "hosted independent writer lock fault and retry"]
        async fn test_cooldown_hosted_busy_writer_retry() -> Result<()> {
            let directory = tempfile::tempdir()?;
            let settings = DatabaseSettings {
                url: directory.path().join("busy.db").to_string_lossy().into_owned(),
                token: String::new(),
            };
            let first = Database::new(&settings).await?;
            first.migrate().await?;
            let second = Database::new(&settings).await?;
            let active =
                second.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
            let (id, _, message) = seed(&active, "busy-retry", 1).await?;
            {
                let mut rows = second.tx_conn.query("PRAGMA busy_timeout=1", ()).await?;
                while rows.next().await?.is_some() {}
            }
            let lock = first.begin_immediate_transaction().await?;
            let started = std::time::Instant::now();
            let failed = active.create_patch(id, &message, 1, "diff").await;
            let elapsed = started.elapsed();
            lock.rollback().await?;
            assert!(failed.is_err());
            assert!(elapsed < std::time::Duration::from_secs(5), "{elapsed:?}");
            assert_eq!(scalar(&second, "SELECT COUNT(*) FROM patches").await?, 0);
            assert_eq!(scalar(&second, "SELECT COUNT(*) FROM review_cooldown_events").await?, 0);
            assert_eq!(second.get_patchset_status(id).await?.as_deref(), Some("Incomplete"));
            active.create_patch(id, &message, 1, "diff").await?;
            assert_eq!(scalar(&second, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
            Ok(())
        }

        #[tokio::test]
        #[ignore = "hosted pruning batch and permanent dedup state"]
        async fn test_cooldown_hosted_pruning_keeps_dedup_state() -> Result<()> {
            let db = database().await?;
            let active =
                db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
            let mut oldest = None;
            for now in 1..=17 {
                let (id, _, message) = seed(&active, &format!("prune-{now}"), 1).await?;
                admit_at(&active, id, &message, now).await?;
                if oldest.is_none() {
                    oldest = Some((id, message));
                }
            }
            let (id, _, message) = seed(&active, "prune-new", 1).await?;
            admit_at(
                &active, id, &message,
                i64::from(crate::cooldown::MAX_WINDOW_SECONDS) + 100,
            ).await?;
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events WHERE admitted_at<100").await?, 1);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?, 18);
            let (oldest_id, oldest_message) = oldest.context("missing oldest admission")?;
            let sql = format!("SELECT COUNT(*) FROM review_cooldown_events WHERE patchset_id={oldest_id}");
            assert_eq!(scalar(&db, &sql).await?, 0);
            db.create_patch(oldest_id, &oldest_message, 1, "diff").await?;
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?, 18);
            Ok(())
        }

        #[tokio::test]
        #[ignore = "hosted stale delivery lease after durable quarantine"]
        async fn test_cooldown_hosted_stale_leases_recheck_quarantine() -> Result<()> {
            let directory = tempfile::tempdir()?;
            let settings = DatabaseSettings {
                url: directory.path().join("lease-recovery.db").to_string_lossy().into_owned(),
                token: String::new(),
            };
            let db = Database::new(&settings).await?;
            db.migrate().await?;
            let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
            let (id, thread, message) = seed(&active, "lease-recovery", 1).await?;
            let patch = active.create_patch(id, &message, 1, "diff").await?;
            db.insert_email_outbox(patch, "Pending", "sink@example.test", "", "review", &message, "", "body").await?;
            db.insert_patchwork_notification("Pending", "sink@example.test", "notification", &format!("<{message}>"), "", "body").await?;
            db.insert_patchwork_outbox(&message, "https://patchwork.example.test", "warning", "fixture", "https://review.example.test", "review").await?;
            assert!(db.lock_pending_email().await?.is_some());
            assert!(db.lock_pending_email().await?.is_some());
            assert!(db.lock_pending_email().await?.is_none());
            assert!(db.lock_pending_patchwork().await?.is_some());
            // A correction arrives after claiming, before any external delivery.
            assert!(active.create_message(&message, thread, None, "dev@example.test", "[PATCH] changed", 1, "changed", "list@example.test", "", None, None).await.is_err());
            assert_eq!(db.get_patchset_status(id).await?.as_deref(), Some("Cooldown blocked"));
            db.conn.execute("UPDATE email_outbox SET locked_at=0 WHERE status='Sending'", ()).await?;
            db.conn.execute("UPDATE patchwork_outbox SET locked_at=0 WHERE status='Sending'", ()).await?;
            drop(active);
            drop(db);
            let db = Database::new(&settings).await?;
            assert_eq!(db.sweep_ghost_emails().await?, 2);
            assert_eq!(db.sweep_ghost_patchwork().await?, 1);
            assert!(db.lock_pending_email().await?.is_none());
            assert!(db.lock_pending_patchwork().await?.is_none());
            assert!(!db.release_patchset_embargo(id, chrono::Utc::now().timestamp()).await?);
            assert!(!db.claim_patchset_for_review(id).await?);
            assert!(db.cancel_patchset(id, false).await?);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM email_outbox WHERE status='Cancelled'").await?, 2);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patchwork_outbox WHERE status='Cancelled'").await?, 1);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
            Ok(())
        }

        #[tokio::test]
        #[ignore = "hosted disable and cancellation rollback rehearsal"]
        async fn test_cooldown_hosted_disable_cancel_reopen() -> Result<()> {
            let directory = tempfile::tempdir()?;
            let settings = DatabaseSettings {
                url: directory.path().join("disable-rehearsal.db").to_string_lossy().into_owned(),
                token: String::new(),
            };
            let db = Database::new(&settings).await?;
            db.migrate().await?;
            let mut ctx = context("list@example.test", "dev@example.test");
            ctx.policy.burst = 1;
            let active = db.with_cooldown_context(Some(ctx));
            let (prior, _, first) = seed(&active, "disable-prior", 1).await?;
            active.create_patch(prior, &first, 1, "diff").await?;
            let (held, _, message) = seed(&active, "disable-held", 1).await?;
            active.create_patch(held, &message, 1, "diff").await?;
            let (waiting, _, _) = seed(&active, "disable-waiting", 2).await?;
            let frozen_sql = format!("SELECT decided_deadline FROM review_cooldown_intents WHERE patchset_id={held}");
            let before = scalar(&db, &frozen_sql).await?;
            // The ordinary handle represents ingestion after configuration disable.
            let (legacy, _, message) = seed(&db, "disable-new-legacy", 1).await?;
            db.create_patch(legacy, &message, 1, "diff").await?;
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents").await?, 3);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            assert_eq!(scalar(&db, &frozen_sql).await?, before);
            assert!(!db.claim_patchset_for_review(waiting).await?);
            assert!(db.cancel_patchset(waiting, false).await?);
            assert!(db.cancel_patchset(held, false).await?);
            drop(active);
            drop(db);
            let db = Database::new(&settings).await?;
            db.migrate().await?;
            assert_eq!(db.get_patchset_status(waiting).await?.as_deref(), Some("Cancelled"));
            assert_eq!(db.get_patchset_status(held).await?.as_deref(), Some("Cancelled"));
            assert_eq!(scalar(&db, &frozen_sql).await?, before);
            assert!(db.lock_pending_email().await?.is_none());
            assert!(db.lock_pending_patchwork().await?.is_none());
            assert_eq!(scalar(&db, "PRAGMA user_version").await?, 15);
            Ok(())
        }
    }
