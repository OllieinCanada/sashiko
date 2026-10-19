
    mod hosted_observability_controls {
        use super::*;
        use crate::db::hosted_probe as probe;
        #[tokio::test]
        #[ignore = "hosted SQL counter calibration"]
        async fn test_probe_sql_counter_calibration() -> Result<()> {
            let db = database().await?;
            probe::reset();
            let tx = db.begin_immediate_transaction().await?;
            let mut rows = tx.query("SELECT 1", ()).await?;
            assert_eq!(rows.next().await?.context("missing calibration row")?.get::<i64>(0)?, 1);
            drop(rows);
            tx.execute("UPDATE meta SET value=value WHERE key='probe-nonexistent'", ()).await?;
            tx.rollback().await?;
            let result = probe::finish();
            assert_eq!(result["sql_api_calls"]["query"], 1);
            assert_eq!(result["sql_api_calls"]["execute"], 2);
            assert_eq!(result["sql_api_calls"]["execute_batch"], 0);
            assert_eq!(result["begin_immediate_success"], 1);
            assert_eq!(result["timings"]["explicit_transaction_hold"]["count"], 1);
            println!("PROBE_CONTROL {}", result);
            Ok(())
        }
        #[tokio::test]
        #[ignore = "hosted deliberate contention calibration"]
        async fn test_probe_mutex_and_hold_calibration() -> Result<()> {
            let db = database().await?;
            probe::reset();
            let first = db.begin_immediate_transaction().await?;
            let second = db.begin_immediate_transaction();
            tokio::pin!(second);
            tokio::select! {
                _ = &mut second => anyhow::bail!("contender escaped the held writer mutex"),
                _ = tokio::time::sleep(std::time::Duration::from_millis(100)) => {}
            }
            first.rollback().await?;
            second.await?.rollback().await?;
            let result = probe::finish();
            assert_eq!(result["begin_immediate_success"], 2);
            assert_eq!(result["timings"]["explicit_transaction_hold"]["count"], 2);
            assert!(result["timings"]["transaction_mutex_wait"]["max_ns"].as_u64().context("missing wait")? >= 80_000_000);
            assert!(result["timings"]["explicit_transaction_hold"]["max_ns"].as_u64().context("missing hold")? >= 80_000_000);
            println!("PROBE_CONTROL {}", result);
            Ok(())
        }
        #[tokio::test]
        #[ignore = "hosted stalled collaborator outside writer lane"]
        async fn test_probe_paused_collaborator_allows_independent_admission() -> Result<()> {
            let db = database().await?;
            let active = db.with_cooldown_context(Some(context("list@example.test", "dev@example.test")));
            let (slow_id, _, slow_msg) = seed(&active, "paused-slow", 1).await?;
            let (fast_id, _, fast_msg) = seed(&active, "paused-fast", 1).await?;
            let gate = tokio::sync::Notify::new();
            let slow = async {
                gate.notified().await;
                active.create_patch(slow_id, &slow_msg, 1, "diff").await
            };
            tokio::pin!(slow);
            tokio::select! {
                _ = &mut slow => anyhow::bail!("paused collaborator advanced without a permit"),
                _ = tokio::time::sleep(std::time::Duration::from_millis(20)) => {}
            }
            probe::reset();
            tokio::time::timeout(std::time::Duration::from_secs(5),
                active.create_patch(fast_id, &fast_msg, 1, "diff")).await??;
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 1);
            assert_eq!(scalar(&db, &format!("SELECT prior_count FROM review_cooldown_intents WHERE patchset_id={fast_id}")).await?, 0);
            gate.notify_one();
            tokio::time::timeout(std::time::Duration::from_secs(5), slow).await??;
            let result = probe::finish();
            assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, 2);
            assert_eq!(scalar(&db, &format!("SELECT prior_count FROM review_cooldown_intents WHERE patchset_id={slow_id}")).await?, 1);
            println!("PROBE_CONTROL {}", result);
            Ok(())
        }
    }
