#!/usr/bin/env python3
"""Diagnostic callsite timings; never used as a performance acceptance retry."""
import ast
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import tempfile

ROOT = Path.cwd()
SOURCE = ROOT / "diagnostic-source"
OUT = ROOT / "diagnostic-results"
OUT.mkdir(exist_ok=True)
META = json.loads((ROOT / "input-refresh/manifest.json").read_text())
ENV = os.environ.copy()
ENV.update(CARGO_TARGET_DIR=str(ROOT / "target"), CARGO_NET_RETRY="0",
           CARGO_HTTP_TIMEOUT="20", PYTHONDONTWRITEBYTECODE="1")
REPORT = {"status": "RUNNING", "head": META["head"], "upstream": META["upstream"],
          "scope": "Instrumented diagnostic; not a budget rerun or production performance claim.",
          "samples": [], "checks": [], "callsites": {}, "provider_calls": 0}
spec = importlib.util.spec_from_file_location("scanner", ROOT / ".github/adaptive-observability/instrument.py")
scanner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scanner)
def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")
def run(args, label, cwd=SOURCE, env=ENV, timeout=900):
    print("START " + label, flush=True)
    if subprocess.run(["pgrep", "-x", "sashiko"], stdout=subprocess.DEVNULL).returncode == 0:
        raise RuntimeError("unexpected running sashiko")
    with (OUT / (label + ".log")).open("w") as log:
        child = subprocess.Popen(args, cwd=cwd, env=env, stdout=log,
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
    if code:
        print(text[-18000:], flush=True)
        raise RuntimeError(label + ": exit " + str(code))
    REPORT["checks"].append({"name": label, "status": "PASS"})
    save()
    print("PASS " + label, flush=True)
    return text
def instrument(text, filename):
    code = scanner.mask(text)
    functions = list(re.finditer(r"\bfn\s+(\w+)\s*\(", code))
    def function(at):
        names = [f.group(1) for f in functions if f.start() < at]
        return names[-1] if names else "module"
    edits = []
    labels = {}
    pattern = r"\b(?:self\s*\.\s*)?(?:conn|tx_conn|tx|stmt)\s*\.\s*(query|execute|execute_batch|transaction_with_behavior|commit|rollback)\s*\("
    matches = [(m, m.group(1)) for m in re.finditer(pattern, code)]
    for match in re.finditer(r"\b\w+\s*\.\s*(next)\s*\(\s*\)(?=\s*\.\s*await)", code):
        matches.append((match, "next"))
    for match, kind in matches:
        opening = code.index("(", match.start())
        depth = 1
        end = opening + 1
        while depth:
            if code[end] == "(": depth += 1
            elif code[end] == ")": depth -= 1
            end += 1
        base = filename + ":" + function(match.start()) + ":" + kind
        labels[base] = labels.get(base, 0) + 1
        label = base + ":" + str(labels[base])
        edits.append((end, ")"))
        edits.append((match.start(), "crate::db::cost_probe::measure(" + json.dumps(label) + ", "))
    spans = {"create_message_with_references", "create_patchset",
             "create_patch_with_git_patch_id", "write_patch_transaction",
             "bind_cooldown_patch_tx", "complete_patchset_tx", "cooldown_owner"}
    for match in functions:
        if match.group(1) in spans:
            opening = code.index("{", match.end())
            label = "SPAN:" + filename + ":" + match.group(1)
            edits.append((opening + 1, "\nlet _cost_span = crate::db::cost_probe::Span::new(" + json.dumps(label) + ");\n"))
    for at, addition in sorted(edits, reverse=True):
        text = text[:at] + addition + text[at:]
    return text, labels
def build(directory, label):
    run(["cargo", "clean", "-p", "sashiko"], "clear-generated-" + label, cwd=directory, timeout=60)
    run(["cargo", "fmt", "--all"], "format-" + label, cwd=directory, timeout=60)
    text = run(["cargo", "test", "--locked", "--offline", "--all-features",
                "--lib", "--no-run", "--message-format=json"], "build-" + label, cwd=directory)
    binaries = []
    for line in text.splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (item.get("reason") == "compiler-artifact" and item.get("target", {}).get("kind") == ["lib"]
                and item.get("profile", {}).get("test") and item.get("executable")):
            binaries.append(item["executable"])
    if len(set(binaries)) != 1:
        raise RuntimeError("ambiguous library artifact")
    binary = OUT / (label + "-tests")
    shutil.copy2(binaries[0], binary)
    return binary
def install(directory, candidate, fixture):
    db = directory / "src/db.rs"
    text = db.read_text()
    if candidate:
        cooldown = directory / "src/db/cooldown.rs"
        value = cooldown.read_text()
        closing = value.rfind("}")
        cooldown.write_text(value[:closing] + fixture + "\n" + value[closing:])
        paths = ["src/db.rs", "src/db/cooldown.rs", "src/db/conflict.rs"]
    else:
        tree = ast.parse((ROOT / ".github/adaptive-baseline-validation/run.py").read_text())
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "baseline_fixture")
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "<baseline-adapter>", "exec"), namespace)
        db.write_text(text + namespace["baseline_fixture"](fixture))
        paths = ["src/db.rs"]
    for path in paths:
        value, labels = instrument((directory / path).read_text(), path)
        (directory / path).write_text(value)
        REPORT["callsites"][("candidate" if candidate else "baseline") + ":" + path] = labels
    with db.open("a") as stream:
        stream.write('\n#[cfg(feature = "server")]\npub mod cost_probe;\n')
    (directory / "src/db/cost_probe.rs").write_bytes((ROOT / ".github/adaptive-refresh/cost_probe.rs").read_bytes())
def main():
    run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(SOURCE)], "clone", ROOT, timeout=60)
    run(["git", "fetch", "--no-tags", "https://github.com/sashiko-dev/sashiko.git", META["upstream"]], "fetch-upstream", timeout=60)
    run(["git", "fetch", str(ROOT / "input-refresh/rebased-source.bundle"), "HEAD"], "fetch-bundle", timeout=60)
    run(["git", "checkout", "--detach", META["head"]], "checkout", timeout=30)
    if subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=SOURCE, text=True).strip() != META["tree"]:
        raise RuntimeError("unexpected source tree")
    original = {p: (SOURCE / p).read_text() for p in ["src/db.rs", "src/db/cooldown.rs", "src/db/conflict.rs"]}
    fixture = (ROOT / ".github/adaptive-validation/native_fixture.rs").read_text()
    fixture = scanner.once(fixture, "            let started = std::time::Instant::now();",
        '            crate::db::cost_probe::reset();\n'
        '            let _ = crate::db::cost_probe::measure("CONTROL", db.conn.query("SELECT 1", ())).await?;\n'
        '            let control = crate::db::cost_probe::snapshot();\n'
        '            assert_eq!(control["CONTROL"]["calls"], 1);\n'
        '            assert!(control["CONTROL"]["total_ns"].as_u64().unwrap() > 0);\n'
        '            crate::db::cost_probe::reset();\n'
        '            let started = std::time::Instant::now();')
    fixture = scanner.once(fixture, '"storage": "file-backed", "profile": "instrumentation-free-debug"',
        '"storage": "file-backed", "profile": "api-cost-diagnostic", "api_cost": crate::db::cost_probe::snapshot()')
    try:
        run(["cargo", "fetch", "--locked"], "fetch-dependencies", timeout=120)
        install(SOURCE, True, fixture)
        candidate = build(SOURCE, "candidate")
        archive = subprocess.check_output(["git", "archive", META["upstream"]], cwd=SOURCE)
        with tempfile.TemporaryDirectory(prefix="adaptive-cost-baseline-") as tmp:
            baseline_root = Path(tmp)
            with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
                stream.extractall(baseline_root, filter="data")
            install(baseline_root, False, fixture)
            baseline = build(baseline_root, "baseline")
        for retained in [0, 10000]:
            for variant, mode, binary in [("baseline", "disabled", baseline),
                                           ("candidate", "disabled", candidate),
                                           ("candidate", "enabled", candidate)]:
                env = ENV.copy()
                env.update(COOLDOWN_PROBE_MODE=mode, COOLDOWN_PROBE_RETAINED=str(retained))
                text = run([str(binary), "test_cooldown_hosted_performance", "--ignored",
                            "--nocapture", "--test-threads=1"], f"{variant}-{mode}-{retained}", env=env, timeout=180)
                markers = [line.split("COOLDOWN_PROBE ", 1)[1] for line in text.splitlines() if "COOLDOWN_PROBE " in line]
                if len(markers) != 1 or "1 passed; 0 failed" not in text:
                    raise RuntimeError("missing diagnostic workload")
                row = json.loads(markers[0])
                row["variant"] = variant
                if not any(key.startswith("SPAN:") for key in row["api_cost"]):
                    raise RuntimeError("span instrumentation inactive")
                if not any(":query:" in key for key in row["api_cost"]):
                    raise RuntimeError("query instrumentation inactive")
                REPORT["samples"].append(row)
                print("DIAGNOSTIC " + json.dumps(row), flush=True)
                save()
        REPORT["status"] = "PASS"
        save()
        print(json.dumps({"status": "PASS", "samples": len(REPORT["samples"])}), flush=True)
    finally:
        for path, text in original.items():
            (SOURCE / path).write_text(text)
        (SOURCE / "src/db/cost_probe.rs").unlink(missing_ok=True)
try:
    save()
    main()
except BaseException as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
