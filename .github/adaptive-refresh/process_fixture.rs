
    #[tokio::test]
    #[ignore = "hosted process-kill conflict recovery"]
    async fn test_hosted_conflict_process_phases() -> Result<()> {
        let path = std::path::PathBuf::from(std::env::var("CONFLICT_PROCESS_DB")?);
        let phase = std::env::var("CONFLICT_PROCESS_PHASE")?;
        let action = std::env::var("CONFLICT_PROCESS_ACTION")?;
        let db = database(&path).await?;
        if action == "prepare" {
            let ids = seed(&db, 132).await?;
            let owners: Vec<i64> = ids.iter().enumerate()
                .filter_map(|(index, &id)| (index != 1).then_some(id)).collect();
            queue_fixture(&db, ids[2], 2).await?;
            let group = db.prepare_cooldown_conflict(owners.len(), "process crash fixture").await?;
            if phase == "preparing" {
                db.stage_cooldown_conflict(group, &owners[..64]).await?;
            } else {
                for batch in owners.chunks(CONFLICT_BATCH) {
                    db.stage_cooldown_conflict(group, batch).await?;
                }
                db.activate_cooldown_conflict(group).await?;
                if phase == "handoff" {
                    assert!(!db.drain_cooldown_conflict_batch(group).await?);
                } else {
                    anyhow::ensure!(phase == "active", "invalid process phase");
                }
            }
            std::fs::write(std::env::var("CONFLICT_PROCESS_READY")?, b"committed")?;
            std::future::pending::<()>().await;
            unreachable!();
        }
        anyhow::ensure!(action == "recover", "invalid process action");
        let mut rows = db.conn.query("SELECT id FROM patchsets ORDER BY id", ()).await?;
        let mut ids = Vec::new();
        while let Some(row) = rows.next().await? {
            ids.push(row.get::<i64>(0)?);
        }
        drop(rows);
        assert_eq!(ids.len(), 132);
        let owners: Vec<i64> = ids.iter().enumerate()
            .filter_map(|(index, &id)| (index != 1).then_some(id)).collect();
        if phase == "preparing" {
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflict_members").await?, 64);
            assert_eq!(scalar(&db, "SELECT staged FROM review_cooldown_conflicts").await?, 64);
            for &owner in &owners {
                assert!(!db.cooldown_publication_blocked(owner).await?);
            }
            db.conn.execute(
                "UPDATE review_cooldown_conflicts SET created_at=0,lease_until=0", (),
            ).await?;
            db.recover_cooldown_conflicts().await?;
            for &owner in &owners {
                assert!(!db.cooldown_publication_blocked(owner).await?);
            }
        } else {
            assert_blocked(&db, &owners).await?;
            assert!(db.lock_pending_email().await?.is_none());
            assert!(db.lock_pending_patchwork().await?.is_none());
            assert!(db.lock_pending_forge_outbox().await?.is_none());
        }
        assert!(!db.cooldown_publication_blocked(ids[1]).await?);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflicts").await?, 0);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_conflict_members").await?, 0);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
        assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_messages").await?, 1);
        Ok(())
    }
