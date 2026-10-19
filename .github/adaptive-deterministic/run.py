#!/usr/bin/env python3
"""Run isolated deterministic additions on unchanged production source."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path.cwd()
FIXTURES = ROOT / ".github/adaptive-deterministic"
OUT = ROOT / "adaptive-deterministic-results"
OUT.mkdir(exist_ok=True)
SOURCE_BASE = "bd59059f1864aea81b11b5de0eb97e5d2ec53667"
PATHS = {
    "src/main.rs": ["main_fixture.rs", "cancel_fixture.rs"],
    "src/reviewer.rs": ["reviewer_fixture.rs"],
    "src/db/cooldown.rs": ["db_fixture.rs"],
    "src/cooldown.rs": ["pure_fixture.rs"],
    "src/server.rs": ["server_fixture.rs"],
}
ORIGINAL = {p: (ROOT / p).read_text() for p in PATHS}
ENV = os.environ.copy()
ENV.update({"HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "localhost,127.0.0.1", "RUST_BACKTRACE": "0"})
REPORT = {
    "status": "RUNNING",
    "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "production_base": SOURCE_BASE,
    "source_sha256": {p: hashlib.sha256(s.encode()).hexdigest() for p, s in ORIGINAL.items()},
    "fixture_sha256": {},
    "checks": [],
    "mutants": [],
    "limitations": [
        "Temporary databases, fixed fixture review outputs, local recording sendmail; no model calls or external delivery.",
        "Clock tests drive explicit scheduling/admission time parameters, not the host wall clock.",
        "Resource tests cover bounded corpus and configured ceilings, not a universal allocation bound.",
        "Privacy test covers public review/details/summary routes and captured handler tracing; actual model-provider logs are not exercised.",
        "Cancellation covers uncommitted admission and pre-acceptance sendmail, not every detached review-task or SMTP acknowledgement window.",
        "Policy agreement, permanent storage and indivisible ownership-group limitations remain open.",
    ],
}
TESTS = [
    ("ingestion-crosspost-ignore", "bin", "tests::test_det6_ingestion_crosspost_and_ignore_matrix", 90),
    ("enabled-routing", "lib", "reviewer::tests::test_det6_enabled_routing_and_integration_matrix", 120),
    ("clock-jumps", "lib", "db::cooldown::tests::test_det6_forward_clock_release_is_irreversible", 60),
    ("cancel-admission", "lib", "db::cooldown::tests::test_det6_cancel_uncommitted_admission_releases_writer", 60),
    ("bound-sql", "lib", "db::cooldown::tests::test_det6_bound_sql_payloads_preserve_schema_and_dedup", 90),
    ("malformed-canaries", "lib", "cooldown::tests::test_det6_malformed_identity_and_id_errors_do_not_echo_inputs", 30),
    ("private-routes-traces", "lib", "server::tests::test_det6_held_and_quarantined_canaries_stay_private", 60),
    ("abort-transport-recover", "bin", "tests::test_det6_abort_adaptive_transport_then_recover", 90),
]

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def command(args, label, timeout, expected=0):
    print("START " + label, flush=True)
    started = time.monotonic()
    with (OUT / (label + ".log")).open("w") as stream:
        process = subprocess.Popen(args, cwd=ROOT, env=ENV, stdout=stream,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        finally:
            # This runner owns the session, including any interrupted recording MTA.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    text = (OUT / (label + ".log")).read_text()
    if code != expected:
        print(text[-14000:], flush=True)
        raise RuntimeError(label + ": unexpected process exit " + str(code))
    print("PASS " + label, flush=True)
    return text, time.monotonic() - started

def build(label):
    text, _ = command(
        ["cargo", "test", "--locked", "--all-features", "--lib", "--bin", "sashiko",
         "--no-run", "--message-format=json"], label, 900)
    binaries = {}
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") != "compiler-artifact"
                or not item.get("executable") or not item.get("profile", {}).get("test")):
            continue
        kind = item.get("target", {}).get("kind")
        if kind == ["lib"]:
            binaries["lib"] = item["executable"]
        elif kind == ["bin"] and item["target"].get("name") == "sashiko":
            binaries["bin"] = item["executable"]
    if set(binaries) != {"lib", "bin"}:
        raise RuntimeError("missing or ambiguous test binary")
    return binaries

def test(binary, name, label, timeout, negative=False):
    text, seconds = command(
        [binary, name, "--exact", "--nocapture", "--test-threads=1"], label, timeout,
        expected=101 if negative else 0)
    summary = "0 passed; 1 failed" if negative else "1 passed; 0 failed"
    if "running 1 test" not in text or summary not in text:
        raise RuntimeError(label + ": missing exact-one-test control")
    if negative and not ("panicked at" in text or "Error:" in text):
        raise RuntimeError(label + ": missing semantic failure")
    row = {"name": label, "test": name, "seconds": seconds,
           "status": "KILLED" if negative else "PASS"}
    REPORT["checks"].append(row)
    save()
    markers = [line.split("DET6_CASES", 1)[1].strip()
               for line in text.splitlines() if "DET6_CASES" in line]
    required_marker = {
        "ingestion-crosspost-ignore": "ingestion=19",
        "enabled-routing": "notification_policy=16",
        "clock-jumps": "selector_clock_instants=7",
        "abort-transport-recover": "transport_abort=1",
    }.get(label)
    if required_marker and (len(markers) != 1 or required_marker not in markers[0]):
        raise RuntimeError(label + ": missing complete-case fixture marker")
    row["case_markers"] = markers
    save()
    for marker in markers:
        print("DET6_CASES " + marker, flush=True)

def restore():
    for path, text in ORIGINAL.items():
        (ROOT / path).write_text(text)

try:
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", SOURCE_BASE, "HEAD", "--",
         "src", "docs", "designs", "MAINTAINERS_GUIDE.md", "Cargo.toml", "Cargo.lock"],
        text=True)
    if diff.strip():
        raise RuntimeError("production source differs from frozen checked base")
    for path, fixtures in PATHS.items():
        source = ORIGINAL[path]
        closing = source.rfind("}")
        if closing < 0:
            raise RuntimeError("missing test-module closing brace")
        addition = ""
        for fixture in fixtures:
            raw = (FIXTURES / fixture).read_bytes()
            REPORT["fixture_sha256"][fixture] = hashlib.sha256(raw).hexdigest()
            addition += "\n" + raw.decode()
        (ROOT / path).write_text(source[:closing] + addition + "\n" + source[closing:])
    save()
    command(["cargo", "fmt", "--all"], "format-fixtures", 60)
    baseline = {p: (ROOT / p).read_text() for p in PATHS}
    patch = subprocess.check_output(["git", "diff", "--", *PATHS], text=True)
    (OUT / "deterministic-test-additions.patch").write_text(patch)
    binaries = build("build-fixtures")
    for label, kind, target, seconds in TESTS:
        test(binaries[kind], target, label, seconds)
    command(["cargo", "clippy", "--locked", "--all-targets", "--all-features",
             "--", "-D", "warnings"], "clippy-fixtures", 600)
    # Verify that the two new matrices detect removal of their intended guard.
    mutants = [
        ("ignore-ingestion", "src/main.rs",
         "if sashiko::email_router::EmailRouter::is_ignored_author(policy, &author_email) {",
         "if false && sashiko::email_router::EmailRouter::is_ignored_author(policy, &author_email) {",
         "bin", TESTS[0][2]),
        ("review-privacy", "src/server.rs",
         "async fn enforce_review_embargo(\n", None, "lib", TESTS[6][2]),
    ]
    for label, path, anchor, replacement, kind, target in mutants:
        for p, text in baseline.items():
            (ROOT / p).write_text(text)
        text = baseline[path]
        if text.count(anchor) != 1:
            raise RuntimeError(label + ": non-unique mutation anchor")
        if replacement is not None:
            text = text.replace(anchor, replacement)
        else:
            opening = text.index("{", text.index(anchor))
            text = text[:opening + 1] + "\n    if true { return Ok(()); }\n" + text[opening + 1:]
        (ROOT / path).write_text(text)
        binaries = build("build-mutant-" + label)
        test(binaries[kind], target, "negative-" + label, 120, negative=True)
        test(binaries["lib"], TESTS[5][2], "unrelated-under-" + label, 30)
        REPORT["mutants"].append({"name": label, "status": "KILLED", "target": target})
        save()
    for path, text in baseline.items():
        (ROOT / path).write_text(text)
    binaries = build("build-restored-fixtures")
    test(binaries["lib"], TESTS[6][2], "restored-privacy", 60)
    restore()
    if any((ROOT / p).read_text() != s for p, s in ORIGINAL.items()):
        raise RuntimeError("source restore mismatch")
    REPORT["source_restored"] = True
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
finally:
    restore()
