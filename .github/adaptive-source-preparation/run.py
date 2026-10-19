#!/usr/bin/env python3
"""Build checked, source-only signed-off commits without publishing a PR."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path.cwd()
OUT = ROOT / "adaptive-source-preparation"
OUT.mkdir(exist_ok=True)
BASE = "7f92f869a960a20f7d395550b4879d897ebdf4ea"
PREREQUISITE = "a377db68dbd2c2fabfefe3136aea8b4499e4a648"
CANDIDATE = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
IDENTITY = {"name": "Ollie Slapinski", "email": "oliverslapinski@hotmail.com"}
REPORT = {
    "status": "RUNNING", "base": BASE, "candidate_checkpoint": CANDIDATE,
    "prerequisite_snapshot": PREREQUISITE, "identity": IDENTITY,
    "model_review": "BLOCKED: no authenticated provider supplied to this job",
    "commits": [], "checks": [],
    "scope": "source-only preparation artifacts; no upstream PR or push",
}
ENV = os.environ.copy()
ENV["CARGO_TARGET_DIR"] = str(ROOT / "target")
ENV["RUSTUP_TOOLCHAIN"] = "stable"


def save():
    (OUT / "manifest.json").write_text(json.dumps(REPORT, indent=2) + "\n")


def run(args, label, cwd=ROOT, timeout=900):
    print("START " + label, flush=True)
    with (OUT / (label + ".log")).open("w") as output:
        process = subprocess.run(args, cwd=cwd, env=ENV, stdout=output,
                                 stderr=subprocess.STDOUT, timeout=timeout)
    if process.returncode:
        print((OUT / (label + ".log")).read_text()[-16000:], flush=True)
        raise RuntimeError(f"{label}: exit {process.returncode}")
    print("PASS " + label, flush=True)


def output(args, cwd):
    return subprocess.check_output(args, cwd=cwd, env=ENV, text=True).strip()


def restore(source, destination, paths):
    for path in paths:
        data = subprocess.check_output(["git", "show", source + ":" + path], cwd=ROOT)
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    subprocess.run(["git", "add", "--"] + paths, cwd=destination, env=ENV, check=True)


def add_prerequisite_index(directory):
    data = json.loads((ROOT / ".github/adaptive-source-preparation/prerequisite-index.json").read_text())
    source = directory / "src/db.rs"
    text = source.read_text()
    if text.count(data["query"]) != 1 or text.count(data["anchor"]) != 1:
        raise RuntimeError("unexpected prerequisite query layout")
    text = text.replace(data["query"], "SUPERSEDED_SERIES_CANDIDATE_QUERY")
    text = text.replace(data["anchor"], data["constant"] + data["anchor"])
    marker = '        info!("Database schema is up to date at version 13.");'
    if text.count(marker) != 1:
        raise RuntimeError("unexpected prerequisite migration layout")
    text = text.replace(marker, data["migration"] + marker.replace("version 13", "version 14"))
    text = text.replace("mod tests {\n", "mod tests {\n" + data["test"], 1)
    source.write_text(text)
    restore(CANDIDATE, directory, ["src/migrations/014_held_series_index.sql", "src/prerequisites.rs"])
    fixture = directory / "src/prerequisites.rs"
    fixture_text = fixture.read_text()
    if fixture_text.count("assert_eq!(version, 15);") != 1:
        raise RuntimeError("unexpected migration fixture version")
    fixture.write_text(fixture_text.replace("assert_eq!(version, 15);", "assert_eq!(version, 14);"))
    subprocess.run(["git", "add", "--", "src/db.rs", "src/prerequisites.rs"], cwd=directory, env=ENV, check=True)


def checked_commit(directory, message, phase):
    run(["make", "check-pr", "RANGE=" + BASE + "..HEAD"],
        "check-pr-before-" + phase, cwd=directory)
    REPORT["checks"].append({"name": "make check-pr before " + phase, "status": "PASS"})
    save()
    body = message + "\n\nSigned-off-by: " + IDENTITY["name"] + " <" + IDENTITY["email"] + ">\n"
    if any(len(line) > 72 and not line.startswith("Fixes: ") for line in body.splitlines()):
        raise RuntimeError("commit message exceeds 72 columns")
    message_file = OUT / (phase + "-message.txt")
    message_file.write_text(body)
    run(["git", "commit", "--file", str(message_file)], "commit-" + phase, cwd=directory)
    commit = output(["git", "rev-parse", "HEAD"], directory)
    REPORT["commits"].append({
        "phase": phase, "sha": commit,
        "author": output(["git", "show", "-s", "--format=%an <%ae>", commit], directory),
        "changed_files": output(["git", "diff-tree", "--no-commit-id", "--name-only", "-r", commit], directory).splitlines(),
    })
    run(["make", "sob", "RANGE=" + BASE + "..HEAD"], "sob-" + phase, cwd=directory)
    save()


def main():
    # Keep the candidate reviewable even if required checks block commits.
    source_paths = ["src", "docs", "designs", "MAINTAINERS_GUIDE.md"]
    patch = subprocess.check_output(
        ["git", "diff", "--binary", "--full-index", BASE, CANDIDATE, "--"] + source_paths,
        cwd=ROOT)
    (OUT / "candidate-source-unchecked.patch").write_bytes(patch)
    REPORT["unchecked_source_patch_sha256"] = hashlib.sha256(patch).hexdigest()
    REPORT["unchecked_source_patch_scope"] = output(
        ["git", "diff", "--name-only", BASE, CANDIDATE, "--"] + source_paths,
        ROOT).splitlines()
    REPORT["unchecked_source_patch_warning"] = "Review artifact only; not a checked contribution or completed model review"
    save()
    run(["git", "fetch", "--no-tags", "origin", BASE, PREREQUISITE], "fetch-snapshots", timeout=60)
    with tempfile.TemporaryDirectory(prefix="adaptive-source-only-") as temporary:
        directory = Path(temporary) / "source"
        run(["git", "clone", "--no-hardlinks", "--no-checkout", str(ROOT), str(directory)],
            "clone-clean-source", timeout=60)
        run(["git", "checkout", "--detach", BASE], "checkout-base", cwd=directory, timeout=60)
        run(["git", "config", "user.name", IDENTITY["name"]], "configure-author-name", cwd=directory, timeout=30)
        run(["git", "config", "user.email", IDENTITY["email"]], "configure-author-email", cwd=directory, timeout=30)
        if output(["git", "status", "--porcelain"], directory):
            raise RuntimeError("initial source checkout is dirty")
        # Keep the upstream lint compatibility prerequisite separate from
        # supersession and adaptive behavior; no handler body is changed.
        server = directory / "src/server.rs"
        source = server.read_text()
        for name in ["submit_patch", "analyze_bug", "forge_webhook", "create_auth_token"]:
            anchor = "async fn " + name + "("
            if source.count(anchor) != 1:
                raise RuntimeError("unexpected upstream response handler layout")
            source = source.replace(
                anchor,
                "#[allow(clippy::result_large_err)] // Preserve Axum extractor rejection status and body.\n" + anchor)
        server.write_text(source)
        subprocess.run(["git", "add", "--", "src/server.rs"], cwd=directory, env=ENV, check=True)
        target = directory / "target"
        if not target.exists():
            target.symlink_to(ROOT / "target", target_is_directory=True)
        run(["cargo", "build", "--locked", "--all-features", "--bin", "sashiko"],
            "build-upstream-fixture-binary", cwd=directory)
        checked_commit(
            directory,
            "server: allow concrete extractor rejection response size\n\n"
            "Keep the status and body returned by Axum extractor rejections.\n"
            "Scope the large-error lint allowance to the four affected\n"
            "handlers; retain all other warning checks.\n\n"
            "Fixes: 99bc30a9a499 (\"server: authorize /api/submit before reading its body\")\n"
            "Fixes: 7f92f869a960 (\"server: scope 25 MiB body limit and authorize before reading bodies\")",
            "response-lint",
        )
        restore(PREREQUISITE, directory, ["src/db.rs"])
        add_prerequisite_index(directory)
        run(["cargo", "fmt", "--all"], "format-prerequisite", cwd=directory, timeout=60)
        subprocess.run(["git", "add", "--", "src/db.rs"], cwd=directory, env=ENV, check=True)
        checked_commit(
            directory,
            "db: retire superseded series reviews awaiting publication\n\n"
            "Include unpublished Reviewed mail series in supersession. Cancel\n"
            "held reviews and unsent outboxes atomically, preserve active\n"
            "candidate capacity, and respect release after candidate selection.\n\n"
            "Index held candidates separately from archived Reviewed rows.",
            "prerequisite",
        )
        paths = output(
            ["git", "diff", "--name-only", PREREQUISITE, CANDIDATE, "--",
             "src", "docs", "designs", "MAINTAINERS_GUIDE.md"], ROOT).splitlines()
        if not paths or any(path.startswith(".github/") for path in paths):
            raise RuntimeError("invalid source-only candidate range")
        restore(CANDIDATE, directory, paths)
        checked_commit(
            directory,
            "mail: add opt-in per-author publication cooldowns\n\n"
            "Persist one admission per complete canonical revision and retain\n"
            "the longer legacy embargo. Preserve decisions and early release\n"
            "across replay and restart, and quarantine ambiguous ownership.\n\n"
            "Leave deployed mailing-list policy unchanged.",
            "adaptive",
        )
        if output(["git", "status", "--porcelain"], directory):
            raise RuntimeError("prepared source checkout has uncommitted changes")
        REPORT["head"] = output(["git", "rev-parse", "HEAD"], directory)
        REPORT["tree"] = output(["git", "rev-parse", "HEAD^{tree}"], directory)
        patch_directory = OUT / "patches"
        patch_directory.mkdir()
        run(["git", "format-patch", "--output-directory", str(patch_directory),
             BASE + "..HEAD"], "format-source-patches", cwd=directory, timeout=60)
        run(["git", "bundle", "create", str(OUT / "source-only.bundle"),
             BASE + "..HEAD"], "bundle-source-commits", cwd=directory, timeout=60)
        REPORT["patches"] = {
            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
            for path in patch_directory.iterdir()
        }
        REPORT["status"] = "PREPARED_WITH_REVIEW_BLOCKED"
        save()
        print(json.dumps(REPORT, indent=2), flush=True)


try:
    main()
except Exception as error:
    REPORT["status"] = "FAIL"
    REPORT["error"] = str(error)
    save()
    print(json.dumps(REPORT, indent=2), flush=True)
    raise
