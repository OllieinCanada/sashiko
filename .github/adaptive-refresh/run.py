#!/usr/bin/env python3
"""Rebase isolated signed-off source and refresh deterministic evidence."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

ROOT = Path.cwd()
OUT = ROOT / "refresh-results"
OUT.mkdir(exist_ok=True)
SOURCE = ROOT / "refresh-source"
BASE = "f6e2e172e1e669b6767a4c74fe91d062b41fd71c"
UPSTREAM = "026195ab58e2099e81017adbc6b97f33c509c8ba"
OLD = "6667a81cd25a69feca76e65d94aacb4c83b2ce72"
NATIVE = "b24d9e05094ccfcf7609a46bb254608a3177dea1"
ENV = os.environ.copy()
ENV.update(CARGO_TARGET_DIR=str(ROOT / "target"), CARGO_NET_RETRY="0",
           CARGO_HTTP_TIMEOUT="20", GIT_TERMINAL_PROMPT="0",
           PYTHONDONTWRITEBYTECODE="1")
MANIFEST = OUT / "manifest.json"
REPORT = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {
    "status": "RUNNING", "upstream": UPSTREAM, "original_source": OLD,
    "original_bounded_patch": NATIVE, "checks": [], "provider_calls": 0,
    "upstream_pr_opened": False}
def save():
    MANIFEST.write_text(json.dumps(REPORT, indent=2) + "\n")
def read(args, cwd=SOURCE):
    return subprocess.check_output(args, cwd=cwd, env=ENV, text=True).strip()
def run(args, label, cwd=SOURCE, timeout=1200):
    print("START " + label, flush=True)
    started = time.monotonic()
    if subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError("unexpected existing sashiko process")
    with (OUT / (label + ".log")).open("w") as log:
        p = subprocess.Popen(args, cwd=cwd, env=ENV, stdout=log,
                             stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = p.wait(timeout=timeout)
        finally:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
    text = (OUT / (label + ".log")).read_text()
    REPORT["checks"].append({"name": label, "exit": code,
                             "seconds": time.monotonic() - started})
    save()
    if code:
        print(text[-20000:], flush=True)
        raise RuntimeError(label + ": exit " + str(code))
    print("PASS " + label, flush=True)
    return text
def prepare():
    if read(["git", "status", "--porcelain", "--untracked-files=no"], ROOT):
        raise RuntimeError("audit checkout not clean")
    run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(SOURCE)],
        "clone-source", ROOT, 60)
    run(["git", "fetch", str(ROOT / "input-source/source-only.bundle"), "HEAD"],
        "fetch-clean-bundle", timeout=60)
    run(["git", "cat-file", "-e", OLD + "^{commit}"], "verify-old-source", timeout=30)
    run(["git", "fetch", str(ROOT / "input-native/candidate.bundle"), "HEAD"],
        "fetch-native-bundle", timeout=60)
    run(["git", "cat-file", "-e", NATIVE + "^{commit}"], "verify-native-source", timeout=30)
    run(["git", "fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", UPSTREAM],
        "fetch-upstream", timeout=60)
    run(["git", "checkout", "--detach", OLD], "checkout-clean-source", timeout=30)
    if read(["git", "status", "--porcelain"]):
        raise RuntimeError("source checkout not clean")
    for key, value in [("user.name", "Ollie Slapinski"),
                       ("user.email", "oliverslapinski@hotmail.com")]:
        run(["git", "config", key, value], "configure-" + key, timeout=30)
    try:
        run(["git", "rebase", "--onto", UPSTREAM, BASE], "rebase-source", timeout=120)
    except Exception:
        paths = read(["git", "diff", "--name-only", "--diff-filter=U"]).splitlines()
        REPORT["unmerged_paths"] = paths
        for index, path in enumerate(paths):
            (OUT / ("conflict-" + str(index) + ".txt")).write_text(
                "PATH " + path + "\n" + (SOURCE / path).read_text())
            for stage in [1, 2, 3]:
                data = subprocess.run(["git", "show", ":" + str(stage) + ":" + path],
                                      cwd=SOURCE, capture_output=True, text=True)
                (OUT / ("conflict-" + str(index) + "-stage-" + str(stage))).write_text(data.stdout)
        save()
        raise
    patch = subprocess.check_output(["git", "diff", "--binary", NATIVE + "^", NATIVE,
                                     "--", "src"], cwd=SOURCE)
    (OUT / "bounded.patch").write_bytes(patch)
    patchfile = OUT / "bounded.patch"
    run(["git", "apply", "--3way", "--index", str(patchfile)], "apply-bounded-source", timeout=60)
    run(["cargo", "fetch", "--locked"], "fetch-dependencies", timeout=120)
    text = run(["make", "check-pr", "RANGE=" + UPSTREAM + "..HEAD"],
               "required-check-pr", timeout=1800)
    REPORT["suite_summaries"] = [line for line in text.splitlines()
                                if line.startswith("test result:")]
    run(["git", "diff", "--check"], "diff-check", timeout=30)
    run(["git", "commit", "-s", "-m",
         "db: bound adaptive conflict quarantine transactions\n\n"
         "Stage exact owner membership in bounded transactions and activate\n"
         "publication guards atomically. Recover interrupted handoff while\n"
         "preserving ownership tombstones and frozen accounting."],
        "commit-bounded-source", timeout=30)
    run(["make", "sob", "RANGE=" + UPSTREAM + "..HEAD"], "verify-final-signoffs", timeout=30)
    if read(["git", "status", "--porcelain"]):
        raise RuntimeError("final source checkout dirty")
    REPORT["head"] = read(["git", "rev-parse", "HEAD"])
    REPORT["tree"] = read(["git", "rev-parse", "HEAD^{tree}"])
    REPORT["commits"] = read(["git", "log", "--format=%H %s", UPSTREAM + "..HEAD"]).splitlines()
    REPORT["changed_paths"] = read(["git", "diff", "--name-only", UPSTREAM, "HEAD"]).splitlines()
    run(["git", "bundle", "create", str(OUT / "rebased-source.bundle"),
         UPSTREAM + "..HEAD"], "export-bundle", timeout=60)
    (OUT / "rebased-source.patch").write_bytes(subprocess.check_output(
        ["git", "format-patch", "--stdout", UPSTREAM + "..HEAD"], cwd=SOURCE))
    tree = read(["git", "ls-tree", "-r", "HEAD"]).splitlines()
    (OUT / "source-tree.json").write_text(json.dumps(tree))
    REPORT["status"] = "REBASED_REQUIRED_CHECKS_PASS_EXTENDED_PENDING"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
def supplemental(mode):
    head = REPORT["head"]
    if read(["git", "rev-parse", "HEAD"]) != head:
        raise RuntimeError("unexpected source revision")
    # Copy audit fixtures only, never include them in the contribution.
    for directory in (ROOT / ".github").glob("adaptive-*"):
        if directory.is_dir():
            shutil.copytree(directory, SOURCE / ".github" / directory.name, dirs_exist_ok=True)
    mapping = {
        "deterministic": ("adaptive-deterministic", "bd59059f1864aea81b11b5de0eb97e5d2ec53667"),
        "performance": ("adaptive-baseline-validation", "7f92f869a960a20f7d395550b4879d897ebdf4ea"),
        "rollback": ("adaptive-downgrade", "bd59059f1864aea81b11b5de0eb97e5d2ec53667")}
    folder, old = mapping[mode]
    path = SOURCE / ".github" / folder / "run.py"
    text = path.read_text()
    if mode == "performance":
        text = text.replace(old, UPSTREAM)
        text = text.replace('"repeat_of": "39297399851",',
                            '"scope": "fresh upstream and rebased conflict source",')
    else:
        if text.count(old) != 1:
            raise RuntimeError("ambiguous frozen source guard")
        text = text.replace(old, head)
    if mode == "rollback":
        text = text.replace('"review_cooldown_clock", "meta"]',
                            '"review_cooldown_clock", "review_cooldown_conflicts", '
                            '"review_cooldown_conflict_members", "meta"]')
    path.write_text(text)
    REPORT[mode + "_runner_sha256"] = hashlib.sha256(text.encode()).hexdigest()
    save()
    try:
        run(["python3", str(path)], mode, timeout=1800)
    finally:
        manifest = SOURCE / (folder + "-results") / "manifest.json"
        if folder == "adaptive-baseline-validation":
            manifest = SOURCE / "adaptive-baseline-results/manifest.json"
        if manifest.exists():
            value = json.loads(manifest.read_text())
            REPORT[mode] = value
            (OUT / (mode + "-manifest.json")).write_text(json.dumps(value, indent=2))
        REPORT["tracked_source_restored"] = not bool(read(["git", "diff", "--name-only", "HEAD", "--", "src"]))
        save()
    if not REPORT["tracked_source_restored"]:
        raise RuntimeError("supplemental harness left source dirty")
try:
    save()
    mode = sys.argv[1]
    prepare() if mode == "prepare" else supplemental(mode)
except BaseException as error:
    REPORT["last_error"] = str(error)
    REPORT["failed_phase"] = sys.argv[1]
    save()
    raise
