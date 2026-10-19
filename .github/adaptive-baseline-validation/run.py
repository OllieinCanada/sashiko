#!/usr/bin/env python3
"""Native matched upstream/candidate workload, with explicit baseline adapters."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tarfile
import tempfile
import time

ROOT = Path.cwd()
OUT = ROOT / "adaptive-baseline-results"
OUT.mkdir(exist_ok=True)
BASE = "f5b01837023512fb6b43a76f88a0aaf77c5ca43d"
FIXTURE = (ROOT / ".github/adaptive-validation/native_fixture.rs").read_text()
SOURCE = ROOT / "src/db/cooldown.rs"
ORIGINAL = SOURCE.read_text()
ENV = os.environ.copy()
ENV["CARGO_TARGET_DIR"] = str(ROOT / "target")
REPORT = {
    "status": "RUNNING", "baseline_commit": BASE,
    "candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "budgets": {"disabled_over_baseline": 1.20, "enabled_over_disabled": 1.50,
                "case_timeout_seconds": 180, "repetitions": 3},
    "limitations": [
        "Serial file-backed debug workload; no production latency claim.",
        "Retained state is 10000 synthetic archived owners, not a replay.",
        "Baseline has the same archived patchsets and no adaptive tables.",
        "No writer hold/wait or SQL API counter instrumentation.",
        "Legacy equality covers this trace with no fixed deadline configured.",
        "Does not replace the original full acceptance matrix.",
    ],
    "samples": [], "binaries": {},
}


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


def run(args, label, cwd=ROOT, env=ENV, timeout=180):
    print("START " + label, flush=True)
    started = time.monotonic()
    with (OUT / (label + ".log")).open("w") as stream:
        process = subprocess.run(args, cwd=cwd, env=env, stdout=stream,
                                 stderr=subprocess.STDOUT, timeout=timeout)
    if process.returncode:
        print((OUT / (label + ".log")).read_text()[-16000:], flush=True)
        raise RuntimeError(f"{label}: exit {process.returncode}")
    print("PASS " + label, flush=True)
    return (OUT / (label + ".log")).read_text(), time.monotonic() - started


OBSERVATIONS = r'''
            let mut rows = db.conn.query(
                "SELECT json_group_array(json_array(cover_letter_message_id,subject,author,date,status,total_parts,received_parts,subject_index,parser_version,to_recipients,cc_recipients,embargo_until,embargo_release_started_at)) FROM (SELECT * FROM patchsets WHERE id>0 ORDER BY id)",
                (),
            ).await?;
            let patchsets: String = rows.next().await?.context("missing legacy observation")?.get(0)?;
            let mut rows = db.conn.query(
                "SELECT json_group_array(json_array(message_id,part_index,hex(diff),status,git_patch_id)) FROM (SELECT * FROM patches ORDER BY id)",
                (),
            ).await?;
            let patches_state: String = rows.next().await?.context("missing patch observation")?.get(0)?;
            use sha2::Digest as _;
            let legacy_patchsets_sha256 = sha2::Sha256::digest(patchsets.as_bytes()).iter().map(|byte| format!("{byte:02x}")).collect::<String>();
            let legacy_patches_sha256 = sha2::Sha256::digest(patches_state.as_bytes()).iter().map(|byte| format!("{byte:02x}")).collect::<String>();
'''


def fixture_with_observations():
    source = FIXTURE
    anchor = '            println!("COOLDOWN_PROBE {}", serde_json::json!({'
    if source.count(anchor) != 1:
        raise RuntimeError("unexpected fixture print anchor")
    source = source.replace(anchor, OBSERVATIONS + "\n" + anchor)
    anchor = '"storage": "file-backed", "profile": "instrumentation-free-debug"'
    source = source.replace(anchor, anchor + ',\n'
                            '                "legacy_patchsets_sha256": legacy_patchsets_sha256,\n'
                            '                "legacy_patches_sha256": legacy_patches_sha256')
    return source


def baseline_fixture(source):
    file_db = source[source.index("        async fn file_database"):
                     source.index("        async fn retained_owners")]
    ingest = source[source.index("        async fn ingest"):
                    source.index("        #[tokio::test]")]
    first = source.index("        #[tokio::test]")
    end = source.index("        #[tokio::test]", first + 1)
    performance = source[first:end]
    old = "let handle = db.with_cooldown_context(enabled.then(|| context(list, &author)));"
    if performance.count(old) != 1:
        raise RuntimeError("unexpected context adapter anchor")
    performance = performance.replace(old, 'let handle = db.with_bug_actor("system", "hosted-baseline", None);')
    performance = performance.replace(
        'assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_events").await?, admitted);',
        'assert_eq!(admitted, 0);')
    performance = performance.replace(
        'assert_eq!(scalar(&db, "SELECT COUNT(*) FROM review_cooldown_intents WHERE state=\'blocked\'").await?, 0);',
        '')
    helpers = r'''
        async fn fixture_source_handle(db: &Database, _message: &str) -> Result<Database> {
            Ok(db.with_bug_actor("system", "hosted-baseline", None))
        }
        async fn scalar(db: &Database, sql: &str) -> Result<i64> {
            Ok(db.conn.query(sql, ()).await?.next().await?.context("missing scalar")?.get(0)?)
        }
        async fn retained_owners(db: &Database, count: i64) -> Result<()> {
            if count > 0 {
                db.conn.execute(
                    "WITH RECURSIVE n(v) AS (VALUES(1) UNION ALL SELECT v+1 FROM n WHERE v < ?) INSERT INTO patchsets(id,status,total_parts,received_parts) SELECT -v,'Reviewed',1,1 FROM n",
                    libsql::params![count],
                ).await?;
            }
            Ok(())
        }
'''
    return '\n#[cfg(all(test, feature = "server"))]\nmod hosted_baseline {\nuse super::*;\n' + file_db + helpers + ingest + performance + '\n}\n'


def build(cwd, label):
    run(["cargo", "fmt", "--all"], "format-" + label, cwd=cwd, timeout=60)
    text, _ = run(["cargo", "test", "--locked", "--all-features", "--lib",
                   "--no-run", "--message-format=json"],
                  "build-" + label, cwd=cwd, timeout=600)
    binaries = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact"
                and item.get("target", {}).get("kind") == ["lib"]
                and item.get("profile", {}).get("test")
                and item.get("executable")):
            binaries.append(item["executable"])
    if len(set(binaries)) != 1:
        raise RuntimeError("ambiguous library test artifact")
    path = OUT / (label + "-tests")
    shutil.copy2(binaries[0], path)
    REPORT["binaries"][label] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
    }
    save()
    return path


def main():
    run(["git", "fetch", "--no-tags", "origin", BASE], "fetch-baseline", timeout=60)
    archive = subprocess.check_output(["git", "archive", BASE], cwd=ROOT)
    REPORT["baseline_archive_sha256"] = hashlib.sha256(archive).hexdigest()
    native = fixture_with_observations()
    REPORT["adapted_fixture_sha256"] = hashlib.sha256(native.encode()).hexdigest()
    save()
    closing = ORIGINAL.rfind("}")
    SOURCE.write_text(ORIGINAL[:closing] + native + "\n" + ORIGINAL[closing:])
    candidate = build(ROOT, "candidate")
    with tempfile.TemporaryDirectory(prefix="adaptive-upstream-") as directory:
        baseline_root = Path(directory)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(baseline_root, filter="data")
        db_source = baseline_root / "src/db.rs"
        db_source.write_text(db_source.read_text() + baseline_fixture(native))
        REPORT["baseline_fixture_sha256"] = hashlib.sha256(db_source.read_bytes()).hexdigest()
        baseline = build(baseline_root, "baseline")
    cases = [("baseline", "disabled", baseline),
             ("candidate", "disabled", candidate),
             ("candidate", "enabled", candidate)]
    for repetition in range(3):
        ordered = cases if repetition % 2 == 0 else list(reversed(cases))
        for retained in [0, 10000]:
            for variant, mode, binary in ordered:
                if shutil.disk_usage(ROOT).free < 3 * 1024 ** 3:
                    raise RuntimeError("free disk below 3 GiB floor")
                env = ENV.copy()
                env["COOLDOWN_PROBE_MODE"] = mode
                env["COOLDOWN_PROBE_RETAINED"] = str(retained)
                label = f"sample-{repetition}-{retained}-{variant}-{mode}"
                text, elapsed = run(
                    [str(binary), "test_cooldown_hosted_performance",
                     "--ignored", "--nocapture", "--test-threads=1"],
                    label, env=env)
                marker = "COOLDOWN_PROBE "
                matches = [line.split(marker, 1)[1] for line in text.splitlines() if marker in line]
                if len(matches) != 1 or "1 passed; 0 failed" not in text:
                    raise RuntimeError(label + ": missing test or measurement")
                row = json.loads(matches[0])
                row.update(variant=variant, repetition=repetition, process_seconds=elapsed)
                REPORT["samples"].append(row)
                save()
    comparisons = []
    for retained in [0, 10000]:
        selected = [x for x in REPORT["samples"] if x["retained"] == retained]
        medians = {}
        for variant, mode, _ in cases:
            values = [x["seconds"] for x in selected
                      if x["variant"] == variant and x["mode"] == mode]
            medians[variant + "_" + mode] = statistics.median(values)
        disabled = [x for x in selected if x["mode"] == "disabled"]
        legacy_equal = all(len({x[key] for x in disabled}) == 1 for key in
                           ["legacy_patchsets_sha256", "legacy_patches_sha256"])
        disabled_ratio = medians["candidate_disabled"] / medians["baseline_disabled"]
        enabled_ratio = medians["candidate_enabled"] / medians["candidate_disabled"]
        comparisons.append({
            "retained": retained, "median_seconds": medians,
            "disabled_over_baseline": disabled_ratio,
            "enabled_over_disabled": enabled_ratio, "legacy_state_equal": legacy_equal,
            "budget_pass": legacy_equal and disabled_ratio <= 1.20 and enabled_ratio <= 1.50,
        })
    REPORT["comparisons"] = comparisons
    REPORT["status"] = "PASS" if all(x["budget_pass"] for x in comparisons) else "FAIL_BUDGET"
    save()
    print(json.dumps({key: REPORT[key] for key in ["status", "comparisons"]}, indent=2), flush=True)
    if REPORT["status"] != "PASS":
        raise SystemExit(2)


try:
    main()
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
    raise
finally:
    SOURCE.write_text(ORIGINAL)
