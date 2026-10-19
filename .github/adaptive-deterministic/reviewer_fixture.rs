
    async fn det6_make_reviewed_owner(
        db: &Arc<Database>, author: &str, findings: bool,
    ) -> Result<(i64, i64)> {
        let mut result = (0, 0);
        for token in ["prior", "target"] {
            let message = format!("det6-route-{token}@example.test");
            let subject = format!("[PATCH] det6-route-{token}");
            let thread = db.create_thread(&message, &subject, 1).await?;
            db.create_message(&message, thread, None, author, &subject, 1,
                "Signed-off-by: Fixture <fixture@example.test>\n---\ndiff",
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
            let patch = active.create_patch(id, &message, 1, "diff").await?;
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

    #[tokio::test]
    async fn test_det6_enabled_routing_and_integration_matrix() -> Result<()> {
        // Expectations are literal policy outcomes, independent of the router.
        let cases = [
            ("all", "\"author\", \"list\", \"recipients\"", false, "none", true, 1, false, false, false, "Pending", vec!["dev@example.test","list@example.test","person@example.test"], vec!["static@example.test"]),
            ("author", "\"author\"", false, "none", true, 1, false, false, false, "Pending", vec!["dev@example.test"], vec!["static@example.test"]),
            ("list", "\"list\"", false, "none", true, 1, false, false, false, "Pending", vec!["list@example.test"], vec!["static@example.test"]),
            ("recipients", "\"recipients\"", false, "none", true, 1, false, false, false, "Pending", vec!["person@example.test"], vec!["static@example.test"]),
            ("empty", "", false, "none", true, 1, false, false, false, "Muted", vec![], vec![]),
            ("mute", "\"author\"", true, "none", true, 1, false, false, false, "Muted", vec![], vec![]),
            ("ignored", "\"author\"", false, "none", true, 1, true, false, false, "Muted", vec![], vec![]),
            ("self", "\"author\"", false, "none", true, 1, false, true, false, "Muted", vec![], vec![]),
            ("disabled-smtp", "\"author\"", false, "none", true, 0, false, false, false, "Disabled", vec!["dev@example.test"], vec!["static@example.test"]),
            ("dry-run", "\"author\"", false, "none", true, 2, false, false, false, "Dry-Run", vec!["dev@example.test"], vec!["static@example.test"]),
            ("positive-none", "\"author\", \"list\", \"recipients\"", false, "none", false, 1, false, false, false, "Skipped", vec![], vec![]),
            ("positive-author", "\"author\", \"list\", \"recipients\"", false, "author", false, 1, false, false, false, "Pending", vec!["dev@example.test"], vec![]),
            ("positive-all", "\"author\", \"list\", \"recipients\"", false, "all", false, 1, false, false, false, "Pending", vec!["dev@example.test","list@example.test","person@example.test"], vec!["static@example.test"]),
            ("patchwork", "\"author\"", false, "none", true, 1, false, false, true, "Pending", vec!["dev@example.test"], vec!["static@example.test"]),
            ("ignored-patchwork", "\"author\"", false, "none", true, 1, true, false, true, "Muted", vec![], vec![]),
            ("muted-patchwork", "\"author\"", true, "none", true, 1, false, false, true, "Muted", vec![], vec![]),
        ];
        for (label, targets, mute, positive, findings, smtp_mode, ignored, self_author, patchwork, status, expected_to, expected_cc) in cases {
            let directory = tempdir()?;
            let policy_path = directory.path().join("lists.toml");
            let static_cc = if label == "empty" { "" } else { "\"static@example.test\"" };
            let ignored_address = if ignored { "\"dev@example.test\"" } else { "" };
            std::fs::write(&policy_path, format!(r#"
[defaults]
cc = [{static_cc}]
["list@example.test"]
nntp_group = "test.list"
reply_to = [{targets}]
positive_review = "{positive}"
mute_all = {mute}
ignored_emails = [{ignored_address}]
["list@example.test".adaptive_cooldown]
enabled = true
window_seconds = 3600
burst = 1
step_seconds = 3600
max_extra_seconds = 3600
["list@example.test".patchwork]
enabled = {patchwork}
api_url = "https://patchwork.example.test/api"
email = "checks@example.test"
token = "DET6_FAKE_CREDENTIAL_CANARY"
"#))?;
            let mut settings = Settings::new()?;
            settings.database.url = ":memory:".into();
            settings.git.repository_path = directory.path().to_string_lossy().into_owned();
            settings.review.worktree_dir = Some(directory.path().join("worktrees").to_string_lossy().into_owned());
            settings.review.email_policy_path = policy_path.to_string_lossy().into_owned();
            settings.ai.provider = "stdio-gemini".into();
            settings.ai.no_ai = true;
            settings.ai.response_cache = false;
            settings.smtp = (smtp_mode != 0).then(|| crate::settings::SmtpSettings {
                transport: crate::settings::MailTransport::Sendmail, server: None, port: None,
                username: None, password: None, sendmail_path: Some("/no-external-transport".into()),
                sender_address: "bot@example.test".into(), reply_to: None, dry_run: smtp_mode == 2,
            });
            let db = Arc::new(Database::new(&settings.database).await?);
            db.migrate().await?;
            let author = if self_author { "bot@example.test" } else { "dev@example.test" };
            let (id, patch) = det6_make_reviewed_owner(&db, author, findings).await?;
            let mut rows = db.conn.query("SELECT prior_count,extra_seconds,decided_deadline,admitted_at FROM review_cooldown_intents WHERE patchset_id=?", libsql::params![id]).await?;
            let row = rows.next().await?.context("decision")?;
            assert_eq!(row.get::<i64>(0)?, 1, "{label}");
            assert_eq!(row.get::<i64>(1)?, 3600, "{label}");
            assert_eq!(row.get::<i64>(2)? - row.get::<i64>(3)?, 3600, "{label}");
            let reviewer = Reviewer::new(db.clone(), settings).await;
            if findings {
                reviewer.release_embargoed_results().await?;
                let queued: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox", ()).await?.next().await?.context("early")?.get(0)?;
                assert_eq!(queued, 0, "{label}: publication before release");
                assert!(db.lock_pending_patchwork().await?.is_none());
            }
            // Authorized release is separate from message-controlled routing.
            assert!(db.release_patchset_embargo(id, chrono::Utc::now().timestamp()).await?);
            reviewer.release_embargoed_results().await?;
            let mut rows = db.conn.query("SELECT status,to_addresses,cc_addresses,body FROM email_outbox WHERE patch_id=?", libsql::params![patch]).await?;
            let row = rows.next().await?.context("review notification")?;
            assert_eq!(row.get::<String>(0)?, status, "{label}");
            for (column, expected) in [(1, expected_to), (2, expected_cc)] {
                let raw: Vec<String> = serde_json::from_str(&row.get::<String>(column)?)?;
                let mut actual: Vec<String> = raw.into_iter().map(|address| {
                    address.parse::<lettre::message::Mailbox>().unwrap().email.to_string()
                }).collect();
                actual.sort();
                let mut expected: Vec<String> = expected.into_iter().map(str::to_string).collect();
                expected.sort();
                assert_eq!(actual, expected, "{label}: recipient column={column}");
            }
            assert!(!row.get::<String>(3)?.contains("DET6_FAKE_CREDENTIAL_CANARY"));
            assert!(rows.next().await?.is_none(), "{label}: duplicate review email");
            let api: i64 = db.conn.query("SELECT COUNT(*) FROM patchwork_outbox", ()).await?.next().await?.context("api")?.get(0)?;
            let email: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox WHERE patch_id IS NULL", ()).await?.next().await?.context("patchwork email")?.get(0)?;
            let expected_integrations = i64::from(patchwork && !ignored);
            assert_eq!(api, expected_integrations, "{label}");
            assert_eq!(email, expected_integrations, "{label}");
            let bodies: String = db.conn.query("SELECT coalesce(group_concat(body,''),'') FROM email_outbox", ()).await?.next().await?.context("bodies")?.get(0)?;
            assert!(!bodies.contains("DET6_FAKE_CREDENTIAL_CANARY"));
            reviewer.release_embargoed_results().await?;
            let duplicate: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox WHERE patch_id=?", libsql::params![patch]).await?.next().await?.context("dedup")?.get(0)?;
            assert_eq!(duplicate, 1, "{label}");
        }
        println!("DET6_CASES notification_policy=16 earned_hold_each=3600");
        Ok(())
    }
