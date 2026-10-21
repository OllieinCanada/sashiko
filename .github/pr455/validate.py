"""Build a test-only Sashiko replacement in an isolated, pinned clone."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path.cwd()
SOURCE = ROOT / "candidate"
OUT = ROOT / "pr455-results"
OUT.mkdir()
os.environ["CARGO_TARGET_DIR"] = str(ROOT / "target")
BASE = "9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b"
BRANCH = "test/sashiko-guidance-lifecycle-20261021"
REPORT = {"status": "RUNNING", "base": BASE, "checks": [], "mutants": [],
          "provider_calls": 0, "pr_opened": False}
def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
def command(name, args, cwd=SOURCE, timeout=1800, expected=0, env=None):
    start = time.monotonic()
    log = OUT / (name + ".log")
    with log.open("w") as stream:
        try:
            result = subprocess.run(args, cwd=cwd, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=timeout, env=env)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    REPORT["checks"].append({"name": name, "command": args, "exit": code,
                             "seconds": round(time.monotonic()-start, 3)})
    save()
    print(json.dumps(REPORT["checks"][-1]), flush=True)
    if expected is not None and code != expected:
        print(log.read_text()[-14000:], flush=True)
        raise RuntimeError(name + " failed")
    return code, log.read_text()
def git(*args):
    return subprocess.check_output(["git", *args], cwd=SOURCE, text=True).strip()
try:
    command("clone", ["git", "clone", "--no-checkout",
            "https://github.com/sashiko-dev/sashiko.git", str(SOURCE)], cwd=ROOT, timeout=60)
    git("checkout", "--detach", BASE)
    assert not git("status", "--porcelain")
    assert subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode != 0
    git("config", "user.name", "Ollie Slapinski")
    git("config", "user.email", "oliverslapinski@hotmail.com")
    git("switch", "-c", BRANCH)
    path = SOURCE / "src/workflows/sashiko_patch_review.rs"
    original = path.read_text()
    pos = original.rfind("}")
    addition = (ROOT / ".github/pr455/test_additions.txt").read_text()
    path.write_text(original[:pos] + addition + original[pos:])
    REPORT["rustc"] = subprocess.check_output(["rustc", "--version"], text=True).strip()
    REPORT["cargo"] = subprocess.check_output(["cargo", "--version"], text=True).strip()
    command("dependencies", ["cargo", "fetch", "--locked"], timeout=240)
    os.environ["CARGO_NET_OFFLINE"] = "true"
    command("format", ["cargo", "fmt", "--all"])
    command("format-check", ["cargo", "fmt", "--all", "--", "--check"])
    (OUT / "candidate.patch").write_text(git("diff") + "\n")
    command("targeted-positive", ["cargo", "test", "--offline", "--all-features",
        "--lib", "workflows::sashiko_patch_review::tests::", "--", "--nocapture"])
    clean = path.read_text()
    mutants = [
      ("missing-selected-guides",
       "if !s.selected_guides.is_empty() {", "if false && !s.selected_guides.is_empty() {",
       "test_bundled_guidance_reaches_analysis_and_finding_report"),
      ("reversed-selected-guides",
       "for guide in &s.selected_guides {", "for guide in s.selected_guides.iter().rev() {",
       "test_bundled_guidance_reaches_analysis_and_finding_report"),
      ("finding-discarded-before-report",
       "apply_verification_stage_output(state, out, outcome, analysis_stage_by_name);",
       "apply_verification_stage_output(state, out, outcome, analysis_stage_by_name); state.findings.clear();",
       "test_bundled_guidance_reaches_analysis_and_finding_report"),
      ("unselected-guide-injected",
       '.include_file("review-core.md")',
       '.include_file("review-core.md").include_file("patterns/resource-limits.md")',
       "test_unselected_and_missing_guidance_stays_out_of_analysis"),
    ]
    for name, old, new, test in mutants:
        assert clean.count(old) == 1, name
        path.write_text(clean.replace(old, new, 1))
        code, log = command("mutant-" + name, ["cargo", "test", "--offline",
            "--all-features", "--lib", test, "--", "--nocapture"], expected=None)
        killed = code == 101 and "test result: FAILED" in log and test in log
        REPORT["mutants"].append({"name": name, "runtime_regression_detected": killed})
        path.write_text(clean)
        save()
        if not killed:
            raise RuntimeError("mutant did not fail at the intended regression: " + name)
    command("restored-targeted", ["cargo", "test", "--offline", "--all-features",
        "--lib", "workflows::sashiko_patch_review::tests::"])

    required_code, required_log = command("required-checks",
        ["make", "check-pr", "RANGE=HEAD..HEAD"], timeout=1800, expected=None)
    known_baseline = False
    if required_code != 0:
        # Attribute the previously observed toolchain lint on the exact base.
        # Do not mask candidate diagnostics or alter the contribution's code.
        lint = ["cargo", "clippy", "--offline", "--all-targets", "--all-features",
                "--message-format=json", "--", "-D", "warnings"]
        path.write_text(original)
        baseline_code, baseline_log = command("baseline-clippy", lint, expected=None)
        path.write_text(clean)
        candidate_code, candidate_log = command("candidate-clippy", lint, expected=None)
        def errors(log):
            found = []
            for line in log.splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("reason") != "compiler-message":
                    continue
                message = row["message"]
                if message["level"] != "error":
                    continue
                spans = [(span["file_name"], span["line_start"], span["column_start"])
                         for span in message["spans"] if span["is_primary"]]
                found.append({"code": (message.get("code") or {}).get("code"),
                              "message": message["message"], "spans": spans})
            unique = {json.dumps(item, sort_keys=True): item for item in found}
            return [unique[key] for key in sorted(unique)]
        baseline_errors = errors(baseline_log)
        candidate_errors = errors(candidate_log)
        known_baseline = (
            baseline_code == candidate_code == 101
            and len(baseline_errors) == 4
            and candidate_errors == baseline_errors
            and all(item["code"] == "clippy::result_large_err"
                    and all(span[0] == "src/server.rs" for span in item["spans"])
                    for item in baseline_errors)
            and "result_large_err" in required_log)
        REPORT["upstream_clippy"] = {"same_exact_diagnostics": known_baseline,
                                    "errors": baseline_errors,
                                    "required_check_exit": required_code}
        save()
        if not known_baseline:
            raise RuntimeError("required checks failed without exact known-baseline attribution")
        command("minimal-clippy", ["cargo", "clippy", "--offline", "--all-targets",
                "--no-default-features", "--", "-D", "warnings"])
        command("cache-clippy", ["cargo", "clippy", "--offline", "--all-targets",
                "--no-default-features", "--features", "cache", "--", "-D", "warnings"])
        command("full-suite", ["cargo", "test", "--offline", "--all-features"])

    command("diff-check", ["git", "diff", "--check"])
    assert git("diff", "--name-only") == "src/workflows/sashiko_patch_review.rs"
    (OUT / "candidate.patch").write_text(git("diff") + "\n")
    message = (
        "test: cover Sashiko guidance propagation and finding lifecycle\n\n"
        "Record actual first-party workflow provider requests to protect\n"
        "bundled guide selection, exact contents and ordering. Carry a\n"
        "nonempty finding through verification into the report request and\n"
        "final output, and reject unintended guide injection.\n\n"
        "Use deterministic in-process providers with no external API calls.\n"
        "Compiled mutations confirm both guidance and finding regressions\n"
        "are caught. This retains the test value of closed PR 455 without\n"
        "its extra profile or project-context mechanism.\n")
    message_path = OUT / "commit-message.txt"
    message_path.write_text(message)
    git("add", "src/workflows/sashiko_patch_review.rs")
    command("commit", ["git", "commit", "-s", "-F", str(message_path)])
    REPORT["head"] = git("rev-parse", "HEAD")
    REPORT["tree"] = git("rev-parse", "HEAD^{tree}")
    REPORT["changed_files"] = git("diff", "--name-only", BASE, "HEAD").splitlines()
    command("final-signoffs", ["make", "sob", "RANGE=" + BASE + "..HEAD"])
    command("export-bundle", ["git", "bundle", "create", str(OUT / "candidate.bundle"),
                             "HEAD", "^" + BASE])
    assert not git("status", "--porcelain")
    REPORT["status"] = "VALIDATED_WITH_UPSTREAM_CLIPPY_FAILURE" if known_baseline else "PASS"
except Exception as error:
    REPORT["status"] = "FAILED"
    REPORT["error"] = str(error)
finally:
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
if REPORT["status"] not in ("PASS", "VALIDATED_WITH_UPSTREAM_CLIPPY_FAILURE"):
    raise SystemExit(1)
