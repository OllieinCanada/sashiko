    #[cfg(feature = "server")]
    #[tokio::test]
    async fn test_det6_actual_wall_clock_jumps_preserve_publication() -> anyhow::Result<()> {
        use anyhow::Context as _;
        use sashiko::db::{Finding, Severity};
        use sashiko::settings::{DatabaseSettings, MailTransport, SmtpSettings};
        let clock_path = std::path::PathBuf::from(std::env::var("SASHIKO_TEST_REALTIME_FILE")?);
        let probe_path = std::path::PathBuf::from(std::env::var("SASHIKO_TEST_RELEASE_PROBE")?);
        let set_clock = |seconds: i64| -> anyhow::Result<()> {
            let next = clock_path.with_extension("next");
            std::fs::write(&next, seconds.to_string())?;
            std::fs::rename(next, &clock_path)?;
            assert_eq!(chrono::Utc::now().timestamp(), seconds, "chrono bypassed wall-clock shim");
            assert_eq!(std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH)?.as_secs(), seconds as u64);
            Ok(())
        };
        async fn await_selector(path: &std::path::Path, instant: i64, count: usize) -> anyhow::Result<()> {
            tokio::time::timeout(std::time::Duration::from_secs(5), async {
                loop {
                    if let Ok(value) = std::fs::read_to_string(path)
                        && value.starts_with(&format!("{instant}:")) {
                        assert_eq!(value, format!("{instant}:{count}"));
                        break;
                    }
                    tokio::time::sleep(std::time::Duration::from_millis(10)).await;
                }
            }).await?;
            Ok(())
        }
        set_clock(2_000_000_000)?;
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
        let mut held_raw = String::new();
        for token in ["prior", "held"] {
            let raw = format!(
                "Message-ID: <{token}@example.test>\r\nFrom: Dev <dev@example.test>\r\nTo: list@example.test\r\nSubject: [PATCH] {token}\r\nDate: Thu, 1 Jan 1970 00:00:00 +0000\r\n\r\nSigned-off-by: Dev <dev@example.test>\r\n---\r\ndiff --git a/f b/f\r\n--- a/f\r\n+++ b/f\r\n@@ -1 +1 @@\r\n-old\r\n+new\r\n"
            );
            if token == "held" { held_raw = raw.clone(); }
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
        let deadline: i64 = db.conn.query("SELECT embargo_until FROM patchsets WHERE id=?", libsql::params![target])
            .await?.next().await?.context("deadline")?.get(0)?;
        assert_eq!(deadline, 2_000_003_600);
        let frozen: String = db.conn.query("SELECT json_array(admitted_at,prior_count,extra_seconds,decided_deadline) FROM review_cooldown_intents WHERE patchset_id=?",
            libsql::params![target]).await?.next().await?.context("frozen")?.get(0)?;

        let capture = directory.path().join("accepted.eml");
        let source_script = directory.path().join("sendmail.source");
        let sendmail = directory.path().join("sendmail");
        let quoted = capture.to_string_lossy().replace('\'', "'\\''");
        std::fs::write(&source_script, format!("#!/bin/sh\ncat >> '{quoted}'\n"))?;
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
        for instant in [2_000_003_599_i64, 1_999_999_000] {
            set_clock(instant)?;
            let early = sashiko::reviewer::Reviewer::new(db.clone(), settings.clone()).await;
            let early = tokio::spawn(async move { early.start().await });
            let observed = await_selector(&probe_path, instant, 0).await;
            early.abort();
            assert!(early.await.unwrap_err().is_cancelled());
            observed?;
            let count: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox", ()).await?
                .next().await?.context("early outbox")?.get(0)?;
            assert_eq!(count, 0, "wall-clock jump released findings early");
        }
        set_clock(deadline)?;
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
        await_selector(&probe_path, deadline, 1).await?;
        assert!(!capture.exists());
        let worker = sashiko::worker::email::EmailWorker::new(db.clone(), smtp, false);
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
        let accepted = std::fs::read_to_string(capture)?;
        for instant in [2_500_000_000_i64, 1_999_999_000] {
            set_clock(instant)?;
            let (metadata, patch) = sashiko::patch::parse_email(held_raw.as_bytes())?;
            assert!(matches!(process_parsed_article(&db, ParsedArticle {
                group: "test.list".into(), article_id: "wall-clock-replay".into(),
                source: MessageSource::Nntp, metadata: Some(metadata), patch, baseline: None,
                failed_error: None, skip_filters: None, only_filters: None, mr_url: None,
                mr_title: None, mr_number: None, receipt: None,
            }, None, &policy, &[]).await, ProcessStatus::Ingested));
            let replay = sashiko::reviewer::Reviewer::new(db.clone(), settings.clone()).await;
            let replay = tokio::spawn(async move { replay.start().await });
            let observed = await_selector(&probe_path, instant, 0).await;
            replay.abort();
            assert!(replay.await.unwrap_err().is_cancelled());
            observed?;
            let count: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox", ()).await?
                .next().await?.context("replay outbox")?.get(0)?;
            assert_eq!(count, 1, "replay duplicated notification after clock jump");
            let after: String = db.conn.query("SELECT json_array(admitted_at,prior_count,extra_seconds,decided_deadline) FROM review_cooldown_intents WHERE patchset_id=?",
                libsql::params![target]).await?.next().await?.context("post-jump snapshot")?.get(0)?;
            assert_eq!(after, frozen);
            let embargo: Option<i64> = db.conn.query("SELECT embargo_until FROM patchsets WHERE id=?", libsql::params![target])
                .await?.next().await?.context("embargo")?.get(0)?;
            assert!(embargo.is_none(), "backward clock re-held a published review");
        }
        println!("DET6_CASES real_wall_clock_states=6 natural_deadline_release=1 replay_jumps=2");
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
