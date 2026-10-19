
    async fn det6_make_reviewed_owner(
        db: &Arc<Database>, author: &str, findings: bool,
    ) -> Result<(i64, i64)> {
        let mut result = (0, 0);
        let content = "Signed-off-by: Fixture <fixture@example.test>\n---\ndiff";
        for token in ["prior", "target"] {
            let message = format!("det6-route-{token}@example.test");
            let subject = format!("[PATCH] det6-route-{token}");
            let thread = db.create_thread(&message, &subject, 1).await?;
            db.create_message(&message, thread, None, author, &subject, 1,
                content,
                "list@example.test, Person <person@example.test>", "person@example.test, bot@example.test",
                None, Some("test.list")).await?;
            let hash: String = db.conn.query("SELECT cooldown_source_hash FROM messages WHERE message_id=?",
                libsql::params![message.clone()]).await?.next().await?.context("hash")?.get(0)?;
            let active = db.with_cooldown_context(Some(crate::cooldown::CooldownContext {
                list: "list@example.test".into(), author: crate::cooldown::author_key(author)?,
                policy: crate::cooldown::CooldownPolicy {window_seconds: 3600, burst: 1, step_seconds: 3600, max_extra_seconds: 3600},
                legacy_deadline: None,
                source_snapshot: Some(crate::cooldown::SourceSnapshot {message_id: message.clone(), fingerprint: hash}),
            }));
            let id = active.create_patchset(thread, Some(&message), &message, &subject, author,
                1, 1, 3, "list@example.test, Person <person@example.test>", "person@example.test, bot@example.test",
                None, 1, None, true, None, None).await?.context("owner")?;
            let patch = active.create_patch(id, &message, 1, content).await?;
            if token == "prior" {
                db.update_patchset_status(id, "Cancelled").await?;
            } else {
                let review = db.create_review(id, Some(patch), "fixture", "no-model", None, None).await?;
                db.complete_review(review, "Reviewed", "DET6_HELD_CONTENT_CANARY",
                    Some("fixture summary"), None, Some("DET6_HELD_CONTENT_CANARY"),
                    Some("DET6_PRIVATE_LOG_CANARY")).await?;
                if findings {
                    db.create_finding(Finding {review_id: review, severity: Severity::High,
                        severity_explanation: None, problem: "DET6_HELD_CONTENT_CANARY".into(),
                        preexisting: Some(false), locations: None}).await?;
                }
                db.update_patch_status(patch, "Reviewed").await?;
                db.update_patchset_status(id, "Reviewed").await?;
                result = (id, patch);
            }
        }
        Ok(result)
    }


    struct Det6ProviderDrop(Arc<std::sync::atomic::AtomicBool>);
    impl Drop for Det6ProviderDrop {
        fn drop(&mut self) { self.0.store(true, Ordering::SeqCst); }
    }
    struct Det6BlockedProvider {
        started: Arc<tokio::sync::Notify>,
        dropped: Arc<std::sync::atomic::AtomicBool>,
        calls: Arc<AtomicUsize>,
    }
    #[async_trait]
    impl AiProvider for Det6BlockedProvider {
        async fn generate_content(&self, _request: AiRequest) -> Result<AiResponse> {
            let _guard = Det6ProviderDrop(self.dropped.clone());
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.started.notify_one();
            std::future::pending::<Result<AiResponse>>().await
        }
        fn get_capabilities(&self) -> ProviderCapabilities {
            ProviderCapabilities { model_name: "local-deterministic-mock".into(), context_window_size: 1000 }
        }
    }
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn test_det6_cancel_active_review_reaps_child_and_provider() -> Result<()> {
        let directory = tempdir()?;
        let mut settings = Settings::new()?;
        settings.database.url = ":memory:".into();
        settings.review.timeout_seconds = 60;
        settings.review.max_retries = 0;
        settings.ai.no_ai = false; // The provider below is an in-process mock.
        let db = Arc::new(Database::new(&settings.database).await?);
        db.migrate().await?;
        let (id, patch) = det6_make_reviewed_owner(&db, "dev@example.test", true).await?;
        db.update_patchset_status(id, ReviewStatus::InReview.as_str()).await?;
        db.update_patch_status(patch, ReviewStatus::InReview.as_str()).await?;
        let review = db.create_review(id, Some(patch), "mock", "no-network", None, None).await?;
        let snapshot_sql = "SELECT json_array(admitted_at,prior_count,extra_seconds,decided_deadline,released_at) FROM review_cooldown_intents WHERE patchset_id=?";
        let before: String = db.conn.query(snapshot_sql, libsql::params![id]).await?
            .next().await?.context("snapshot")?.get(0)?;
        let script = directory.path().join("blocked-review.py");
        let pid_file = directory.path().join("worker.pid");
        std::fs::write(&script, r#"import json,os,pathlib,sys,time
sys.stdin.readline()
pathlib.Path(sys.argv[1]).write_text(str(os.getpid()))
print(json.dumps({"type":"ai_request","tx_id":1,"payload":{"messages":[]}}), flush=True)
time.sleep(600)
"#)?;
        let started = Arc::new(tokio::sync::Notify::new());
        let dropped = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let calls = Arc::new(AtomicUsize::new(0));
        let provider = Arc::new(Det6BlockedProvider {started: started.clone(), dropped: dropped.clone(), calls: calls.clone()});
        let permits = Arc::new(Semaphore::new(1));
        let child_permits = permits.clone();
        let child_db = db.clone();
        let child_script = script.clone();
        let child_pid = pid_file.clone();
        let mut task = tokio::spawn(async move {
            let mut cmd = Command::new("/usr/bin/python3");
            cmd.arg(&child_script).arg(&child_pid);
            run_review_tool_with_cmd(cmd, id, &serde_json::json!({"patchset_id":id,"patches":[]}),
                &settings, child_db, "", Some(1), None, Arc::new(QuotaManager::new()),
                review, None, provider, child_permits).await
        });
        let ready = tokio::time::timeout(std::time::Duration::from_secs(5), started.notified()).await;
        if ready.is_err() {
            task.abort();
            let _ = task.await;
            return Err(anyhow!("mock request never started"));
        }
        assert_eq!(calls.load(Ordering::SeqCst), 1);
        assert_eq!(permits.available_permits(), 0);
        let pid: u32 = std::fs::read_to_string(&pid_file)?.parse()?;
        db.update_patchset_status(id, ReviewStatus::Cancelled.as_str()).await?;
        let result = tokio::time::timeout(std::time::Duration::from_secs(8), &mut task).await;
        let result = match result {
            Ok(result) => result?,
            Err(_) => {
                task.abort();
                let _ = task.await;
                return Err(anyhow!("active review cancellation did not finish"));
            }
        };
        let error = result.expect_err("cancelled worker returned a completed review");
        assert!(error.downcast_ref::<ReviewError>().is_some_and(|error| matches!(error, ReviewError::Cancelled)));
        let dropped_result = tokio::time::timeout(std::time::Duration::from_secs(2), async {
            while !dropped.load(Ordering::SeqCst) || permits.available_permits() != 1 {
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        }).await;
        if dropped_result.is_err() {
            return Err(anyhow!("mock provider task remained active after cancellation"));
        }
        assert_eq!(permits.available_permits(), 1);
        tokio::time::timeout(std::time::Duration::from_secs(5), async {
            loop {
                match std::fs::metadata(format!("/proc/{pid}")) {
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound => break Ok::<(), anyhow::Error>(()),
                    Err(error) => break Err(error.into()),
                    Ok(_) => tokio::time::sleep(std::time::Duration::from_millis(10)).await,
                }
            }
        }).await??;
        assert_eq!(db.get_patchset_status(id).await?.as_deref(), Some(ReviewStatus::Cancelled.as_str()));
        assert!(!db.get_releasable_embargoed_patchsets(chrono::Utc::now().timestamp()+7200, 10).await?.iter().any(|p|p.id == id));
        let after: String = db.conn.query(snapshot_sql, libsql::params![id]).await?
            .next().await?.context("post-cancellation snapshot")?.get(0)?;
        assert_eq!(before, after);
        let outbox: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox", ()).await?
            .next().await?.context("outbox count")?.get(0)?;
        assert_eq!(outbox, 0);
        println!("DET6_CASES active_review_cancel=1 child_reaped=1 mock_future_dropped=1 permit_restored=1 frozen_decision=1");
        Ok(())
    }
