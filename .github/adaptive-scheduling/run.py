#!/usr/bin/env python3
"""Exercise natural expiry across reopened workers and a gated recording MTA."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
ROOT = Path.cwd()
OUT = ROOT / "adaptive-scheduling-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "src/main.rs"
ORIGINAL = SOURCE.read_text()
REPORT = {"status": "RUNNING", "source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "checks": [], "replays_after_delivery": 3, "limitations": [
              "File-backed local fixture, natural 30-second deadline, no manual release.",
              "Completed review is a fixture; no model call or real outbound delivery.",
              "Workers and DB handles reopen in one test process; separate process admission recovery is covered by the existing restart job.",
              "Gated local recording sendmail represents a slow external transport; no SMTP acceptance/acknowledgement crash is simulated."]}
spec = importlib.util.spec_from_file_location("injector", ROOT / ".github/adaptive-observability/instrument.py")
injector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(injector)
once = injector.once

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def run(args, label, timeout):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        result = subprocess.run(args, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=timeout)
    text = (OUT / (label + ".log")).read_text()
    if result.returncode:
        print(text[-18000:], flush=True)
        raise RuntimeError(label + ": exit " + str(result.returncode))
    print("PASS " + label, flush=True)
    return text

try:
    save()
    start = ORIGINAL.index("    #[tokio::test]\n    async fn test_cooldown_config_to_real_release_and_sendmail")
    code = injector.mask(ORIGINAL)
    opening = code.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        if code[end] == "{": depth += 1
        elif code[end] == "}": depth -= 1
        end += 1
    test = ORIGINAL[start:end]
    test = once(test, "test_cooldown_config_to_real_release_and_sendmail",
                "test_cooldown_natural_expiry_restart_and_slow_transport")
    test = once(test, "step_seconds = 3600\nmax_extra_seconds = 3600",
                "step_seconds = 30\nmax_extra_seconds = 30")
    test = once(test, "        assert!(db.release_patchset_embargo(target, now).await?);", '''
        let deadline: i64 = db.conn.query("SELECT embargo_until FROM patchsets WHERE id=?", libsql::params![target]).await?
            .next().await?.context("missing held deadline")?.get(0)?;
        assert!(deadline > chrono::Utc::now().timestamp());
''')
    test = once(test, '        let quoted = capture.to_string_lossy().replace(\'\\\'\', "\'\\\\\'\'");\n', '')
    test = once(test, '''        std::fs::write(&source_script, format!("#!/bin/sh\\ncat >> '{quoted}'\\n"))?;''', r'''
        let gate = directory.path().join("transport-gate");
        let entered = directory.path().join("transport-entered");
        let attempts = directory.path().join("transport-attempts");
        std::fs::write(&source_script, format!(
            "#!/usr/bin/env python3\nimport pathlib,sys,time\nwith open({attempts:?}, 'a') as attempts: attempts.write('1\\n')\npathlib.Path({entered:?}).write_text('entered')\nwhile not pathlib.Path({gate:?}).exists(): time.sleep(0.02)\nwith open({capture:?}, 'a') as capture: capture.write(sys.stdin.read())\n"
        ))?;
''')
    test = once(test, '''        let reviewer = sashiko::reviewer::Reviewer::new(db.clone(), settings).await;''', '''
        let premature = sashiko::reviewer::Reviewer::new(db.clone(), settings.clone()).await;
        let premature = tokio::spawn(async move { premature.start().await });
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        premature.abort();
        let _ = premature.await;
        let early: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox", ()).await?
            .next().await?.context("missing early queue count")?.get(0)?;
        assert_eq!(early, 0, "worker published before the natural deadline");
        assert!(chrono::Utc::now().timestamp() < deadline);
        drop(db);
        let db = Arc::new(Database::new(&settings.database).await?);
        tokio::time::timeout(std::time::Duration::from_secs(45), async {
            while chrono::Utc::now().timestamp() < deadline {
                tokio::time::sleep(std::time::Duration::from_millis(50)).await;
            }
        }).await?;
        let reviewer = sashiko::reviewer::Reviewer::new(db.clone(), settings.clone()).await;''')
    test = once(test, '''        assert!(!capture.exists());
        let worker = sashiko::worker::email::EmailWorker::new(db.clone(), smtp, false);''', '''
        assert!(!capture.exists());
        let again = sashiko::reviewer::Reviewer::new(db.clone(), settings.clone()).await;
        let again = tokio::spawn(async move { again.start().await });
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        again.abort();
        let _ = again.await;
        let queued: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox", ()).await?
            .next().await?.context("missing dedup queue count")?.get(0)?;
        assert_eq!(queued, 1, "restart duplicated the notification");
        let worker = sashiko::worker::email::EmailWorker::new(db.clone(), smtp.clone(), false);''')
    test = once(test, '''        let delivery = tokio::spawn(async move { worker.run().await });
        let wait_sent =''', '''
        let delivery = tokio::spawn(async move { worker.run().await });
        let entered_result = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            while !entered.exists() {
                tokio::time::sleep(std::time::Duration::from_millis(20)).await;
            }
        }).await;
        let independent = tokio::time::timeout(std::time::Duration::from_secs(5),
            db.create_thread("while-sendmail@example.test", "unrelated write", 1)).await;
        // Release the child before propagating errors so cleanup cannot strand it.
        std::fs::write(&gate, "continue")?;
        let wait_sent =''')
    test = once(test, '''        wait_sent??;
        let accepted =''', '''
        entered_result?;
        independent??;
        wait_sent??;
        let worker = sashiko::worker::email::EmailWorker::new(db.clone(), smtp, false);
        let again = tokio::spawn(async move { worker.run().await });
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        again.abort();
        let _ = again.await;
        assert_eq!(std::fs::read_to_string(&attempts)?.lines().count(), 1);
        let accepted =''')
    test = once(test, "        let mut target = 0;", "        let mut held_raw = String::new();\n        let mut target = 0;")
    test = once(test, "            let (metadata, patch) = sashiko::patch::parse_email(raw.as_bytes())?;",
                '            if token == "held" { held_raw = raw.clone(); }\n            let (metadata, patch) = sashiko::patch::parse_email(raw.as_bytes())?;')
    test = once(test, """        wait_sent??;
        let worker =""", '''
        wait_sent??;
        let frozen_sql = "SELECT json_array(c.admitted_at,c.prior_count,c.extra_seconds,c.decided_deadline,c.released_at,p.embargo_until) FROM review_cooldown_intents c JOIN patchsets p ON p.id=c.patchset_id WHERE p.id=?";
        let before: String = db.conn.query(frozen_sql, libsql::params![target]).await?
            .next().await?.context("missing pre-replay snapshot")?.get(0)?;
        for attempt in 0..3 {
            let (metadata, patch) = sashiko::patch::parse_email(held_raw.as_bytes())?;
            let article = ParsedArticle {
                group: "test.list".into(), article_id: format!("replay-{attempt}"),
                source: MessageSource::Nntp, metadata: Some(metadata), patch,
                baseline: None, failed_error: None, skip_filters: None,
                only_filters: None, mr_url: None, mr_title: None, mr_number: None, receipt: None,
            };
            assert!(matches!(process_parsed_article(&db, article, None, &policy, &[]).await, ProcessStatus::Ingested));
        }
        let after: String = db.conn.query(frozen_sql, libsql::params![target]).await?
            .next().await?.context("missing post-replay snapshot")?.get(0)?;
        assert_eq!(before, after, "replay changed a frozen decision or live release");
        let reviewer = sashiko::reviewer::Reviewer::new(db.clone(), settings.clone()).await;
        let reviewer = tokio::spawn(async move { reviewer.start().await });
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        reviewer.abort();
        let _ = reviewer.await;
        let total: i64 = db.conn.query("SELECT COUNT(*) FROM email_outbox", ()).await?
            .next().await?.context("missing replay queue count")?.get(0)?;
        assert_eq!(total, 1);
        println!("SCHEDULING_CHECK natural-expiry/reopen/release-restart/slow-transport/replay");
        let worker =''')

    SOURCE.write_text(ORIGINAL[:end] + "\n\n" + test + ORIGINAL[end:])
    REPORT["fixture_sha256"] = hashlib.sha256(test.encode()).hexdigest()
    save()
    run(["cargo", "fmt", "--all"], "format-scheduling-fixture", 60)
    text = run(["cargo", "test", "--locked", "--all-features", "--bin", "sashiko",
                "test_cooldown_natural_expiry_restart_and_slow_transport",
                "--", "--nocapture", "--test-threads=1"], "natural-expiry-restart-slow-transport", 600)
    # Unit tests carry the tests:: prefix; insist that a real test executed.
    if "1 passed; 0 failed" not in text:
        raise RuntimeError("expected one passing end-to-end test")
    REPORT["checks"].append({"name": "natural-expiry-restart-slow-transport", "status": "PASS"})
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
finally:
    SOURCE.write_text(ORIGINAL)
