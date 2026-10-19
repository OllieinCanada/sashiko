    async fn det6_privacy_paths(quarantined: bool) -> anyhow::Result<()> {
        use crate::cooldown::{CooldownContext, CooldownPolicy};
        let mut settings = crate::settings::Settings::new()?;
        settings.database.url = ":memory:".into();
        settings.server.testing_mode = false;
        let db = Arc::new(Database::new(&settings.database).await?);
        db.migrate().await?;
        let active = db.with_cooldown_context(Some(CooldownContext {
            list: "list@example.test".into(),
            author: "dev@example.test".into(),
            policy: CooldownPolicy {
                window_seconds: 100,
                burst: 2,
                step_seconds: 10,
                max_extra_seconds: 30,
            },
            legacy_deadline: Some(chrono::Utc::now().timestamp() + 3600),
            source_snapshot: None,
        }));
        let msg = "direct-review@example.test";
        let thread = active.create_thread(msg, "[PATCH] direct", 1).await?;
        active
            .create_message(
                msg,
                thread,
                None,
                "dev@example.test",
                "[PATCH] direct",
                1,
                "diff",
                "list@example.test",
                "",
                None,
                None,
            )
            .await?;
        let mut context = crate::cooldown::CooldownContext {
            list: "list@example.test".into(),
            author: "dev@example.test".into(),
            policy: CooldownPolicy {
                window_seconds: 100,
                burst: 2,
                step_seconds: 10,
                max_extra_seconds: 30,
            },
            legacy_deadline: Some(chrono::Utc::now().timestamp() + 3600),
            source_snapshot: None,
        };
        let fingerprint: String = db
            .conn
            .query(
                "SELECT cooldown_source_hash FROM messages WHERE message_id = ?",
                libsql::params![msg],
            )
            .await?
            .next()
            .await?
            .unwrap()
            .get(0)?;
        context.source_snapshot = Some(crate::cooldown::SourceSnapshot {
            message_id: msg.into(),
            fingerprint,
        });
        let active = db.with_cooldown_context(Some(context));
        let id = active
            .create_patchset(
                thread,
                Some(msg),
                msg,
                "[PATCH] direct",
                "dev@example.test",
                1,
                1,
                3,
                "list@example.test",
                "",
                None,
                1,
                None,
                true,
                None,
                None,
            )
            .await?
            .unwrap();
        let patch = active.create_patch(id, msg, 1, "diff").await?;
        let review = db
            .create_review(id, Some(patch), "fixture", "no-model", None, None)
            .await?;
        db.complete_review(
            review,
            "Reviewed",
            "DET6_HELD_CONTENT_CANARY",
            Some("result"),
            None,
            Some("inline"),
            Some("DET6_PRIVATE_LOG_CANARY DET6_FAKE_CREDENTIAL_CANARY"),
        )
        .await?;
        db.update_patch_status(patch, "Reviewed").await?;
        db.update_patchset_status(id, "Reviewed").await?;
        if quarantined {
        assert!(
            db.create_message(
                msg,
                thread,
                None,
                "changed@example.test",
                "[PATCH] changed",
                1,
                "changed",
                "list@example.test",
                "",
                None,
                None
            )
            .await
            .is_err()
        );
        }
        settings.server.acl.admins = vec!["operator@example.test".into()];
        let settings = Arc::new(settings);
        let (event_tx, _event_rx) = mpsc::channel(1);
        let (fetch_tx, _fetch_rx) = mpsc::channel(1);
        let state = Arc::new(AppState {
            db: db.clone(),
            sender: event_tx,
            fetch_sender: fetch_tx,
            settings: settings.clone(),
            read_only: false,
            allow_all_submit: false,
            smtp_enabled: false,
            dry_run: true,
            local_token: None,
            email_worker_heartbeat: None,
            forge_registry: Arc::new(crate::forge::ForgeRegistry::new()),
            patchsets_homepage_cache: AsyncCache::new(Duration::from_secs(2)),
            messages_homepage_cache: AsyncCache::new(Duration::from_secs(2)),
            patchsets_count_cache: AsyncCache::new(Duration::from_secs(10)),
            messages_count_cache: AsyncCache::new(Duration::from_secs(10)),
            stats_timeline_cache: AsyncMapCache::new(Duration::from_secs(60)),
            stats_reviews_cache: AsyncCache::new(Duration::from_secs(60)),
            stats_tools_cache: AsyncCache::new(Duration::from_secs(60)),
            bug_subsystems_cache: AsyncMapCache::new(Duration::from_secs(60)),
            sign_in_link_rate_limiter: SignInLinkRateLimiter::new(),
        });
        let headers = axum::http::HeaderMap::new();
        for query in [
            ReviewQuery {
                id: Some(review),
                patchset_id: None,
            },
            ReviewQuery {
                id: None,
                patchset_id: Some(id),
            },
        ] {
            let result = get_review(
                crate::auth::OptionalAuthUser(None),
                OptionalPrincipal(Principal::anonymous()),
                headers.clone(),
                State(state.clone()),
                Query(ReviewQuery {
                    id: query.id,
                    patchset_id: query.patchset_id,
                }),
            )
            .await;
            assert_eq!(result.unwrap_err(), StatusCode::NOT_FOUND);
            let result = get_review_log(
                crate::auth::OptionalAuthUser(None),
                OptionalPrincipal(Principal::anonymous()),
                headers.clone(),
                State(state.clone()),
                Query(query),
            )
            .await;
            assert_eq!(result.unwrap_err(), StatusCode::NOT_FOUND);
        }
        let query = || PatchQuery {
            id: id.to_string(),
            page: None,
            per_page: None,
        };
        let Json(public) = get_patchset(
            crate::auth::OptionalAuthUser(None),
            OptionalPrincipal(Principal::anonymous()),
            headers.clone(),
            State(state.clone()),
            Query(query()),
        )
        .await
        .unwrap();
        assert!(public["reviews"].as_array().unwrap().is_empty());
        assert_eq!(public["can_view_embargoed"], false);
        let serialized = serde_json::to_string(&public)?;
        for marker in ["DET6_HELD_CONTENT_CANARY","DET6_PRIVATE_LOG_CANARY","DET6_FAKE_CREDENTIAL_CANARY"] {
            assert!(!serialized.contains(marker));
        }
        let Json(summary) = get_patchset_summary(
            crate::auth::OptionalAuthUser(None),
            OptionalPrincipal(Principal::anonymous()), headers.clone(), State(state.clone()),
            Query(query())).await.unwrap();
        let serialized = serde_json::to_string(&summary)?;
        assert!(!serialized.contains("DET6_HELD_CONTENT_CANARY"));
        assert!(!serialized.contains("DET6_PRIVATE_LOG_CANARY"));
        assert!(!serialized.contains("DET6_FAKE_CREDENTIAL_CANARY"));
        let principal = Principal::resolve("operator@example.test", &settings.server.acl, None);
        let auth = crate::auth::OptionalAuthUser(Some(crate::auth::AuthUser {
            email: "operator@example.test".into(),
            typ: Some("session".into()),
            iat: Some(1),
            sid: None,
            max_bug_access: None,
        }));
        let Json(authorized) = get_patchset(
            auth,
            OptionalPrincipal(principal),
            headers.clone(),
            State(state.clone()),
            Query(query()),
        )
        .await
        .unwrap();
        assert_eq!(authorized["can_view_embargoed"], true);
        assert_eq!(authorized["can_release_embargo"], !quarantined);
        assert_eq!(authorized["reviews"].as_array().unwrap().len(), 1);
        let operator = || crate::auth::OptionalAuthUser(Some(crate::auth::AuthUser {
            email: "operator@example.test".into(), typ: Some("session".into()),
            iat: Some(1), sid: None, max_bug_access: None,
        }));
        for logs in [false, true] {
            let principal = Principal::resolve("operator@example.test", &settings.server.acl, None);
            let query = Query(ReviewQuery { id: Some(review), patchset_id: None });
            let Json(visible) = if logs {
                get_review_log(operator(), OptionalPrincipal(principal), headers.clone(), State(state.clone()), query).await.unwrap()
            } else {
                get_review(operator(), OptionalPrincipal(principal), headers.clone(), State(state.clone()), query).await.unwrap()
            };
            let serialized = serde_json::to_string(&visible)?;
            assert!(serialized.contains("DET6_HELD_CONTENT_CANARY"));
            assert!(serialized.contains("DET6_PRIVATE_LOG_CANARY"));
        }
        Ok(())
    }


    #[derive(Clone)]
    struct Det6Capture(Arc<std::sync::Mutex<Vec<u8>>>);
    impl std::io::Write for Det6Capture {
        fn write(&mut self, data: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(data);
            Ok(data.len())
        }
        fn flush(&mut self) -> std::io::Result<()> { Ok(()) }
    }
    impl<'a> tracing_subscriber::fmt::MakeWriter<'a> for Det6Capture {
        type Writer = Self;
        fn make_writer(&'a self) -> Self::Writer { self.clone() }
    }
    #[tokio::test]
    async fn test_det6_held_and_quarantined_canaries_stay_private() -> anyhow::Result<()> {
        use tracing::instrument::WithSubscriber;
        let captured = Det6Capture(Arc::new(std::sync::Mutex::new(Vec::new())));
        let subscriber = tracing_subscriber::fmt().without_time().with_ansi(false)
            .with_writer(captured.clone()).finish();
        let result = async {
            det6_privacy_paths(false).await?;
            det6_privacy_paths(true).await
        }.with_subscriber(subscriber).await;
        result?;
        let logs = String::from_utf8(captured.0.lock().unwrap().clone())?;
        assert!(logs.contains("Fetching"), "logging fixture captured no positive control");
        for marker in ["DET6_HELD_CONTENT_CANARY","DET6_PRIVATE_LOG_CANARY","DET6_FAKE_CREDENTIAL_CANARY"] {
            assert!(!logs.contains(marker), "private marker reached handler logs");
        }
        println!("DET6_CASES visibility_states=2 public_paths=6 authorized_paths=3 trace_canaries=3");
        Ok(())
    }
