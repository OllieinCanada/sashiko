#!/usr/bin/env python3
"""Validate real wall-clock jumps in one isolated test process per timezone."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path.cwd()
OUT = ROOT / "adaptive-clock-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "src/main.rs"
ORIGINAL = SOURCE.read_text()
REVIEWER = ROOT / "src/reviewer.rs"
REVIEWER_ORIGINAL = REVIEWER.read_text()
BASE = "bd59059f1864aea81b11b5de0eb97e5d2ec53667"
DIRECTORY = ROOT / ".github/adaptive-clock"
REPORT = {"status": "RUNNING", "production_base": BASE,
          "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
          "source_sha256": hashlib.sha256(ORIGINAL.encode()).hexdigest(),
          "checks": [], "limitations": [
              "LD_PRELOAD changes wall-clock APIs only in the owned test process and its recording MTA; no host-clock change.",
              "Monotonic time remains real; child process groups have bounded external timeouts.",
              "Review output is a fixture and delivery is local recording only.",
              "This does not establish arbitrary host/kernel clock behavior or remove fixed-deadline policy tradeoffs."]}

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def run(args, name, timeout=600, env=None):
    print("START " + name, flush=True)
    with (OUT / (name + ".log")).open("w") as output:
        process = subprocess.Popen(args, cwd=ROOT, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    text = (OUT / (name + ".log")).read_text()
    if code:
        print(text[-14000:], flush=True)
        raise RuntimeError(name + ": exit " + str(code))
    print("PASS " + name, flush=True)
    return text

try:
    REPORT["reviewer_source_sha256"] = hashlib.sha256(REVIEWER_ORIGINAL.encode()).hexdigest()
    save()
    diff = subprocess.check_output(
        ["git", "diff", "--name-only", BASE, "HEAD", "--", "src", "docs", "designs",
         "MAINTAINERS_GUIDE.md", "Cargo.toml", "Cargo.lock"], text=True)
    if diff.strip():
        raise RuntimeError("production base changed")
    fixture = (DIRECTORY / "fixture.rs").read_text()
    REPORT["fixture_sha256"] = hashlib.sha256(fixture.encode()).hexdigest()
    shim = DIRECTORY / "realtime.c"
    REPORT["shim_sha256"] = hashlib.sha256(shim.read_bytes()).hexdigest()
    shared = (OUT / "controlled-realtime.so").resolve()
    run(["cc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra", "-Werror",
         str(shim), "-o", str(shared)], "compile-clock-shim", 60)
    closing = ORIGINAL.rfind("}")
    SOURCE.write_text(ORIGINAL[:closing] + "\n" + fixture + "\n" + ORIGINAL[closing:])
    observer_anchor = "        let patchsets = self.db.get_releasable_embargoed_patchsets(now, 10).await?;"
    if REVIEWER_ORIGINAL.count(observer_anchor) != 1:
        raise RuntimeError("release observer anchor is not unique")
    observer = """
        if let Ok(path) = std::env::var("SASHIKO_TEST_RELEASE_PROBE") {
            std::fs::write(path, format!("{}:{}", now, patchsets.len()))?;
        }
"""
    REVIEWER.write_text(REVIEWER_ORIGINAL.replace(observer_anchor, observer_anchor + observer))
    REPORT["release_query_observer"] = "records actual now and selected count after production query"
    run(["cargo", "fmt", "--all"], "format-clock-fixture", 60)
    (OUT / "clock-test-addition.patch").write_text(
        subprocess.check_output(["git", "diff", "--", "src/main.rs", "src/reviewer.rs"], text=True))
    text = run(["cargo", "test", "--locked", "--all-features", "--bin", "sashiko",
                "--no-run", "--message-format=json"], "build-clock-fixture", 900)
    executables = []
    for line in text.splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (row.get("reason") == "compiler-artifact"
                and row.get("target", {}).get("name") == "sashiko"
                and row.get("target", {}).get("kind") == ["bin"]
                and row.get("profile", {}).get("test") and row.get("executable")):
            executables.append(row["executable"])
    if len(set(executables)) != 1:
        raise RuntimeError("missing exact clock test artifact")
    binary = executables[0]
    REPORT["binary_sha256"] = hashlib.sha256(Path(binary).read_bytes()).hexdigest()
    for label, timezone in [("utc", "UTC"), ("new-york", "America/New_York")]:
        control = (OUT / ("wall-clock-" + label)).resolve()
        control.write_text("2000000000")
        probe = str((OUT / ("release-probe-" + label)).resolve())
        env = os.environ.copy()
        if env.get("LD_PRELOAD"):
            raise RuntimeError("unexpected inherited preload")
        env.update({"LD_PRELOAD": str(shared), "SASHIKO_TEST_REALTIME_FILE": str(control),
                    "SASHIKO_TEST_RELEASE_PROBE": probe, "TZ": timezone, "HTTP_PROXY": "http://127.0.0.1:9",
                    "HTTPS_PROXY": "http://127.0.0.1:9", "NO_PROXY": "localhost,127.0.0.1"})
        calibration = run(["python3", "-c",
            "import time; assert int(time.time()) == 2000000000; start=time.monotonic(); time.sleep(.03); assert time.monotonic()-start >= .02; print('CALIBRATED_REALTIME_AND_MONOTONIC')"],
            "calibrate-" + label, 10, env)
        if "CALIBRATED_REALTIME_AND_MONOTONIC" not in calibration:
            raise RuntimeError("clock calibration did not execute")
        text = run([binary, "tests::test_det6_actual_wall_clock_jumps_preserve_publication",
                    "--exact", "--nocapture", "--test-threads=1"],
                   "wall-clock-" + label, 90, env)
        if ("running 1 test" not in text or "1 passed; 0 failed" not in text
                or "real_wall_clock_states=6 natural_deadline_release=1 replay_jumps=2" not in text):
            raise RuntimeError("clock fixture did not complete every state")
        REPORT["checks"].append({"timezone": timezone, "status": "PASS", "wall_clock_states": 6,
                                 "natural_deadline_release": 1, "post_release_replay_jumps": 2})
        save()
    run(["cargo", "clippy", "--locked", "--all-features", "--all-targets",
         "--", "-D", "warnings"], "clippy-clock-fixture", 600)
    SOURCE.write_text(ORIGINAL)
    REVIEWER.write_text(REVIEWER_ORIGINAL)
    if SOURCE.read_text() != ORIGINAL or REVIEWER.read_text() != REVIEWER_ORIGINAL:
        raise RuntimeError("source restore failed")
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
    SOURCE.write_text(ORIGINAL)
    REVIEWER.write_text(REVIEWER_ORIGINAL)
