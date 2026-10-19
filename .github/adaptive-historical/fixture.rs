
#[cfg(all(test, feature = "server"))]
mod hosted_historical_shadow {
    use super::*;
    use anyhow::Context as _;
    use sashiko::settings::DatabaseSettings;

    #[tokio::test]
    #[ignore = "hosted public archive replay into an isolated shadow database"]
    async fn test_historical_archive_shadow_replay() -> anyhow::Result<()> {
        let path = std::env::var("HISTORICAL_SHADOW_DB")?;
        let db = Arc::new(Database::new(&DatabaseSettings {
            url: path,
            token: String::new(),
        }).await?);
        db.migrate().await?;
        if std::env::var("HISTORICAL_SHADOW_PHASE")? == "prepare" {
            db.create_thread("protected-control@example.test", "protected source control", 1).await?;
            return Ok(());
        }
        let raw = std::fs::read(std::env::var("HISTORICAL_RAW_EMAIL")?)?;
        let policy = sashiko::email_policy::EmailPolicyConfig::load(
            std::env::var("HISTORICAL_SHADOW_POLICY")?,
        )?;
        let (metadata, patch) = sashiko::patch::parse_email(&raw)?;
        anyhow::ensure!(metadata.total == 1 && metadata.index == 1, "archive sample is not a singleton patch");
        anyhow::ensure!(patch.is_some(), "archive sample contains no parsed patch");
        assert_eq!(metadata.message_id, std::env::var("HISTORICAL_MESSAGE_ID")?);
        let article_id = metadata.message_id.clone();
        assert!(matches!(
            process_parsed_article(
                &db,
                ParsedArticle {
                    group: "org.kernel.vger.git".into(),
                    article_id,
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
                },
                None,
                &policy,
                &[],
            ).await,
            ProcessStatus::Ingested
        ));
        let mut rows = db.conn.query(
            "SELECT (SELECT COUNT(*) FROM review_cooldown_events), (SELECT COUNT(*) FROM review_cooldown_intents), (SELECT COUNT(*) FROM patches), (SELECT COUNT(*) FROM email_outbox)",
            (),
        ).await?;
        let row = rows.next().await?.context("missing historical replay counts")?;
        assert_eq!(row.get::<i64>(0)?, 1);
        assert_eq!(row.get::<i64>(1)?, 1);
        assert_eq!(row.get::<i64>(2)?, 1);
        assert_eq!(row.get::<i64>(3)?, 0);
        Ok(())
    }
}
