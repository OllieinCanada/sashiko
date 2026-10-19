
    mod hosted_concurrency {
        use super::*;
        #[tokio::test(flavor = "multi_thread", worker_threads = 8)]
        #[ignore = "hosted sixteen independent SQLite writers"]
        async fn test_cooldown_sixteen_writers_replay_release() -> Result<()> {
            let directory = tempfile::tempdir()?;
            let settings = DatabaseSettings {
                url: directory.path().join("concurrent.db").to_string_lossy().into_owned(),
                token: String::new(),
            };
            let initial = Database::new(&settings).await?;
            initial.migrate().await?;
            let mut workers = Vec::new();
            for worker in 0..16 {
                let db = Database::new(&settings).await?;
                let list = format!("list{}@example.test", worker / 4 % 2);
                let author = format!("dev{}@example.test", worker % 4);
                let mut ctx = context(&list, &author);
                ctx.policy.burst = 1;
                let active = db.with_cooldown_context(Some(ctx));
                let mut inputs = Vec::new();
                for sequence in 0..8 {
                    let (id, _, message) = seed(&active, &format!("writer-{worker}-{sequence}"), 1).await?;
                    inputs.push((id, message));
                }
                workers.push((active, inputs));
            }
            let barrier = Arc::new(tokio::sync::Barrier::new(16));
            let mut tasks = tokio::task::JoinSet::new();
            let started = std::time::Instant::now();
            for (active, inputs) in workers {
                let barrier = barrier.clone();
                tasks.spawn(async move {
                    barrier.wait().await;
                    for (sequence, (id, message)) in inputs.into_iter().enumerate() {
                        active.create_patch(id, &message, 1, "diff").await?;
                        if sequence % 2 == 0 {
                            active.release_patchset_embargo(id, chrono::Utc::now().timestamp()).await?;
                        }
                        let snapshot = "SELECT json_array(c.admitted_at,c.prior_count,c.extra_seconds,c.decided_deadline,c.released_at,p.embargo_until) FROM review_cooldown_intents c JOIN patchsets p ON p.id=c.patchset_id WHERE p.id=?";
                        let before: String = active.conn.query(snapshot, libsql::params![id]).await?
                            .next().await?.context("missing concurrent decision")?.get(0)?;
                        active.with_cooldown_context(None).create_patch(id, &message, 1, "diff").await?;
                        let after: String = active.conn.query(snapshot, libsql::params![id]).await?
                            .next().await?.context("missing concurrent replay")?.get(0)?;
                        anyhow::ensure!(before == after, "concurrent replay changed frozen decision");
                    }
                    Ok::<(), anyhow::Error>(())
                });
            }
            tokio::time::timeout(std::time::Duration::from_secs(60), async {
                while let Some(result) = tasks.join_next().await { result??; }
                Ok::<(), anyhow::Error>(())
            }).await??;
            assert_eq!(scalar(&initial, "SELECT COUNT(*) FROM review_cooldown_events").await?, 128);
            assert_eq!(scalar(&initial, "SELECT COUNT(*) FROM patches").await?, 128);
            assert_eq!(scalar(&initial, "SELECT COUNT(*) FROM review_cooldown_intents WHERE state='decided'").await?, 128);
            assert_eq!(scalar(&initial, "SELECT COUNT(*) FROM review_cooldown_intents WHERE released_at IS NOT NULL").await?, 64);
            let mut groups = initial.conn.query(
                "SELECT list,author,COUNT(*),SUM(prior_count=0),SUM(prior_count=1),SUM(prior_count=2),SUM(prior_count=3) FROM review_cooldown_intents GROUP BY list,author", ()).await?;
            let mut scopes = 0;
            while let Some(row) = groups.next().await? {
                scopes += 1;
                assert_eq!(row.get::<i64>(2)?, 16);
                for column in 3..=5 { assert_eq!(row.get::<i64>(column)?, 1); }
                assert_eq!(row.get::<i64>(6)?, 13);
            }
            assert_eq!(scopes, 8);
            println!("CONCURRENCY writers=16 admissions=128 replays=128 releases=64 seconds={}", started.elapsed().as_secs_f64());
            Ok(())
        }
    }
