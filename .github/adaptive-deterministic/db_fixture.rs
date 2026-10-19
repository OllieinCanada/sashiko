
    #[tokio::test]
    async fn test_det6_forward_clock_release_is_irreversible() -> Result<()> {
        let db = database().await?;
        let mut policy = context("list@example.test", "dev@example.test");
        policy.policy.burst = 1;
        let active = db.with_cooldown_context(Some(policy));
        let (prior, _, msg) = seed(&active, "det6-clock-prior", 1).await?;
        admit_at(&active, prior, &msg, 1000).await?;
        let (held, _, message) = seed(&active, "det6-clock-held", 1).await?;
        admit_at(&active, held, &message, 1001).await?;
        completed_fixture(&db, held, true).await?;
        let snapshot = scalar(&db, "SELECT decided_deadline FROM review_cooldown_intents WHERE admitted_at=1001").await?;
        assert_eq!(snapshot, 1011);
        for (now, eligible) in [(0, false), (999, false), (1010, false), (1011, true), (4000, true), (i64::MAX, true), (1010, false)] {
            let selected = db.get_releasable_embargoed_patchsets(now, 10).await?;
            assert_eq!(selected.iter().any(|p| p.id == held), eligible, "now={now}");
            assert_eq!(scalar(&db, "SELECT decided_deadline FROM review_cooldown_intents WHERE admitted_at=1001").await?, snapshot);
        }
        let (late, _, msg) = seed(&active, "det6-clock-later", 1).await?;
        admit_at(&active, late, &msg, 4000).await?;
        let (backward, _, msg) = seed(&active, "det6-clock-back", 1).await?;
        assert!(admit_at(&active, backward, &msg, 3999).await.is_err());
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
        assert!(db.release_patchset_embargo(held, 4000).await?);
        db.create_patch(held, &message, 1, "diff").await?;
        assert_eq!(db.get_patchset_details(held, None, None).await?.unwrap()["embargo_until"], serde_json::Value::Null);
        assert_eq!(scalar(&db, "SELECT released_at FROM review_cooldown_intents WHERE admitted_at=1001").await?, 4000);
        assert_eq!(scalar(&db, "SELECT decided_deadline FROM review_cooldown_intents WHERE admitted_at=1001").await?, 1011);
        println!("DET6_CASES selector_clock_instants=7 forward_admission=1 backward_rejection=1");
        Ok(())
    }

    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn test_det6_cancel_uncommitted_admission_releases_writer() -> Result<()> {
        let directory = tempfile::tempdir()?;
        let settings = DatabaseSettings {url: directory.path().join("cancel.db").to_string_lossy().into_owned(), token: String::new()};
        let db = Database::new(&settings).await?;
        db.migrate().await?;
        let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let (id, _, message) = seed(&active, "det6-abort-admission", 1).await?;
        let (ready, observed) = tokio::sync::oneshot::channel();
        let writer = active.with_cooldown_context(active.cooldown_context.clone());
        let task = tokio::spawn(async move {
            let tx = writer.begin_immediate_transaction().await?;
            tx.execute("INSERT INTO patches(patchset_id,message_id,part_index,diff,cooldown_content_hash) VALUES (?, ?, 1, 'diff', ?)",
                libsql::params![id, message, crate::cooldown::content_fingerprint(b"diff")]).await?;
            tx.execute("UPDATE patchsets SET received_parts=1 WHERE id=?", libsql::params![id]).await?;
            Database::complete_patchset_tx(&tx, id, 1000, writer.cooldown_context.as_ref()).await?;
            let _ = ready.send(());
            std::future::pending::<()>().await;
            tx.commit().await
        });
        tokio::time::timeout(std::time::Duration::from_secs(5), observed).await??;
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        let independent = Database::new(&settings).await?;
        tokio::time::timeout(std::time::Duration::from_secs(5), independent.create_thread("det6-writer-after-abort@example.test", "unrelated", 1)).await??;
        assert_eq!(scalar(&independent, "SELECT COUNT(*) FROM patches").await?, 0);
        assert_eq!(scalar(&independent, "SELECT COUNT(*) FROM review_cooldown_events").await?, 0);
        assert_eq!(scalar(&independent, "SELECT COUNT(*) FROM review_cooldown_intents WHERE state='decided'").await?, 0);
        let mut rows = independent.conn.query("SELECT message_id FROM review_cooldown_messages WHERE patchset_id=?", libsql::params![id]).await?;
        let message: String = rows.next().await?.context("owner message")?.get(0)?;
        active.create_patch(id, &message, 1, "diff").await?;
        assert_eq!(scalar(&independent, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
        Ok(())
    }

    #[tokio::test]
    async fn test_det6_bound_sql_payloads_preserve_schema_and_dedup() -> Result<()> {
        let db = database().await?;
        let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
        let before: String = db.conn.query("SELECT group_concat(name || ':' || coalesce(sql,''), char(10)) FROM (SELECT name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') ORDER BY name)", ()).await?.next().await?.context("schema")?.get(0)?;
        for index in 0..64 {
            let token = format!("det6-{index}-');DROP(TABLE);--");
            let (id, _, message) = seed(&active, &token, 1).await?;
            active.create_patch(id, &message, 1, "diff").await?;
            active.create_patch(id, &message, 1, "diff").await?;
        }
        let after: String = db.conn.query("SELECT group_concat(name || ':' || coalesce(sql,''), char(10)) FROM (SELECT name,sql FROM sqlite_master WHERE type IN ('table','index','trigger') ORDER BY name)", ()).await?.next().await?.context("schema")?.get(0)?;
        assert_eq!(before, after);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM patches").await?, 64);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 64);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents WHERE state='decided'").await?, 64);
        Ok(())
    }
