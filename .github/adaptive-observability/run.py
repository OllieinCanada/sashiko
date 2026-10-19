#!/usr/bin/env python3
"""Bounded diagnostic instrumentation, separate from performance acceptance."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import importlib.util
ROOT = Path.cwd()
OUT = ROOT / "adaptive-observability-results"
OUT.mkdir(exist_ok=True)
BASE = "715294a276efee9d39fbb55cf31eef267e96c7b1"
DB = ROOT / "src/db.rs"
COOLDOWN = ROOT / "src/db/cooldown.rs"
PROBE = ROOT / "src/db/hosted_probe.rs"
ORIGINAL_DB = DB.read_text()
ORIGINAL_COOLDOWN = COOLDOWN.read_text()
ENV = os.environ.copy()
ENV["CARGO_TARGET_DIR"] = str(ROOT / "target")
REPORT = {
    "status": "RUNNING", "checkpoint": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
    "base": BASE, "controls": [], "samples": [], "instrumented_callsites": {},
    "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in [DB, COOLDOWN]},
    "limitations": [
        "Diagnostic instrumented debug run; not used for the unchanged performance budgets.",
        "Counts libsql query/execute/execute_batch API calls at conn, tx_conn, tx and stmt callsites in db.rs and db/cooldown.rs.",
        "One execute_batch is one API call, not a count of physical SQLite statements.",
        "Implicit BEGIN/COMMIT inside libsql and SQLite VM operations are not SQL API counts.",
        "Explicit hold is successful BEGIN IMMEDIATE to successful completion, or drop rollback.",
        "Serialized call hold includes statement execution/row draining, not an exact SQLite lock timestamp.",
        "Includes instrumentation overhead; local file-backed SQLite only.",
    ],
}
spec = importlib.util.spec_from_file_location("injector", ROOT / ".github/adaptive-observability/instrument.py")
injector = importlib.util.module_from_spec(spec)
spec.loader.exec_module(injector)

def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")

def run(args, label, cwd=ROOT, env=ENV, timeout=180):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as stream:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=stream,
                                stderr=subprocess.STDOUT, timeout=timeout)
    text = (OUT / (label + ".log")).read_text()
    if result.returncode:
        print(text[-16000:], flush=True)
        raise RuntimeError(label + ": exit " + str(result.returncode))
    print("PASS " + label, flush=True)
    return text

def build(directory, label):
    run(["cargo", "fmt", "--all"], "fmt-" + label, cwd=directory, timeout=60)
    text = run(["cargo", "test", "--locked", "--all-features", "--lib", "--no-run",
                "--message-format=json"], "build-" + label, cwd=directory, timeout=600)
    binaries = []
    for line in text.splitlines():
        try: item = json.loads(line)
        except json.JSONDecodeError: continue
        if (item.get("reason") == "compiler-artifact" and item.get("target", {}).get("kind") == ["lib"]
                and item.get("profile", {}).get("test") and item.get("executable")):
            binaries.append(item["executable"])
    if len(set(binaries)) != 1: raise RuntimeError("ambiguous library artifact")
    binary = OUT / (label + "-tests")
    shutil.copy2(binaries[0], binary)
    REPORT[label + "_binary_sha256"] = hashlib.sha256(binary.read_bytes()).hexdigest()
    save()
    return binary

def install(directory, db_text, cooldown_text=None):
    module = directory / "src/db/hosted_probe.rs"
    module.parent.mkdir(parents=True, exist_ok=True)
    module.write_bytes((ROOT / ".github/adaptive-observability/probe.rs").read_bytes())
    db_text, counts = injector.instrument_db(db_text)
    (directory / "src/db.rs").write_text(db_text)
    if cooldown_text is not None:
        cooldown_text, other = injector.count_calls(cooldown_text)
        (directory / "src/db/cooldown.rs").write_text(cooldown_text)
        counts["cooldown"] = other
    return counts

def main():
    native = (ROOT / ".github/adaptive-validation/native_fixture.rs").read_text()
    native = injector.once(native, "            let started = std::time::Instant::now();",
                           "            crate::db::hosted_probe::reset();\n            let started = std::time::Instant::now();")
    native = injector.once(native, "            let seconds = started.elapsed().as_secs_f64();",
                           "            let seconds = started.elapsed().as_secs_f64();\n            let writer_probe = crate::db::hosted_probe::finish();")
    native = injector.once(native, '"storage": "file-backed", "profile": "instrumentation-free-debug"',
                           '"storage": "file-backed", "profile": "instrumented-debug", "writer_probe": writer_probe')
    controls = (ROOT / ".github/adaptive-observability/controls.rs").read_text()
    closing = ORIGINAL_COOLDOWN.rfind("}")
    candidate_source = ORIGINAL_COOLDOWN[:closing] + native + controls + "\n" + ORIGINAL_COOLDOWN[closing:]
    REPORT["instrumented_callsites"]["candidate"] = install(ROOT, ORIGINAL_DB, candidate_source)
    candidate = build(ROOT, "candidate")
    for name in ["test_probe_sql_counter_calibration", "test_probe_mutex_and_hold_calibration",
                 "test_probe_paused_collaborator_allows_independent_admission"]:
        text = run([str(candidate), name, "--ignored", "--nocapture", "--test-threads=1"], name, timeout=60)
        if "1 passed; 0 failed" not in text: raise RuntimeError("control did not execute")
        markers = [line.split("PROBE_CONTROL ", 1)[1] for line in text.splitlines() if "PROBE_CONTROL " in line]
        if len(markers) != 1: raise RuntimeError("missing control measurement")
        row = {"name": name, "status": "PASS", "probe": json.loads(markers[0])}
        REPORT["controls"].append(row)
        print("CONTROL " + json.dumps(row), flush=True)
        save()
    run(["git", "fetch", "--no-tags", "origin", BASE], "fetch-baseline", timeout=60)
    archive = subprocess.check_output(["git", "archive", BASE], cwd=ROOT)
    baseline_runner = ast.parse((ROOT / ".github/adaptive-baseline-validation/run.py").read_text())
    function = next(node for node in baseline_runner.body if isinstance(node, ast.FunctionDef) and node.name == "baseline_fixture")
    namespace = {}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<baseline-adapter>", "exec"), namespace)
    with tempfile.TemporaryDirectory(prefix="adaptive-instrumented-baseline-") as temporary:
        directory = Path(temporary)
        with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
            stream.extractall(directory, filter="data")
        db_text = (directory / "src/db.rs").read_text() + namespace["baseline_fixture"](native)
        REPORT["instrumented_callsites"]["baseline"] = install(directory, db_text)
        baseline = build(directory, "baseline")
    for retained in [0, 10000]:
        for variant, mode, binary in [("baseline", "disabled", baseline),
                                      ("candidate", "disabled", candidate),
                                      ("candidate", "enabled", candidate)]:
            env = ENV.copy()
            env["COOLDOWN_PROBE_RETAINED"] = str(retained)
            env["COOLDOWN_PROBE_MODE"] = mode
            label = f"probe-{retained}-{variant}-{mode}"
            text = run([str(binary), "test_cooldown_hosted_performance", "--ignored",
                        "--nocapture", "--test-threads=1"], label, env=env)
            markers = [line.split("COOLDOWN_PROBE ", 1)[1] for line in text.splitlines() if "COOLDOWN_PROBE " in line]
            if len(markers) != 1 or "1 passed; 0 failed" not in text: raise RuntimeError("missing workload or probe")
            row = json.loads(markers[0])
            row["variant"] = variant
            if row["writer_probe"]["sql_api_calls"]["query"] <= 0: raise RuntimeError("SQL counters are inactive")
            if row["writer_probe"]["timings"]["explicit_transaction_hold"]["count"] <= 0: raise RuntimeError("writer timers are inactive")
            REPORT["samples"].append(row)
            print("MEASUREMENT " + json.dumps(row, sort_keys=True), flush=True)
            save()
    REPORT["status"] = "PASS"
    save()
    print("RESULT " + json.dumps({"status": "PASS", "controls": len(REPORT["controls"]), "samples": len(REPORT["samples"])}), flush=True)

try:
    save()
    main()
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    raise
finally:
    DB.write_text(ORIGINAL_DB)
    COOLDOWN.write_text(ORIGINAL_COOLDOWN)
    PROBE.unlink(missing_ok=True)
