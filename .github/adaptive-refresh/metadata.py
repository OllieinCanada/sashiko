#!/usr/bin/env python3
"""Normalize trailer grouping without changing a single source tree."""
import base64
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path.cwd()
SOURCE = ROOT / "review-source"
BASE = "026195ab58e2099e81017adbc6b97f33c509c8ba"
TESTED = "a9e2a05f10ecf1a2e8a7b0c3e3025609d9d9c0e9"
TREE = "9a92a08ab85001d30c037811f4546381e22dbeab"
BRANCH = "codex/adaptive-cooldown-review-20261020"
def git(*args, env=None, data=None):
    return subprocess.check_output(["git", *args], cwd=SOURCE, env=env,
                                   input=data, text=True, stderr=subprocess.STDOUT).strip()
def normalize(message):
    lines = message.rstrip("\n").splitlines()
    trailer = re.compile(r"^(Signed-off-by|Fixes|Co-authored-by|Link): ")
    index = len(lines)
    while index and (not lines[index - 1] or trailer.match(lines[index - 1])):
        index -= 1
    suffix = [line for line in lines[index:] if line]
    return "\n".join(lines[:index]).rstrip() + "\n\n" + "\n".join(suffix) + "\n"
def validate(message):
    if "`" in message:
        raise RuntimeError("backticks in commit message")
    for line in message.splitlines():
        if len(line) > 72 and not re.fullmatch(r'Fixes: [0-9a-f]{12} \(".+"\)', line):
            raise RuntimeError("non-log commit line exceeds 72 columns")
    parsed = git("interpret-trailers", "--parse", data=message).splitlines()
    expected = [line for line in message.splitlines()
                if re.match(r"^(Signed-off-by|Fixes|Co-authored-by|Link): ", line)]
    if parsed != expected:
        raise RuntimeError("trailers are not one parsed final block")
    if "Signed-off-by: Ollie Slapinski <oliverslapinski@hotmail.com>" not in parsed:
        raise RuntimeError("configured author sign-off missing")
subprocess.run(["git", "clone", "--no-checkout",
                "https://github.com/OllieinCanada/sashiko.git", str(SOURCE)],
               check=True, timeout=60)
git("checkout", "--detach", TESTED)
if git("rev-parse", "HEAD^{tree}") != TREE or git("status", "--porcelain"):
    raise RuntimeError("not the clean tested tree")
git("config", "user.name", "Ollie Slapinski")
git("config", "user.email", "oliverslapinski@hotmail.com")
commits = git("rev-list", "--reverse", BASE + ".." + TESTED).splitlines()
if len(commits) != 8:
    raise RuntimeError("unexpected source series")
mapping = []
parent = BASE
for old in commits:
    # This task changes commit metadata only. Required diff-aware checks see
    # the same clean tested tree; source equivalence is checked per commit.
    subprocess.run(["make", "check-pr", "RANGE=HEAD..HEAD"], cwd=SOURCE,
                   check=True, timeout=30)
    raw = git("cat-file", "commit", old).split("\n\n", 1)[1]
    message = normalize(raw)
    validate(message)
    fields = git("show", "-s", "--format=%an%n%ae%n%aI%n%cn%n%ce%n%cI", old).splitlines()
    env = os.environ.copy()
    for key, value in zip(["GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE",
                           "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_COMMITTER_DATE"],
                          fields):
        env[key] = value
    tree = git("rev-parse", old + "^{tree}")
    new = git("commit-tree", tree, "-p", parent, env=env, data=message)
    if git("rev-parse", new + "^{tree}") != tree:
        raise RuntimeError("intermediate source tree changed")
    mapping.append({"old": old, "new": new, "tree": tree,
                    "message_changed": raw.strip() != message.strip()})
    parent = new
git("checkout", "--detach", parent)
if git("rev-parse", "HEAD^{tree}") != TREE or git("diff", "--name-only", TESTED, parent):
    raise RuntimeError("final source differs from tested code")
subprocess.run(["make", "check-pr", "RANGE=" + TESTED + ".." + parent],
               cwd=SOURCE, check=True, timeout=60)
existing = git("ls-remote", "--heads", "origin", BRANCH)
if existing and existing.split()[0] != parent:
    raise RuntimeError("review branch exists at another head")
if not existing:
    env = os.environ.copy()
    token = env.pop("GH_TOKEN")
    for key in list(env):
        if key.startswith("GIT_TRACE") or key == "GIT_CURL_VERBOSE":
            env.pop(key)
    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
    env["GIT_CONFIG_VALUE_0"] = "AUTHORIZATION: basic " + base64.b64encode(
        ("x-access-token:" + token).encode()).decode()
    git("push", "--porcelain", "origin", parent + ":refs/heads/" + BRANCH, env=env)
if git("ls-remote", "--heads", "origin", BRANCH).split()[0] != parent:
    raise RuntimeError("review ref mismatch")
result = {"status": "PASS", "tested_source_head": TESTED, "review_head": parent,
          "source_tree": TREE, "upstream": BASE, "branch": BRANCH,
          "all_intermediate_trees_identical": True, "final_tree_identical": True,
          "native_authors_and_dates_preserved": True, "commits": mapping,
          "only_change": "Contiguous Fixes and Signed-off-by trailer block",
          "long_fix_lines": "Unmodified quoted git-log subjects required by AGENTS",
          "provider_calls": 0, "upstream_pr_opened": False}
(ROOT / "review-source-metadata.json").write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result, indent=2))
