#!/usr/bin/env python3
"""Check two independent source-cost reductions before creating native commits."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

ROOT = Path.cwd()
SOURCE = ROOT / "message-cost-source"
OUT = ROOT / "message-cost-results"
OUT.mkdir(exist_ok=True)
SPEC = json.loads((ROOT / ".github/adaptive-refresh/message-cost.json").read_text())
BASE = "026195ab58e2099e81017adbc6b97f33c509c8ba"
ENV = os.environ.copy()
ENV.update(CARGO_TARGET_DIR=str(ROOT / "target"), CARGO_NET_RETRY="0",
           CARGO_HTTP_TIMEOUT="20", PYTHONDONTWRITEBYTECODE="1")
REPORT = {"status": "RUNNING", "upstream": BASE, "previous_head": SPEC["base"],
          "diagnostic_run": SPEC["diagnostic_run"], "checks": [], "mutants": [],
          "provider_calls": 0, "upstream_pr_opened": False}
def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
def output(args, cwd=SOURCE):
    return subprocess.check_output(args, cwd=cwd, env=ENV, text=True).strip()
def run(args, label, expected=0, cwd=SOURCE, timeout=1800):
    print("START " + label, flush=True)
    if subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError("unexpected running sashiko")
    started = time.monotonic()
    with (OUT / (label + ".log")).open("w") as stream:
        child = subprocess.Popen(args, cwd=cwd, env=ENV, stdout=stream,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = child.wait(timeout=timeout)
        finally:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait()
    text = (OUT / (label + ".log")).read_text()
    REPORT["checks"].append({"name": label, "exit": code,
                             "seconds": time.monotonic() - started})
    save()
    if code != expected:
        print(text[-18000:], flush=True)
        raise RuntimeError(label + ": unexpected exit " + str(code))
    print("PASS " + label, flush=True)
    return text
def test(target, label, count=1, expected=0, oracle=None, exact=True):
    args = ["cargo", "test", "--locked", "--offline", "--all-features", "--lib",
            target, "--", "--nocapture", "--test-threads=1"]
    if exact:
        args.append("--exact")
    text = run(args, label, expected)
    summary = f"{count} passed; 0 failed" if expected == 0 else "0 passed; 1 failed"
    if f"running {count} test" not in text or summary not in text:
        raise RuntimeError("missing exact fixture execution")
    if oracle and oracle not in text:
        raise RuntimeError("mutation failed for an unrelated reason")
def apply(row):
    path = SOURCE / row["path"]
    text = path.read_text()
    if text.count(row["from"]) != 1:
        raise RuntimeError("ambiguous source anchor")
    path.write_text(text.replace(row["from"], row["to"]))
def append_test(path, text):
    source = path.read_text()
    closing = source.rfind("}")
    path.write_text(source[:closing] + text + "\n" + source[closing:])
def required(label):
    text = run(["make", "check-pr", "RANGE=" + BASE + "..HEAD"], label)
    REPORT[label + "_suite"] = [line for line in text.splitlines()
                               if line.startswith("test result:")]
    save()
def commit(paths, message, label):
    run(["git", "add", "--", *paths], "stage-" + label, timeout=30)
    run(["git", "commit", "-s", "-m", message], "commit-" + label, timeout=30)
    REPORT[label + "_commit"] = output(["git", "rev-parse", "HEAD"])
    save()
def main():
    if output(["git", "status", "--porcelain", "--untracked-files=no"], ROOT):
        raise RuntimeError("dirty tracked audit checkout")
    run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(SOURCE)],
        "clone", cwd=ROOT, timeout=60)
    run(["git", "fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", BASE],
        "fetch-upstream", timeout=60)
    run(["git", "fetch", str(ROOT / "input-refresh/rebased-source.bundle"), "HEAD"],
        "fetch-bundle", timeout=60)
    run(["git", "checkout", "--detach", SPEC["base"]], "checkout", timeout=30)
    if output(["git", "rev-parse", "HEAD^{tree}"]) != SPEC["tree"] or output(["git", "status", "--porcelain"]):
        raise RuntimeError("not the clean checked source")
    for key, value in [("user.name", "Ollie Slapinski"),
                       ("user.email", "oliverslapinski@hotmail.com")]:
        run(["git", "config", key, value], "configure-" + key, timeout=30)
    module = SOURCE / "src/db/cooldown.rs"
    previous_module = module.read_text()
    run(["cargo", "fetch", "--locked"], "fetch-dependencies", timeout=120)
    run(["cargo", "clean", "-p", "sashiko"], "clear-generated-paths", timeout=60)
    apply(SPEC["hash"])
    hash_path = SOURCE / SPEC["hash"]["path"]
    append_test(hash_path, SPEC["hash"]["test"])
    run(["cargo", "fmt", "--all"], "format-hash", timeout=60)
    hash_source = hash_path.read_text()
    vector = "cooldown::tests::fingerprints_match_standard_sha256_vectors"
    test(vector, "standard-vectors")
    if hash_source.count('b"0123456789abcdef"') != 1:
        raise RuntimeError("ambiguous hash mutation")
    hash_path.write_text(hash_source.replace('b"0123456789abcdef"', 'b"0123456789abcdeg"'))
    test(vector, "mutant-hash-encoding", expected=101,
         oracle="fingerprint differs from the standard SHA-256 encoding")
    REPORT["mutants"].append({"name": "hash-encoding", "status": "KILLED"})
    hash_path.write_text(hash_source)
    test(vector, "restored-standard-vectors")
    required("required-hash-check")
    commit(["src/cooldown.rs"],
           "cooldown: encode fingerprints without per-byte formatting\n\n"
           "Use a direct lowercase hex lookup for the SHA-256 digest. Preserve\n"
           "persisted fingerprint bytes and verify standard reference vectors.",
           "hash")
    apply(SPEC["message"])
    append_test(module, SPEC["source_test"])
    run(["cargo", "fmt", "--all"], "format-message", timeout=60)
    target = "db::cooldown::tests::test_cooldown_source_guard_precedes_thread_merge"
    test("test_cooldown_source_", "source-guards", count=2, exact=False)
    db = SOURCE / "src/db.rs"
    message_source = db.read_text()
    anchor = "if let Some(owner) = Self::cooldown_owner(&tx, message_id).await? {"
    if message_source.count(anchor) != 1:
        raise RuntimeError("ambiguous owner guard mutation")
    db.write_text(message_source.replace(anchor, "if let Some(owner) = None::<i64> {"))
    test(target, "mutant-source-owner", expected=101,
         oracle="source correction was accepted before thread merge")
    test(vector, "unrelated-hash-control")
    REPORT["mutants"].append({"name": "source-owner-lookup", "status": "KILLED"})
    db.write_text(message_source)
    test("test_cooldown_source_", "restored-source-guards", count=2, exact=False)
    test("db::conflict::tests::", "conflict-controls", count=5, exact=False)
    # Only an additional test was appended to the binding module. Preserve
    # exact function bytes for the three earlier compiled guard mutations.
    spec = importlib.util.spec_from_file_location("scanner", ROOT / ".github/adaptive-observability/instrument.py")
    scanner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scanner)
    def function(text, name):
        code = scanner.mask(text)
        at = code.index("fn " + name + "(")
        opening = code.index("{", at)
        depth, end = 1, opening + 1
        while depth:
            if code[end] == "{": depth += 1
            elif code[end] == "}": depth -= 1
            end += 1
        return text[at:end]
    REPORT["reused_guard_functions"] = {}
    for name in ["bind_cooldown_source_tx", "bind_cooldown_patch_tx", "complete_patchset_tx"]:
        before = function(previous_module, name)
        after = function(module.read_text(), name)
        if before != after:
            raise RuntimeError("guard function changed unexpectedly")
        REPORT["reused_guard_functions"][name] = hashlib.sha256(after.encode()).hexdigest()
    REPORT["previous_guard_evidence"] = SPEC["previous_guard_evidence"]
    required("required-message-check")
    REPORT["suite_summaries"] = REPORT["required-message-check_suite"]
    run(["git", "diff", "--check"], "diff-check", timeout=30)
    commit(["src/db.rs", "src/db/cooldown.rs"],
           "db: defer source ownership lookup until a message exists\n\n"
           "Keep the first message lookup small for new mail. Compare stored\n"
           "source identity using the existing canonical owner query only when\n"
           "a message row exists, in the same immediate writer transaction.\n\n"
           "Preserve quarantine before thread merges even without a current\n"
           "adaptive context.",
           "message")
    run(["make", "sob", "RANGE=" + BASE + "..HEAD"], "final-signoffs", timeout=30)
    if output(["git", "status", "--porcelain"]):
        raise RuntimeError("final source checkout dirty")
    REPORT["head"] = output(["git", "rev-parse", "HEAD"])
    REPORT["tree"] = output(["git", "rev-parse", "HEAD^{tree}"])
    REPORT["commits"] = output(["git", "log", "--format=%H %s", BASE + "..HEAD"]).splitlines()
    run(["git", "bundle", "create", str(OUT / "rebased-source.bundle"), BASE + "..HEAD"],
        "export-bundle", timeout=60)
    (OUT / "rebased-source.patch").write_bytes(subprocess.check_output(
        ["git", "format-patch", "--stdout", BASE + "..HEAD"], cwd=SOURCE))
    REPORT["status"] = "CHECKED_OPTIMIZATION_EXTENDED_PENDING"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
try:
    save()
    main()
except BaseException as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
