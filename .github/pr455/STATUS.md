# PR455 test-only replacement

Implementation is complete and published; required model self-review is blocked.
No upstream PR has been opened.

- Branch: test/sashiko-guidance-lifecycle-20261021
- Commit: 0eedc1d48af6af589a5be042c007cb27661e8120
- Tree: 61bf3d20aa0951348a328704fc6243ce3ed29722
- Base: 9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b
- Changed file: src/workflows/sashiko_patch_review.rs (247 test-only insertions)
- [Download the completed patch](https://github.com/OllieinCanada/sashiko/commit/0eedc1d48af6af589a5be042c007cb27661e8120.patch)
- [Prepared PR description](PR_DRAFT.md)
- Required title: test: cover Sashiko guidance propagation and finding lifecycle

## Engineering summary

Current main already contains first-party project selection, embedded and
installed Sashiko guidance, selected-guide loading, analysis, verification and
reporting. Existing tests cover CLI selection, bundle integrity, generic prompt
rendering, verification/reducer behavior and output validators separately.

Two new workflow tests connect those seams at the actual AiProvider request
boundary. They call project_prompts_path(ProjectId::Sashiko), execute the existing
complete workflow with a recording provider, compare complete bundled guide
contents and selected order, inspect nonempty verification/report inputs and
final structured fields, and check unselected/missing guidance and clean output.
No duplicated profile, optional context injection, dependency or production
architecture is introduced. [Coverage mapping](COVERAGE.md).

Four independently compiled mutations trigger real assertion failures. The same
candidate patch/source hash is carried between the mutation and full-suite jobs;
the tests are not re-certified by merely renaming a commit.

## Actual executed checks

| Command | Outcome |
| --- | --- |
| cargo fmt --all -- --check | Passed |
| cargo test --offline --all-features --lib workflows::sashiko_patch_review::tests:: | 13 passed |
| cargo test --offline --all-features | 1008 library + 47 main + 7 CLI + 23 integration = 1085 passed; zero failed; two ignored |
| cargo clippy --offline --all-targets --no-default-features -- -D warnings | Passed |
| cargo clippy --offline --all-targets --no-default-features --features cache -- -D warnings | Passed |
| make check-pr RANGE=HEAD..HEAD on the uncommitted candidate | Failed at strict all-feature Clippy |
| cargo clippy --offline --all-targets --all-features --message-format=json -- -D warnings | Same four unique result_large_err failures on untouched base and candidate |
| make sob RANGE=9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b..HEAD | Passed after native signed-off commit |
| git diff --check | Passed |

Strict all-feature errors are at src/server.rs:438, :1679, :2216 and :6284.
Both library and test compilations emit them, yielding eight raw messages but
four unique diagnostics. Exact base/candidate comparison accounts for this;
the failures remain failures. No source suppression was added.

Executed environment: GitHub Actions Ubuntu 24.04, rustc
1.99.1 (58cf8f9c3 2026-10-13), Cargo 1.99.1, CARGO_BUILD_JOBS=2.
Dependencies were fetched with cargo fetch --locked; regression execution then
used CARGO_NET_OFFLINE=true / --offline. The regression suite used no credentials
or external provider API calls. Local execution was unavailable because bwrap
reported No space left on device creating /workspace/.git.

- [Focused tests, mutations and baseline diagnostics](https://github.com/OllieinCanada/sashiko/actions/runs/39657476345/artifacts/12372497099)
- [Full suite, profiles, native patch and source bundle](https://github.com/OllieinCanada/sashiko/actions/runs/39658748438/artifacts/12373570308)
- [Publication and one authorized review](https://github.com/OllieinCanada/sashiko/actions/runs/39659481289)
- [Model outcome](https://github.com/OllieinCanada/sashiko/actions/runs/39659481289/artifacts/12373351714)
- [Structured evidence](evidence.json)

## Separate required model review

The user explicitly authorized one bounded self-review while keeping tests
offline. Gemini 3.6 Flash was attempted at a $1/600-second ceiling, 24 requests,
500000 aggregate counted input tokens and 8192 maximum output tokens per request.
The offline budget/timeout/redaction/completion controls passed first.

Authenticated metadata and countTokens succeeded. The first generateContent
returned HTTP 503 after 0.551 seconds. The proxy stopped immediately; the agent
reported the single patch incomplete. Empty findings/concerns are not a clean
review. The conservative reservation is $0.035577; actual billing is unknown.
Future workflow execution was disabled at
3cd18461b42af5eb09488ca80dfbb8d23a72f20c. No retry is scheduled.

AGENTS.md requires the local agent loop before opening/updating a PR:
"Fix any valid findings, amend or commit, and re-verify until both
make check-pr and the local self-review pass cleanly."
[Exact instructions](https://github.com/sashiko-dev/sashiko/blob/9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b/AGENTS.md).
Neither the model failure nor known upstream lint failures is silently waived.

## Exact remaining steps

1. Recheck current main and the four upstream all-feature Clippy diagnostics.
   Refresh/revalidate the test patch if upstream changes. Keep unrelated server
   fixes outside this contribution.
2. When a working provider generation path is available, configure it securely
   and complete the required local command from the source checkout:
   sashiko --project sashiko review --agent 9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b..HEAD
   Resolve valid findings and repeat applicable checks/review under an explicit
   budget. No further calls are authorized or scheduled by this handoff.
3. Open the PR using the required title and the prepared description after the
   repository review/check requirements are satisfied. PR creation was not
   attempted while self-review was incomplete. Do not reopen #455 or merge.

To reproduce the deterministic checks, clone the source branch, run
cargo fetch --locked if dependencies are not cached, then run the commands in
the table (using RANGE=9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b..HEAD for make check-pr
in the committed source checkout). The source branch and commit patch remain
available after hosted log/artifact retention expires.
