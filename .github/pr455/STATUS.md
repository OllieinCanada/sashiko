# PR455 test-only replacement

The full required suite passes on repository-pinned Rust 1.90.0. A completed
Sashiko model self-review is the only remaining gate. No upstream PR is open.

- Branch: test/sashiko-guidance-lifecycle-20261021
- Commit: 0eedc1d48af6af589a5be042c007cb27661e8120
- Tree: 61bf3d20aa0951348a328704fc6243ce3ed29722
- Base/current upstream: 9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b
- Changed file: src/workflows/sashiko_patch_review.rs, 247 test-only insertions
- [Completed patch](https://github.com/OllieinCanada/sashiko/commit/0eedc1d48af6af589a5be042c007cb27661e8120.patch)
- [Prepared PR description](PR_DRAFT.md)
- Required title: test: cover Sashiko guidance propagation and finding lifecycle

## Engineering summary

Current main already implements first-party project selection, bundled guides,
analysis, verification and reporting. Existing tests cover those seams separately.

Two new deterministic workflow tests inspect actual AiProvider request payloads:
complete bundled guide contents, selection/order, exclusion of unselected or
missing guides, a nonempty concern reaching verification, structured finding
fields reaching reporting, final report output, and clean-review short-circuiting.
No production code, prompts, dependencies or architecture change.
[Coverage mapping](COVERAGE.md).

The tests start at resolved ProjectId::Sashiko and call the production bundle
selector. Existing CLI tests cover parsing/precedence. Request assertions inspect
AiRequest values rather than provider-specific HTTP serialization.

## Required validation: passed

[Run 39673050262](https://github.com/OllieinCanada/sashiko/actions/runs/39673050262),
checks job 119475643745, executed on the exact source above using Ubuntu 24.04,
rustc 1.90.0 (1159e78c4 2025-09-14), Cargo 1.90.0 and two build jobs.

After cargo fetch --locked, it executed:
make check-pr RANGE=9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b..HEAD

RUSTUP_TOOLCHAIN=1.90.0 and CARGO_NET_OFFLINE=true were set. The hosted shared
target directory was supplied through the existing CLI helper's supported
CARGO_BIN_EXE_sashiko override. No provider secret was available to the tests.

| Check | Result |
| --- | --- |
| Signed-off-by validation | Passed |
| cargo fmt --all -- --check | Passed |
| cargo clippy --all-targets --all-features -- -D warnings | Passed |
| cargo clippy --all-targets --no-default-features -- -D warnings | Passed |
| cargo clippy --all-targets --no-default-features --features cache -- -D warnings | Passed |
| cargo test --all-features | 1008 library + 47 main + 7 CLI + 23 integration = 1085 passed; zero failed; two ignored |
| git diff --check and clean source checkout | Passed |

[Exact check log artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39673050262/artifacts/12380693878).
Tree/hash and the unchanged production prefix were checked before execution;
the checkout stayed clean afterward. Source SHA256:
785d2db3f107d30874584ec44c5233903c6de0b20ae366b5f671eaaa234227f5.

## Earlier results and corrected assessments

Earlier supplemental checks selected Rust 1.99.1 explicitly, bypassing the
repository pin. Newer Clippy reports four async result_large_err diagnostics
in unchanged server code on both upstream and candidate. Those negative results
remain documented; they do not require a server fix, suppression or waiver for
the now-passing prescribed suite. [Toolchain investigation](TOOLCHAIN.md).

The first pinned run passed every lint profile and 1082 tests, but three existing
CLI tests could not find the binary in the harness's shared target directory.
The corrected run used the existing helper's binary override and passed all
1085 tests, without source changes. That first review job was skipped: zero calls.

Earlier Rust 1.99.1 execution passed 13 focused workflow tests, the full suite
and four compiled mutations. Intended regression assertions failed when selected
guidance was dropped, selected order reversed, verified findings discarded, or
unselected guidance injected. The source patch/hash matches the published commit.

- [Focused tests, mutations and supplemental lint diagnostics](https://github.com/OllieinCanada/sashiko/actions/runs/39657476345/artifacts/12372497099)
- [Earlier full suite and native source bundle](https://github.com/OllieinCanada/sashiko/actions/runs/39658748438/artifacts/12373570308)
- [First pinned run with harness failures](https://github.com/OllieinCanada/sashiko/actions/runs/39671889391/artifacts/12380267886)
- [Structured evidence and negative history](evidence.json)

## Required model review: blocked

The additional authorized self-review ran after make check-pr passed. Native
Sashiko --project sashiko review --agent targeted the exact base..head range.
The separate minimal review binary used Rust 1.99.1; it did not change the
reviewed source or offline regression environment.

Offline budget, timeout, redaction and completion controls passed. Authenticated
metadata and token counting succeeded. The first Gemini 3.6 Flash generation
returned HTTP 503 after 0.584 seconds. The proxy stopped immediately. The patch
remains incomplete; empty findings/concerns do not establish a clean review.

This attempt was capped at one dollar and ten minutes. Its conservative
reservation was $0.035577; actual billing is unknown. Both explicitly authorized
attempts have now failed at first-generation HTTP 503. No further calls are
authorized or scheduled. Future execution was disabled at
3f4156d62978380c1088a5476be251a118c4ba22; older provider workflows remain disabled.

[Latest model artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39673050262/artifacts/12381865089).

AGENTS.md requires: "Fix any valid findings, amend or commit, and re-verify
until both make check-pr and the local self-review pass cleanly."
[Exact instructions](https://github.com/sashiko-dev/sashiko/blob/9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b/AGENTS.md).

## Remaining work

1. Complete the required review through a working provider generation path under
   a newly authorized bounded attempt. Resolve valid findings and revalidate
   affected code if any change is needed.
2. Recheck upstream immediately before publication; refresh only if it moved.
3. Open the new PR using the prepared title/body. Do not reopen #455 or merge.

To reproduce locally, honor rust-toolchain.toml, run cargo fetch --locked and
then CARGO_NET_OFFLINE=true make check-pr
RANGE=9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b..HEAD.
A normal clone uses its own target directory and does not need the hosted binary
override. Local execution in this chat remains unavailable because bwrap reports
No space left on device creating /workspace/.git. All successful Rust checks
ran in isolated hosted source checkouts.
