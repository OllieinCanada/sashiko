#!/usr/bin/env python3
"""Fork-only bounded native validation; never calls an AI provider."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import statistics
import subprocess
import tempfile
import time

ROOT = Path.cwd()
OUT = ROOT / "adaptive-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "src/db/cooldown.rs"
ORIGINAL = SOURCE.read_text()
FIXTURE = (ROOT / ".github/adaptive-validation/native_fixture.rs").read_text()
REPORT = {
    "status": "RUNNING",
    "source_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "fixture_sha256": hashlib.sha256(FIXTURE.encode()).hexdigest(),
    "build_profile": "debug",
    "seed": "fixed index trace, 1000 series, 1/2/4/8 parts",
    "retained_state": "synthetic decided owners after event pruning; 0 or 10000",
    "repetitions": 3,
    "budgets": {"candidate_disabled_over_reference_disabled": 1.20,
                "candidate_enabled_over_candidate_disabled": 1.50,
                "case_timeout_seconds": 180,
                "minimum_free_bytes": 3 * 1024 ** 3},
    "limitations": [
        "Reference isolates the old owner query inside the current candidate.",
        "This is not a full comparison against unmodified upstream.",
        "Serial file-backed debug workload; no production latency claim.",
        "Retained owners are synthetic, not a historical ingestion replay.",
        "No SQL API counters or explicit writer hold/wait instrumentation.",
        "Process restart uses exit after commit, not power-loss simulation.",
        "No authenticated Sashiko model provider is supplied to this workflow.",
    ],
    "validation": [],
    "samples": [],
    "binaries": {},
}
OLD_QUERY = ('const COOLDOWN_OWNER_QUERY: &str = "SELECT patchset_id FROM '
             'review_cooldown_messages WHERE message_id = ? UNION ALL SELECT '
             'b.patchset_id FROM review_cooldown_guards b JOIN patchsets p ON '
             'p.id = b.patchset_id WHERE p.cover_letter_message_id = ? UNION ALL '
             'SELECT b.patchset_id FROM review_cooldown_guards b JOIN patches p '
             'ON p.patchset_id = b.patchset_id WHERE p.message_id = ? LIMIT 1";')


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


def command(args, name, env=None, timeout=180, expected=0):
    started = time.monotonic()
    with (OUT / (name + ".log")).open("w") as output:
        result = subprocess.run(args, cwd=ROOT, env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=timeout)
    elapsed = time.monotonic() - started
    if result.returncode != expected:
        raise RuntimeError(f"{name}: exit {result.returncode}, expected {expected}")
    return (OUT / (name + ".log")).read_text(), elapsed


def build(variant):
    source = ORIGINAL
    if variant == "reference":
        start = source.index("const COOLDOWN_OWNER_QUERY:")
        end = source.index('";', start) + 2
        source = source[:start] + OLD_QUERY + source[end:]
    closing = source.rfind("}")
    SOURCE.write_text(source[:closing] + FIXTURE + "\n" + source[closing:])
    command(["cargo", "fmt", "--all"], "fmt-" + variant, timeout=60)
    text, _ = command(
        ["cargo", "test", "--locked", "--all-features", "--lib", "--no-run",
         "--message-format=json"], "build-" + variant, timeout=600)
    candidates = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact"
                and item.get("target", {}).get("kind") == ["lib"]
                and item.get("profile", {}).get("test")
                and item.get("executable")):
            candidates.append(item["executable"])
    if len(set(candidates)) != 1:
        raise RuntimeError(f"unexpected test executables: {candidates}")
    executable = OUT / (variant + "-tests")
    shutil.copy2(candidates[0], executable)
    REPORT["binaries"][variant] = {
        "sha256": hashlib.sha256(executable.read_bytes()).hexdigest(),
        "instrumented_source_sha256": hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
    }
    save()
    return executable


def test(binary, name, env=None, expected=0):
    return command([str(binary), name, "--ignored", "--nocapture",
                    "--test-threads=1"], name + ("-" + env["COOLDOWN_RESTART_PHASE"]
                    if env and "COOLDOWN_RESTART_PHASE" in env else ""),
                   env=env, expected=expected)


def main():
    tracked = subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0")
    REPORT["tracked_content_sha256"] = {
        os.fsdecode(path): hashlib.sha256(Path(os.fsdecode(path)).read_bytes()).hexdigest()
        for path in tracked if path and Path(os.fsdecode(path)).is_file()
    }
    save()
    candidate = build("candidate")
    for name in ["test_cooldown_hosted_maximum_series",
                 "test_cooldown_hosted_history_read_fault"]:
        text, elapsed = test(candidate, name)
        if "1 passed; 0 failed" not in text:
            raise RuntimeError(f"{name}: expected one passing test")
        REPORT["validation"].append({"name": name, "status": "PASS", "seconds": elapsed})
        save()
    with tempfile.TemporaryDirectory(prefix="cooldown-restart-") as directory:
        for phase, expected in [("write", 23), ("read", 0)]:
            env = os.environ.copy()
            env["COOLDOWN_RESTART_PATH"] = str(Path(directory) / "restart.db")
            env["COOLDOWN_RESTART_PHASE"] = phase
            text, elapsed = test(candidate, "test_cooldown_hosted_process_restart",
                                 env=env, expected=expected)
            if phase == "read" and "1 passed; 0 failed" not in text:
                raise RuntimeError("restart verification did not run")
            REPORT["validation"].append({"name": "process-restart-" + phase,
                                         "status": "PASS", "seconds": elapsed})
            save()
    reference = build("reference")
    variants = {"reference": reference, "candidate": candidate}
    for repetition in range(3):
        order = ["reference", "candidate"] if repetition % 2 == 0 else ["candidate", "reference"]
        for retained in [0, 10000]:
            for mode in ["disabled", "enabled"]:
                for variant in order:
                    if shutil.disk_usage(ROOT).free < REPORT["budgets"]["minimum_free_bytes"]:
                        raise RuntimeError("free disk below frozen floor")
                    env = os.environ.copy()
                    env["COOLDOWN_PROBE_MODE"] = mode
                    env["COOLDOWN_PROBE_RETAINED"] = str(retained)
                    label = f"performance-{repetition}-{retained}-{mode}-{variant}"
                    text, elapsed = command(
                        [str(variants[variant]), "test_cooldown_hosted_performance",
                         "--ignored", "--nocapture", "--test-threads=1"],
                        label, env=env)
                    marker = "COOLDOWN_PROBE "
                    lines = [line.split(marker, 1)[1] for line in text.splitlines() if marker in line]
                    if len(lines) != 1 or "1 passed; 0 failed" not in text:
                        raise RuntimeError(f"{label}: missing success/measurement")
                    sample = json.loads(lines[0])
                    sample.update(variant=variant, repetition=repetition, process_seconds=elapsed)
                    REPORT["samples"].append(sample)
                    save()
    summaries = []
    for retained in [0, 10000]:
        medians = {}
        for variant in variants:
            for mode in ["disabled", "enabled"]:
                values = [x["seconds"] for x in REPORT["samples"]
                          if x["retained"] == retained and x["mode"] == mode
                          and x["variant"] == variant]
                medians[f"{variant}_{mode}"] = statistics.median(values)
        disabled_ratio = medians["candidate_disabled"] / medians["reference_disabled"]
        enabled_ratio = medians["candidate_enabled"] / medians["candidate_disabled"]
        summaries.append({
            "retained": retained, "median_seconds": medians,
            "candidate_disabled_over_reference_disabled": disabled_ratio,
            "candidate_enabled_over_candidate_disabled": enabled_ratio,
            "budget_pass": disabled_ratio <= 1.20 and enabled_ratio <= 1.50,
        })
    REPORT["comparisons"] = summaries
    REPORT["status"] = "PASS" if all(x["budget_pass"] for x in summaries) else "FAIL_BUDGET"
    save()
    print(json.dumps({key: REPORT[key] for key in ["status", "validation", "comparisons"]}, indent=2))
    if REPORT["status"] != "PASS":
        raise SystemExit(2)


try:
    main()
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
finally:
    SOURCE.write_text(ORIGINAL)
