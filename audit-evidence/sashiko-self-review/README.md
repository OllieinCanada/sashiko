# Sashiko-for-Sashiko deterministic validation snapshot

This directory preserves a concise, independently reproducible snapshot for
Sashiko pull requests #447 and #455. It is deliberately separate from both
production pull requests so their cumulative diffs remain focused.

## Scope

- Upstream base: `39f6ce95c797bb40023247916a8b16d0f4aaf0da`
- PR #447: `f436726bda82d9814c83d450e87d77c6b7dd7222`
- PR #455: `d045226e9965ddb8a231f0524df4cfac8444d773`
- PR #467 prerequisite: `9228fcf5704c59d15b5bc6c6ecc32ea67742dbd1`
- Combined audit commit: `ac75d748bc0e6a1332503caf4ed2d27d6f0656d8`
- Combined production tree: `934f2c3ef0463da92d1a43265b2f046b93cb3283`

The combined audit commit is an isolated local composition of current
upstream, #467, #447, and #455. It was not pushed as production code. The Git
tree identity is the authoritative identity for the combined production
content tested below.

## Results

| Area | Result | Evidence and limitation |
|---|---|---|
| Exact-head GitHub CI for #447 | PASS | Signed-off-by, lint, and Rust tests passed at the exact head above. |
| Exact-head GitHub CI for #455 | PASS | Signed-off-by, lint, and Rust tests passed at the exact head above. |
| Combined reviewer-to-worker path | PASS | A real hidden worker loaded the selected Sashiko profile, ran all five workflow stages, reached a deterministic recording provider, and returned a structured result. This did not use a live model. |
| Focused deterministic matrix | PASS | 15 tests passed, covering profile resolution, daemon argument delivery, invalid configuration, compatibility, concurrency, and effective workflow-stage context. |
| Mutation sensitivity | PASS | Removing daemon `--prompts` propagation caused the targeted regression test to fail at the intended assertion. The exact audited tree was restored afterward. |
| Authoritative fixture preservation | PASS | HEAD, HEAD, refs, index, status, relevant tracked bytes, and worker/test-binary hashes matched before and after the real-worker run. |
| Local full repository gate for #447 | FAIL | 534 passed, 1 failed, 1 ignored. The sole failure was an unchanged timing-sensitive backoff test also reproduced on exact current upstream. No #447-caused regression was demonstrated, but the run is not called a pass. |
| Local full repository gate for #455 | FAIL | 531 passed, 1 failed, 1 ignored. The sole failure was the same current-upstream timing test. No #455-caused regression was demonstrated, but the run is not called a pass. |
| #467 current-main replay | PASS (focused) | Static replay was clean and prompt-bundle library tests passed 3/3. This is not a fresh full GitHub CI run. |
| Live model review | NOT RUN | No provider/model inference was authorized or initiated. |
| Historical-PR quality benchmark | NOT RUN | No cases were scored and no labels were exposed to a reviewing model. Precision, sensitivity, false-alert rate, and abstention quality are undefined. |

## Important boundaries

The deterministic integration starts inside the reviewer helper. It proves the
reviewer-to-worker-to-workflow-to-provider-request path. It does not prove a
deployed GitHub webhook, daemon startup/configuration deserialization, live
provider transport, or model review quality.

The source-preservation result applies to the tested disposable fixture. It is
not a general sandbox or security proof for arbitrary same-user processes.

PR #467 must land before or with #455 for reliable upgrades of a prompt bundle
that was already extracted. Fresh installations and direct source-tree
`--prompts` use are not affected by that extraction dependency.

## Reproduction outline

Use Rust and Cargo 1.90.0. Check out the exact identities above in isolated
worktrees, then run the repository-prescribed formatting, lint, sign-off, and
test checks. Construct the combined tree in this order:

1. upstream `main` at the recorded base;
2. PR #467;
3. PR #447;
4. PR #455.

At the external model boundary, substitute a deterministic recording provider.
The accepted proof required all five workflow requests to contain the Sashiko
project identity and override guidance, the final three to contain selected
subsystem guidance, and at least one to contain the reviewed diff. The fixture
must compare source refs, index, status, tracked and relevant untracked bytes
before and after execution.

Do not interpret this document as benchmark evidence. A future quality study
needs a predeclared budget, sealed implementation and prompt, mixed-author
historical cases, reviewer access isolation, frozen raw output, and separate
grading.

## Artifact identities

| Artifact | SHA-256 |
|---|---|
| Accepted test-only audit overlay | `64d4142e9b1bfd5b4c070faad3e81208721de13e2b101d24ad9b184dc37f37f9` |
| Hidden worker | `eb52795349c1421fe4d71bbf9c12c0902791f291e7178e7d6ebbbf1e10fad087` |
| All-feature library test binary | `b81795dba040cf3df13da82686b61f07b620f4f7ab47ae0b862e67c55252c195` |

This branch intentionally contains no raw provider output, credentials,
benchmark labels, grader material, or machine-specific build products. Full
local logs remain private and can be supplied on request after reviewing them
for disclosure safety.
