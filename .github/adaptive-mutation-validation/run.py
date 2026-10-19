#!/usr/bin/env python3
"""Kill focused semantic mutants with positive and unrelated controls."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path.cwd()
OUT = ROOT / "adaptive-mutation-results"
OUT.mkdir(exist_ok=True)
FILES = {path: (ROOT / path).read_text() for path in
         ["src/db.rs", "src/db/cooldown.rs", "src/email_policy.rs"]}
CONTROL = "test_cooldown_legacy_has_no_intent_or_events"
CASES = [
    ("author-scope", "src/db/cooldown.rs",
     "WHERE list = ? AND author = ? AND admitted_at > ?",
     "WHERE list = ? AND ? IS NOT NULL AND admitted_at > ?",
     "test_cooldown_deadline_boundary_clean_exception_and_isolation", "lib"),
    ("frozen-replay", "src/db/cooldown.rs",
     '            if state == "waiting" {\n                let Some(context) = context else {',
     '            if state == "waiting" || state == "decided" {\n                let Some(context) = context else {',
     "test_cooldown_incomplete_out_of_order_and_duplicate", "lib"),
    ("deadline", "src/db.rs", "                 p.embargo_until <= ?",
     "                 p.embargo_until >= ?",
     "test_cooldown_deadline_boundary_clean_exception_and_isolation", "lib"),
    ("release-marker", "src/db.rs",
     "WHERE patchset_id = ? AND state != 'blocked' AND released_at IS NULL",
     "WHERE patchset_id = ? AND state != 'blocked' AND released_at IS NULL AND 0",
     "test_cooldown_release_before_admission_and_no_rehold", "lib"),
    ("enablement", "src/email_policy.rs",
     "if source != crate::events::MessageSource::Nntp {",
     "if source == crate::events::MessageSource::Nntp {",
     "test_cooldown_config_to_real_release_and_sendmail", "bin"),
]
REPORT = {
    "status": "RUNNING",
    "candidate_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "source_sha256": {p: hashlib.sha256(s.encode()).hexdigest() for p, s in FILES.items()},
    "observations": [], "mutants": [],
    "limits": {"build_seconds": 600, "test_seconds": 90},
}


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


def restore():
    for path, text in FILES.items():
        (ROOT / path).write_text(text)


def command(args, label, timeout):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as output:
        result = subprocess.run(args, cwd=ROOT, stdout=output,
                                stderr=subprocess.STDOUT, timeout=timeout)
    return result.returncode, (OUT / (label + ".log")).read_text()


def build(label):
    code, text = command(
        ["cargo", "test", "--locked", "--all-features", "--lib", "--bin", "sashiko",
         "--no-run", "--message-format=json"], "build-" + label, 600)
    if code:
        print(text[-16000:], flush=True)
        raise RuntimeError(label + ": invalid mutant/build failure")
    binaries = {}
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") != "compiler-artifact" or not item.get("executable")
                or not item.get("profile", {}).get("test")):
            continue
        kind = item.get("target", {}).get("kind")
        if kind == ["lib"]:
            binaries["lib"] = item["executable"]
        elif kind == ["bin"] and item["target"]["name"] == "sashiko":
            binaries["bin"] = item["executable"]
    if set(binaries) != {"lib", "bin"}:
        raise RuntimeError("missing library/main test artifact")
    return binaries


def test(binary, name, label, should_fail=False):
    code, text = command([binary, name, "--nocapture", "--test-threads=1"], label, 90)
    if should_fail:
        valid = code == 101 and "0 passed; 1 failed" in text and "running 1 test" in text
    else:
        valid = code == 0 and "1 passed; 0 failed" in text and "running 1 test" in text
    if not valid:
        print(text[-16000:], flush=True)
        raise RuntimeError(label + ": unexpected semantic test outcome")
    REPORT["observations"].append({
        "name": label, "test": name,
        "status": "KILLED" if should_fail else "PASS",
    })
    save()
    print("PASS " + label, flush=True)


try:
    save()
    original = build("unmutated")
    for name, _, _, _, target, kind in CASES:
        test(original[kind], target, "positive-" + name)
    test(original["lib"], CONTROL, "positive-unrelated")
    for name, path, old, new, target, kind in CASES:
        restore()
        if FILES[path].count(old) != 1:
            raise RuntimeError(name + ": mutation anchor is not unique")
        (ROOT / path).write_text(FILES[path].replace(old, new))
        mutated = build(name)
        REPORT["mutants"].append({
            "name": name, "path": path, "before": old, "after": new,
            "sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest(),
            "binary_sha256": hashlib.sha256(Path(mutated[kind]).read_bytes()).hexdigest(),
        })
        save()
        test(mutated[kind], target, "negative-" + name, should_fail=True)
        test(mutated["lib"], CONTROL, "unrelated-under-" + name)
    restore()
    restored = build("restored")
    test(restored["lib"], "test_cooldown_incomplete_out_of_order_and_duplicate",
         "restored-replay")
    REPORT["status"] = "PASS"
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
    raise
finally:
    restore()
