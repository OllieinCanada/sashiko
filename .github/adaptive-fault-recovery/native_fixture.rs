
    mod hosted_filesystem_recovery {
        use super::*;
        #[tokio::test]
        #[ignore = "hosted OS I/O faults and killed-process recovery"]
        async fn test_cooldown_filesystem_fault_recovery() -> Result<()> {
            let root = std::path::PathBuf::from(std::env::var("COOLDOWN_FAULT_ROOT")?);
            let settings = DatabaseSettings {
                url: root.join("fault.db").to_string_lossy().into_owned(), token: String::new(),
            };
            let phase = std::env::var("COOLDOWN_FAULT_PHASE")?;
            let mode = std::env::var("COOLDOWN_FAULT_MODE")?;
            let db = Database::new(&settings).await?;
            db.migrate().await?;
            let mut policy = context("list@example.test", "dev@example.test");
            policy.policy.burst = 1;
            let active = db.with_cooldown_context(Some(policy.clone()));
            if phase == "seed" {
                let (prior, _, message) = seed(&active, "fault-prior", 1).await?;
                active.create_patch(prior, &message, 1, "diff").await?;
                seed(&active, "fault-target", 1).await?;
                assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
                return Ok(());
            }
            let mut rows = db.conn.query("SELECT id FROM patchsets WHERE cover_letter_message_id='fault-target-1@example.test'", ()).await?;
            let id: i64 = rows.next().await?.context("missing fault target")?.get(0)?;
            drop(rows);
            let message = "fault-target-1@example.test";
            if phase == "write" {
                {
                    let mut rows = db.tx_conn.query("PRAGMA synchronous=FULL", ()).await?;
                    while rows.next().await?.is_some() {}
                }
                std::fs::write(std::env::var("COOLDOWN_FAULT_ARM")?, "armed")?;
                let result = active.create_patch(id, message, 1, "diff").await;
                if matches!(mode.as_str(), "enospc" | "eio") {
                    std::fs::remove_file(std::env::var("COOLDOWN_FAULT_ARM")?)?;
                    assert!(result.is_err(), "filesystem fault did not reject commit");
                    assert!(std::path::Path::new(&std::env::var("COOLDOWN_FAULT_HIT")?).exists());
                    return Ok(());
                }
                anyhow::bail!("crash gate did not stop writer: {result:?}");
            }
            anyhow::ensure!(phase == "recover", "unknown phase");
            let expected = if mode == "postcommit" { 2 } else { 1 };
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, expected);
            assert_eq!(scalar(&db, &format!("SELECT COUNT(*) FROM patches WHERE patchset_id={id}")).await?, expected - 1);
            let integrity: String = db.conn.query("PRAGMA integrity_check", ()).await?.next().await?
                .context("missing integrity result")?.get(0)?;
            assert_eq!(integrity, "ok");
            assert!(db.conn.query("PRAGMA foreign_key_check", ()).await?.next().await?.is_none());
            active.create_patch(id, message, 1, "diff").await?;
            let frozen_sql = format!("SELECT json_array(c.admitted_at,c.prior_count,c.extra_seconds,c.decided_deadline,c.released_at,p.embargo_until) FROM review_cooldown_intents c JOIN patchsets p ON p.id=c.patchset_id WHERE p.id={id}");
            let before: String = db.conn.query(&frozen_sql, ()).await?.next().await?.context("missing decision")?.get(0)?;
            db.create_patch(id, message, 1, "diff").await?;
            let after: String = db.conn.query(&frozen_sql, ()).await?.next().await?.context("missing replay decision")?.get(0)?;
            assert_eq!(before, after);
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            assert_eq!(scalar(&db, &format!("SELECT prior_count FROM review_cooldown_intents WHERE patchset_id={id}")).await?, 1);
            println!("FAULT_RECOVERY mode={mode} PASS");
            Ok(())
        }
    }
