
    mod hosted_validation {
        use super::*;

        async fn file_database(path: &std::path::Path) -> Result<Database> {
            let db = Database::new(&DatabaseSettings {
                url: path.to_string_lossy().into_owned(),
                token: String::new(),
            })
            .await?;
            db.migrate().await?;
            Ok(db)
        }

        async fn retained_owners(db: &Database, count: i64) -> Result<()> {
            if count == 0 {
                return Ok(());
            }
            let tx = db.begin_immediate_transaction().await?;
            tx.execute(
                "WITH RECURSIVE n(v) AS (VALUES(1) UNION ALL SELECT v+1 FROM n WHERE v < ?) INSERT INTO patchsets(id,status,total_parts,received_parts) SELECT -v,'Reviewed',1,1 FROM n",
                libsql::params![count],
            )
            .await?;
            let policy = serde_json::to_string(&context("retained@example.test", "archive@example.test").policy)?;
            tx.execute(
                "INSERT INTO review_cooldown_intents(patchset_id,list,author,policy,state,created_at,admitted_at,prior_count,extra_seconds,verified_parts,history_since) SELECT id,'retained@example.test','archive@example.test',?,'decided',0,0,0,0,1,0 FROM patchsets WHERE id < 0",
                libsql::params![policy],
            )
            .await?;
            tx.commit().await?;
            Ok(())
        }

        async fn ingest(
            db: &Database,
            token: &str,
            total: u32,
            list: &str,
            author: &str,
            large: bool,
            duplicate: bool,
        ) -> Result<i64> {
            let first = format!("{token}-1@example.test");
            let subject = format!("[PATCH 1/{total}] {token}");
            let thread = db.create_thread(&first, &subject, 1).await?;
            let body = if large { "x".repeat(65536) } else { "diff".into() };
            db.create_message(&first, thread, None, author, &subject, 1, &body, list, "", None, None).await?;
            let handle = fixture_source_handle(db, &first).await?;
            let id = handle.create_patchset(
                thread, Some(&first), &first, &subject, author, 1, total, 3,
                list, "", None, 1, None, true, None, None,
            ).await?.context("missing hosted owner")?;
            handle.create_patch(id, &first, 1, &body).await?;
            if duplicate {
                handle.create_patch(id, &first, 1, &body).await?;
            }
            for part in 2..=total {
                let message = format!("{token}-{part}@example.test");
                let subject = format!("[PATCH {part}/{total}] {token}");
                db.create_message(&message, thread, Some(&first), author, &subject, 1, &body, list, "", None, None).await?;
                let handle = fixture_source_handle(db, &message).await?;
                handle.create_patch(id, &message, part, &body).await?;
                if duplicate {
                    handle.create_patch(id, &message, part, &body).await?;
                }
            }
            Ok(id)
        }

        #[tokio::test]
        #[ignore = "bounded hosted performance fixture"]
        async fn test_cooldown_hosted_performance() -> Result<()> {
            let mode = std::env::var("COOLDOWN_PROBE_MODE")?;
            anyhow::ensure!(mode == "disabled" || mode == "enabled", "invalid mode");
            let retained: i64 = std::env::var("COOLDOWN_PROBE_RETAINED")?.parse()?;
            anyhow::ensure!([0, 10000].contains(&retained), "invalid retained size");
            let directory = tempfile::tempdir()?;
            let db = file_database(&directory.path().join("probe.db")).await?;
            retained_owners(&db, retained).await?;
            let started = std::time::Instant::now();
            let mut admitted = 0;
            let mut patches = 0;
            for item in 0..1000 {
                let parts = [1, 2, 4, 8][item % 4];
                patches += parts;
                let list = if item % 2 == 0 { "list@example.test" } else { "other@example.test" };
                let author = if item % 3 == 0 { "hot@example.test".into() } else { format!("author-{}@example.test", item % 100) };
                let enabled = mode == "enabled" && item % 5 != 0;
                let handle = db.with_cooldown_context(enabled.then(|| context(list, &author)));
                ingest(&handle, &format!("load-{item}"), parts, list, &author, item % 20 == 0, item % 10 == 0).await?;
                admitted += i64::from(enabled);
            }
            let seconds = started.elapsed().as_secs_f64();
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, i64::from(patches));
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, admitted);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents WHERE state='blocked'").await?, 0);
            println!("COOLDOWN_PROBE {}", serde_json::json!({
                "mode": mode, "retained": retained, "series": 1000,
                "patches": patches, "events": admitted, "seconds": seconds,
                "storage": "file-backed", "profile": "instrumentation-free-debug"
            }));
            Ok(())
        }

        #[tokio::test]
        #[ignore = "bounded hosted maximum-series validation"]
        async fn test_cooldown_hosted_maximum_series() -> Result<()> {
            let db = database().await?;
            let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
            let id = ingest(&active, "maximum", MAX_SERIES_PARTS, "list@example.test", "dev@example.test", false, false).await?;
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
            let mut rows = db.conn.query("SELECT verified_parts,state FROM review_cooldown_intents WHERE patchset_id=?", libsql::params![id]).await?;
            let row = rows.next().await?.context("missing maximum decision")?;
            assert_eq!(row.get::<u32>(0)?, MAX_SERIES_PARTS);
            assert_eq!(row.get::<String>(1)?, "decided");
            Ok(())
        }

        #[tokio::test]
        #[ignore = "hosted missing-history read fault"]
        async fn test_cooldown_hosted_history_read_fault() -> Result<()> {
            let db = database().await?;
            let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
            let (id, _, message) = seed(&active, "history-read-fault", 1).await?;
            db.conn.execute("DROP TABLE review_cooldown_events", ()).await?;
            assert!(active.create_patch(id, &message, 1, "diff").await.is_err());
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 0);
            let mut rows = db.conn.query("SELECT state FROM review_cooldown_intents WHERE patchset_id=?", libsql::params![id]).await?;
            assert_eq!(rows.next().await?.context("missing waiting owner")?.get::<String>(0)?, "waiting");
            Ok(())
        }

        #[tokio::test]
        #[ignore = "hosted process exit immediately after commit"]
        async fn test_cooldown_hosted_process_restart() -> Result<()> {
            let phase = std::env::var("COOLDOWN_RESTART_PHASE")?;
            let path = std::path::PathBuf::from(std::env::var("COOLDOWN_RESTART_PATH")?);
            anyhow::ensure!(phase == "write" || phase == "read", "invalid restart phase");
            let db = file_database(&path).await?;
            let mut ctx = context("list@example.test", "dev@example.test");
            ctx.policy.burst = 1;
            let active = db.with_cooldown_context(Some(ctx));
            if phase == "write" {
                for token in ["process-prior", "process-held"] {
                    let (id, _, message) = seed(&active, token, 1).await?;
                    active.create_patch(id, &message, 1, "diff").await?;
                }
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
                // Skip all Rust destructors after both admission commits.
                std::process::exit(23);
            }
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            let mut rows = db.conn.query("SELECT p.id,p.embargo_until,c.decided_deadline FROM patchsets p JOIN review_cooldown_intents c ON c.patchset_id=p.id WHERE p.cover_letter_message_id='process-held-1@example.test'", ()).await?;
            let row = rows.next().await?.context("missing durable owner")?;
            let id: i64 = row.get(0)?;
            let before: i64 = row.get(1)?;
            assert_eq!(before, row.get::<i64>(2)?);
            // Finish this read snapshot before writes through the other connection.
            drop(row);
            drop(rows);
            active.create_patch(id, "process-held-1@example.test", 1, "diff").await?;
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            assert!(db.release_patchset_embargo(id, 1).await?);
            assert_eq!(scalar(&db, &format!("SELECT embargo_until FROM patchsets WHERE id={id}")).await?, 1);
            active.create_patch(id, "process-held-1@example.test", 1, "diff").await?;
            let mut rows = db.conn.query("SELECT embargo_until FROM patchsets WHERE id=?", libsql::params![id]).await?;
            assert_eq!(rows.next().await?.context("missing released owner")?.get::<i64>(0)?, 1);
            Ok(())
        }
    }
