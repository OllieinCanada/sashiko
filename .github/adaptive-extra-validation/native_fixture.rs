
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
    }
