#!/usr/bin/env python3
"""Apply and verify the approved candidate in an isolated hosted checkout."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path.cwd()
OUT = ROOT / "adaptive-conflict-native-results"
START_STATUS = subprocess.check_output(["git", "status", "--porcelain"], text=True)
OUT.mkdir(exist_ok=True)
SPEC = json.loads((ROOT / ".github/adaptive-conflict/candidate.json").read_text())
REPORT = {"status": "RUNNING", "checkpoint": subprocess.check_output(
    ["git", "rev-parse", "HEAD"], text=True).strip(),
    "production_base": SPEC["production_base"], "checks": [], "mutants": [],
    "provider_calls": 0, "upstream_pr_opened": False}
ENV = os.environ.copy()
ENV.update({"CARGO_NET_RETRY": "0", "CARGO_HTTP_TIMEOUT": "20",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "localhost,127.0.0.1", "RUST_BACKTRACE": "0"})
ORIGINAL = {}
NEW = set(SPEC["files"])


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


def command(args, label, timeout=900, expected=0, network=False):
    started = time.monotonic()
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        process = subprocess.Popen(args, env=os.environ.copy() if network else ENV,
                                   stdout=stream, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    text = (OUT / (label + ".log")).read_text()
    if code != expected:
        print(text[-20000:], flush=True)
        raise RuntimeError(label + ": unexpected exit " + str(code))
    REPORT["checks"].append({"name": label, "status": "PASS",
                             "seconds": time.monotonic() - started})
    save()
    if label == "required-check-pr":
        REPORT["suite_summaries"] = [
            line for line in text.splitlines() if line.startswith("test result:")]
        print(json.dumps(REPORT["suite_summaries"]), flush=True)
    print("PASS " + label, flush=True)
    return text


def focused(label, expected=0):
    text = command(["cargo", "test", "--locked", "--offline", "--all-features",
                    "--lib", "db::conflict::tests::", "--", "--nocapture",
                    "--test-threads=1"], label, expected=expected)
    if "running 4 tests" not in text:
        raise RuntimeError("missing four-test native fixture control")
    if expected == 0 and "4 passed; 0 failed" not in text:
        raise RuntimeError("incomplete native fixtures")
    return text


try:
    if START_STATUS.strip():
        raise RuntimeError("non-clean starting checkout: " + START_STATUS)
    changed = subprocess.check_output(
        ["git", "diff", "--name-only", SPEC["production_base"], "HEAD", "--", "src"],
        text=True)
    if changed.strip():
        raise RuntimeError("production source no longer matches audited base")
    for row in SPEC["replacements"]:
        path = row["path"]
        ORIGINAL.setdefault(path, (ROOT / path).read_text())
        source = (ROOT / path).read_text()
        if source.count(row["from"]) != 1:
            raise RuntimeError("non-unique replacement anchor in " + path)
        (ROOT / path).write_text(source.replace(row["from"], row["to"], 1))
    for path, source in SPEC["files"].items():
        if (ROOT / path).exists():
            raise RuntimeError("candidate new path already exists")
        (ROOT / path).write_text(source)
    command(["cargo", "fetch", "--locked"], "fetch-locked", 120, network=True)
    paths = [*ORIGINAL, *NEW]
    unformatted = {path: (ROOT / path).read_text() for path in paths}
    command(["cargo", "fmt", "--all"], "format-native", 60)
    formatting = []
    for path in paths:
        before = unformatted[path].splitlines(keepends=True)
        after = (ROOT / path).read_text().splitlines(keepends=True)
        edits = [{"start": a, "end": b, "lines": after[c:d]}
                 for tag, a, b, c, d in difflib.SequenceMatcher(
                     None, before, after, autojunk=False).get_opcodes()
                 if tag != "equal"]
        formatting.append({"path": path, "edits": edits})
    (OUT / "formatting-edits.json").write_text(json.dumps(formatting))
    print("FORMAT_EDITS_JSON " + json.dumps(formatting), flush=True)
    for path in paths:
        destination = OUT / "formatted" / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())
    REPORT["formatted_sha256"] = {
        path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}
    save()
    focused("native-positive")
    migration = ROOT / "src/migrations/016_cooldown_conflicts.sql"
    original_migration = migration.read_text()
    for label, replacement, oracle in [
        ("expose-preparing", "WHERE g.state IN ('preparing','active')",
         "preparing conflict became visible"),
        ("drop-active-guard", "WHERE g.state = 'active' AND 0",
         "group owner escaped quarantine"),
    ]:
        if original_migration.count("WHERE g.state = 'active'") != 1:
            raise RuntimeError("invalid mutation anchor")
        migration.write_text(original_migration.replace("WHERE g.state = 'active'",
                                                        replacement))
        text = focused("mutant-" + label, expected=101)
        if oracle not in text:
            raise RuntimeError("mutant failed for an unrelated reason")
        REPORT["mutants"].append({"name": label, "status": "KILLED",
                                   "intended_assertion": oracle})
        migration.write_text(original_migration)
        save()
    focused("native-restored")
    command(["make", "check-pr", "RANGE=HEAD~1..HEAD"], "required-check-pr", 1800)
    command(["git", "diff", "--check"], "diff-check", 30)
    # Native commit only after the complete required check suite passes.
    command(["git", "config", "user.name", "Ollie Slapinski"], "configure-author", 30)
    command(["git", "config", "user.email", "oliverslapinski@hotmail.com"],
            "configure-email", 30)
    command(["git", "add", "--", *paths], "stage-source", 30)
    command(["git", "commit", "-s", "-m",
             "db: bound adaptive conflict quarantine transactions\n\n"
             "Stage exact conflict membership in bounded writer transactions, then\n"
             "activate all publication guards atomically. Transfer guards to durable\n"
             "owner blocks in bounded batches and recover interrupted work safely.\n\n"
             "Keep ownership tombstones and frozen accounting unchanged."],
            "native-commit", 30)
    command(["make", "sob", "RANGE=HEAD~1..HEAD"], "native-signoff", 30)
    REPORT["native_head"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True).strip()
    REPORT["native_tree"] = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], text=True).strip()
    command(["git", "bundle", "create", str(OUT / "candidate.bundle"),
             REPORT["checkpoint"] + "..HEAD"], "create-native-bundle", 30)
    patch = subprocess.check_output(
        ["git", "format-patch", "--stdout", "-1", "HEAD"], text=True)
    (OUT / "candidate.patch").write_text(patch)
    if subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=no"],
                               text=True).strip():
        raise RuntimeError("tracked source left dirty")
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except BaseException as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
finally:
    # Failed candidates are never published back to the fork source.
    if REPORT["status"] != "PASS":
        for path, source in ORIGINAL.items():
            (ROOT / path).write_text(source)
        for path in NEW:
            (ROOT / path).unlink(missing_ok=True)
