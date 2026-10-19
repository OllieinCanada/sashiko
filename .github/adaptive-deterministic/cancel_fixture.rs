    #[tokio::test]
    async fn test_det6_abort_adaptive_transport_then_recover() -> anyhow::Result<()> {
        use anyhow::Context as _;
        use sashiko::db::{Finding, Severity};
        use sashiko::settings::{DatabaseSettings, MailTransport, SmtpSettings};
        let directory = tempfile::tempdir()?;
        let policy_path = directory.path().join("mailing_lists.toml");
        std::fs::write(
            &policy_path,
            r#"
["list@example.test"]
nntp_group = "test.list"
reply_to = ["author"]
embargo_hours = 0
["list@example.test".adaptive_cooldown]
enabled = true
window_seconds = 86400
burst = 1
step_seconds = 3600
max_extra_seconds = 3600
"#,
        )?;
        let policy = sashiko::email_policy::EmailPolicyConfig::load(&policy_path)?;
        let db = Arc::new(
            Database::new(&DatabaseSettings {
                url: directory
                    .path()
                    .join("fixture.db")
                    .to_string_lossy()
                    .into_owned(),
                token: String::new(),
            })
            .await?,
        );
        db.migrate().await?;
        let mut target = 0;
        let mut target_patch = 0;
        for token in ["prior", "held"] {
            let raw = format!(
                "Message-ID: <{token}@example.test>\r\nFrom: Dev <dev@example.test>\r\nTo: list@example.test\r\nSubject: [PATCH] {token}\r\nDate: Thu, 1 Jan 1970 00:00:00 +0000\r\n\r\nSigned-off-by: Dev <dev@example.test>\r\n---\r\ndiff --git a/f b/f\r\n--- a/f\r\n+++ b/f\r\n@@ -1 +1 @@\r\n-old\r\n+new\r\n"
            );
            let (metadata, patch) = sashiko::patch::parse_email(raw.as_bytes())?;
            let article = ParsedArticle {
                group: "test.list".into(),
                article_id: token.into(),
                source: MessageSource::Nntp,
                metadata: Some(metadata),
                patch,
                baseline: None,
                failed_error: None,
                skip_filters: None,
                only_filters: None,
                mr_url: None,
                mr_title: None,
                mr_number: None,
                receipt: None,
            };
            assert!(matches!(
                process_parsed_article(&db, article, None, &policy, &[]).await,
                ProcessStatus::Ingested
            ));
            let mut rows = db.conn.query("SELECT p.id, ps.id FROM patches p JOIN patchsets ps ON ps.id = p.patchset_id WHERE p.message_id = ?", libsql::params![format!("{token}@example.test")]).await?;
            let row = rows.next().await?.context("ingestion did not save patch")?;
            target_patch = row.get(0)?;
            target = row.get(1)?;
            if token == "prior" {
                db.update_patchset_status(target, "Cancelled").await?;
            }
        }
        let review = db
            .create_review(
                target,
                Some(target_patch),
                "recording-fixture",
                "no-model-call",
                None,
                None,
            )
            .await?;
        db.complete_review(
            review,
            "Reviewed",
            "Complete fixture output",
            Some("fixture finding"),
            None,
            Some("fixture inline review"),
            None,
        )
        .await?;
        db.create_finding(Finding {
            review_id: review,
            severity: Severity::Low,
            severity_explanation: None,
            problem: "fixture finding".into(),
            preexisting: Some(false),
            locations: None,
        })
        .await?;
        db.update_patch_status(target_patch, "Reviewed").await?;
        db.update_patchset_status(target, "Reviewed").await?;
        let now = chrono::Utc::now().timestamp();
        assert!(
            db.get_releasable_embargoed_patchsets(now, 10)
                .await?
                .is_empty()
        );
        assert!(!db.claim_patchset_embargo_release(target, now).await?);
        assert!(db.lock_pending_email().await?.is_none());
        let hidden = db
            .get_patchset_details(target, None, None)
            .await?
            .context("missing details")?;
        assert_eq!(hidden["status"], "Embargoed");
        assert_eq!(
            hidden["reviews"]
                .as_array()
                .context("missing reviews")?
                .len(),
            0
        );
        assert!(db.release_patchset_embargo(target, now).await?);

        let capture = directory.path().join("accepted.eml");
        let source_script = directory.path().join("sendmail.source");
        let sendmail = directory.path().join("sendmail");
        let entered = directory.path().join("entered");
        let gate = directory.path().join("gate");
        let pid_file = directory.path().join("pid");
        let attempts = directory.path().join("attempts");
        std::fs::write(&source_script, format!(
            "#!/usr/bin/env python3\nimport os,pathlib,sys,time\npathlib.Path({pid_file:?}).write_text(str(os.getpid()))\nwith open({attempts:?},'a') as f:f.write('attempt\\n')\npathlib.Path({entered:?}).write_text('entered')\nwhile not pathlib.Path({gate:?}).exists():time.sleep(0.02)\nwith open({capture:?},'a') as f:f.write(sys.stdin.read())\n"
        ))?;
        assert!(
            std::process::Command::new("install")
                .arg("-m")
                .arg("755")
                .arg(&source_script)
                .arg(&sendmail)
                .status()?
                .success()
        );
        let smtp = SmtpSettings {
            transport: MailTransport::Sendmail,
            server: None,
            port: None,
            username: None,
            password: None,
            sendmail_path: Some(sendmail.to_string_lossy().into_owned()),
            sender_address: "bot@example.test".into(),
            reply_to: None,
            dry_run: false,
        };
        let mut settings = Settings::new()?;
        settings.database = DatabaseSettings {
            url: directory
                .path()
                .join("fixture.db")
                .to_string_lossy()
                .into_owned(),
            token: String::new(),
        };
        settings.review.email_policy_path = policy_path.to_string_lossy().into_owned();
        settings.review.worktree_dir = Some(
            directory
                .path()
                .join("worktrees")
                .to_string_lossy()
                .into_owned(),
        );
        settings.git.repository_path = directory.path().to_string_lossy().into_owned();
        settings.ai.provider = "stdio-gemini".into(); // Inert: no pending reviews, no model subprocess.
        settings.ai.no_ai = true;
        settings.ai.response_cache = false;
        settings.smtp = Some(smtp.clone());
        let reviewer = sashiko::reviewer::Reviewer::new(db.clone(), settings.clone()).await;
        let release = tokio::spawn(async move { reviewer.start().await });
        let wait_queue = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            loop {
                let mut rows = db
                    .conn
                    .query(
                        "SELECT COUNT(*) FROM email_outbox WHERE status = 'Pending'",
                        (),
                    )
                    .await?;
                if rows
                    .next()
                    .await?
                    .context("missing queue count")?
                    .get::<i64>(0)?
                    == 1
                {
                    break Ok::<(), anyhow::Error>(());
                }
                tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            }
        })
        .await;
        release.abort();
        let _ = release.await;
        wait_queue??;
        assert!(!capture.exists());
        let worker = sashiko::worker::email::EmailWorker::new(db.clone(), smtp.clone(), false);
        let delivery = tokio::spawn(async move { worker.run().await });
        let entry = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            while !entered.exists() {
                tokio::time::sleep(std::time::Duration::from_millis(10)).await;
            }
        }).await;
        if entry.is_err() {
            delivery.abort();
            let _ = delivery.await;
            return Err(anyhow::anyhow!("recording transport never entered"));
        }
        let pid: u32 = std::fs::read_to_string(&pid_file)?.parse()?;
        delivery.abort();
        assert!(delivery.await.unwrap_err().is_cancelled());
        tokio::time::timeout(std::time::Duration::from_secs(5), async {
            loop {
                match std::fs::metadata(format!("/proc/{pid}")) {
                    Err(error) if error.kind() == std::io::ErrorKind::NotFound =>
                        break Ok::<(), anyhow::Error>(()),
                    Err(error) => break Err(error.into()),
                    Ok(_) => {}
                }
                tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            }
        }).await??;
        assert!(!capture.exists(), "cancelled child reached acceptance");
        let sending: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox WHERE status='Sending'", ()).await?
            .next().await?.context("sending count")?.get(0)?;
        assert_eq!(sending, 1);
        let frozen: String = db.conn.query("SELECT json_array(admitted_at,prior_count,extra_seconds,decided_deadline,released_at) FROM review_cooldown_intents WHERE patchset_id=?",
            libsql::params![target]).await?.next().await?.context("frozen decision")?.get(0)?;
        let reopened = Arc::new(Database::new(&settings.database).await?);
        assert_eq!(reopened.sweep_ghost_emails().await?, 0, "fresh lease reclaimed");
        tokio::time::timeout(std::time::Duration::from_secs(5),
            reopened.create_thread("det6-write-after-delivery-abort@example.test", "unrelated", 1)).await??;
        reopened.execute("UPDATE email_outbox SET locked_at=? WHERE status='Sending'",
            libsql::params![chrono::Utc::now().timestamp() - 601]).await?;
        std::fs::write(&gate, "resume")?;
        let worker = sashiko::worker::email::EmailWorker::new(reopened.clone(), smtp, false);
        let delivery = tokio::spawn(async move { worker.run().await });
        let wait_sent = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            loop {
                let mut rows = db
                    .conn
                    .query(
                        "SELECT COUNT(*) FROM email_outbox WHERE status = 'Sent'",
                        (),
                    )
                    .await?;
                if rows
                    .next()
                    .await?
                    .context("missing sent count")?
                    .get::<i64>(0)?
                    == 1
                {
                    break Ok::<(), anyhow::Error>(());
                }
                tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            }
        })
        .await;
        delivery.abort();
        let _ = delivery.await;
        wait_sent??;
        let after: String = reopened.conn.query("SELECT json_array(admitted_at,prior_count,extra_seconds,decided_deadline,released_at) FROM review_cooldown_intents WHERE patchset_id=?",
            libsql::params![target]).await?.next().await?.context("post-recovery decision")?.get(0)?;
        assert_eq!(after, frozen);
        assert_eq!(std::fs::read_to_string(attempts)?.lines().count(), 2);
        let accepted = std::fs::read_to_string(capture)?;
        assert_eq!(accepted.matches("Subject:").count(), 1);
        println!("DET6_CASES transport_abort=1 child_reaped=1 fresh_lease_preserved=1 expired_lease_recovered=1 accepted=1");
        assert!(accepted.contains("dev@example.test"));
        assert!(accepted.contains("fixture finding"));
        let mut count = db
            .conn
            .query("SELECT COUNT(*) FROM review_cooldown_events", ())
            .await?;
        assert_eq!(
            count
                .next()
                .await?
                .context("missing event count")?
                .get::<i64>(0)?,
            2
        );
        Ok(())
    }
