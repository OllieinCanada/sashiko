
#[cfg(all(test, feature = "server"))]
mod hosted_old_version {
    use super::*;
    #[tokio::test]
    async fn test_old_version_downgrade_access() -> Result<()> {
        let db = Database::new(&DatabaseSettings {
            url: std::env::var("COOLDOWN_DOWNGRADE_DB")?, token: String::new(),
        }).await?;
        db.migrate().await?;
        let version: i64 = db.conn.query("PRAGMA user_version", ()).await?.next().await?
            .ok_or_else(|| anyhow::anyhow!("missing schema version"))?.get(0)?;
        assert_eq!(version, 16, "old access rewrote schema version");
        if std::env::var("COOLDOWN_DOWNGRADE_PHASE")? == "unsafe-copy" {
            assert!(db.lock_pending_email().await?.is_some(), "negative control did not demonstrate old claim behavior");
            assert!(db.lock_pending_patchwork().await?.is_some());
        } else {
            assert!(db.get_pending_patchsets(10).await?.is_empty());
            assert!(db.get_releasable_embargoed_patchsets(chrono::Utc::now().timestamp(), 10).await?.is_empty());
            assert!(db.lock_pending_email().await?.is_none());
            assert!(db.lock_pending_patchwork().await?.is_none());
        }
        Ok(())
    }
}
