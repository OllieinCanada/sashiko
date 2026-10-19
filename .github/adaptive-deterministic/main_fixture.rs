
    #[cfg(feature = "server")]
    #[tokio::test]
    async fn test_det6_ingestion_crosspost_and_ignore_matrix() -> anyhow::Result<()> {
        use anyhow::Context as _;
        use sashiko::settings::DatabaseSettings;
        let cases = [
            ("single-to", "test.list", "list@example.test", "", MessageSource::Nntp, 1, 0),
            ("single-cc", "unknown", "person@example.test", "List <LIST@EXAMPLE.TEST>", MessageSource::Nntp, 1, 0),
            ("dedup-list", "test.list", "list@example.test", "list@example.test", MessageSource::Nntp, 1, 0),
            ("group-only", "test.list", "person@example.test", "", MessageSource::Nntp, 1, 0),
            ("display-spoof", "unknown", "\"list@example.test\" <person@example.test>", "", MessageSource::Nntp, 0, 0),
            ("two-to", "test.list", "list@example.test, other@example.test", "", MessageSource::Nntp, 0, 0),
            ("two-cc", "unknown", "person@example.test", "list@example.test, other@example.test", MessageSource::Nntp, 0, 0),
            ("reverse-order", "test.other", "other@example.test, list@example.test", "", MessageSource::Nntp, 0, 0),
            ("group-optout", "test.other", "list@example.test", "", MessageSource::Nntp, 0, 0),
            ("single-optout", "test.other", "other@example.test", "", MessageSource::Nntp, 0, 0),
            ("unmatched", "unknown", "person@example.test", "", MessageSource::Nntp, 0, 0),
            ("api-inject", "test.list", "list@example.test", "", MessageSource::ApiInject, 0, 0),
            ("api-thread", "test.list", "list@example.test", "", MessageSource::ApiFetchThread, 0, 0),
            ("git-fetch", "test.list", "list@example.test", "", MessageSource::GitFetch, 0, 0),
            ("git-import", "test.list", "list@example.test", "", MessageSource::GitImport, 0, 0),
            ("git-archive", "test.list", "list@example.test", "", MessageSource::GitArchive, 0, 0),
            ("ignored-global", "test.list", "list@example.test", "", MessageSource::Nntp, 0, 1),
            ("ignored-list", "test.list", "list@example.test", "", MessageSource::Nntp, 0, 2),
            ("ignored-other-list", "test.list", "list@example.test", "", MessageSource::Nntp, 0, 3),
        ];
        for (label, group, to, cc, source, expected_events, ignored) in cases {
            let mut policy = sashiko::email_policy::EmailPolicyConfig::parse_content(r#"
["list@example.test"]
nntp_group = "test.list"
reply_to = ["author", "list", "recipients"]
["list@example.test".adaptive_cooldown]
enabled = true
window_seconds = 3600
burst = 1
step_seconds = 30
max_extra_seconds = 60
["other@example.test"]
nntp_group = "test.other"
["other@example.test".adaptive_cooldown]
enabled = false
"#)?;
            match ignored {
                1 => policy.defaults.ignored_emails.push("DEV@example.test".into()),
                2 => policy.lists.get_mut("list@example.test").unwrap().ignored_emails.push("dev@example.test".into()),
                3 => policy.lists.get_mut("other@example.test").unwrap().ignored_emails.push("dev@example.test".into()),
                _ => {}
            }
            let db = Database::new(&DatabaseSettings {url: ":memory:".into(), token: String::new()}).await?;
            db.migrate().await?;
            let raw = format!(
                "Message-ID: <det6-{label}@example.test>\r\nFrom: Dev <dev@example.test>\r\nTo: {to}\r\nCc: {cc}\r\nSubject: [PATCH] det6-{label}\r\nDate: Thu, 1 Jan 1970 00:00:00 +0000\r\n\r\nSigned-off-by: Dev <dev@example.test>\r\n---\r\ndiff --git a/f b/f\r\n--- a/f\r\n+++ b/f\r\n@@ -1 +1 @@\r\n-old\r\n+new\r\n"
            );
            for replay in 0..2 {
                let (metadata, patch) = sashiko::patch::parse_email(raw.as_bytes())?;
                let outcome = process_parsed_article(&db, ParsedArticle {
                    group: group.into(), article_id: format!("det6-{label}-{replay}"),
                    source, metadata: Some(metadata), patch, baseline: None, failed_error: None,
                    skip_filters: None, only_filters: None, mr_url: None, mr_title: None,
                    mr_number: None, receipt: None,
                }, None, &policy, &[]).await;
                assert!(matches!(outcome, ProcessStatus::Ingested), "{label}/{replay}");
            }
            for table in ["review_cooldown_events", "review_cooldown_intents"] {
                let sql = format!("SELECT COUNT(*) FROM {table}");
                let count: i64 = db.conn.query(&sql, ()).await?.next().await?.context("count")?.get(0)?;
                assert_eq!(count, expected_events, "{label}/{table}");
            }
            let patches: i64 = db.conn.query("SELECT COUNT(*) FROM patches", ()).await?
                .next().await?.context("patch count")?.get(0)?;
            assert_eq!(patches, i64::from(ignored == 0), "{label}");
            let messages: i64 = db.conn.query("SELECT COUNT(*) FROM messages WHERE is_placeholder = 0", ()).await?
                .next().await?.context("message count")?.get(0)?;
            assert_eq!(messages, 1, "{label}");
        }
        println!("DET6_CASES ingestion=19 replay_each=2");
        Ok(())
    }
