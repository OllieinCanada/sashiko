## Summary

Adds two deterministic regression tests for the first-party --project sashiko
review path using installed bundled prompts and an in-process recording provider.

## Motivation

Retains the test-related value of closed #455, following Kees Cook's feedback
about the existing first-party profile. Production functionality already exists;
the remaining gap is proving selected guidance reaches provider requests and a
nonempty finding continues from analysis through verification into reporting.

No production code, prompts, dependencies or workflow architecture change.
This does not require #447 or #467.

## Coverage

- Complete bundled core and selected guide contents reach actual analysis
  AiRequest payloads once, with selected-guide order preserved.
- The real pre-screen keeps eligible guides and filters stage-exclusive guides;
  unselected and missing optional guides stay out of analysis.
- A nonempty concern reaches verification, retains severity, source lineage,
  stage and source-location fields, and appears as structured data in the report
  provider request and in the final plain-text report.
- A clean review skips verification/report and retains its summary.

Existing CLI project parsing/precedence and bundle integrity tests cover their
respective seams. The new tests start at the resolved Sashiko project and call
the actual production bundle selector; they do not add another CLI harness.

## Validation

Exact source: 0eedc1d48af6af589a5be042c007cb27661e8120
Base: 9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b
Environment: Ubuntu 24.04, rustc 1.99.1, Cargo 1.99.1, build jobs 2.

Passed:

- cargo fmt --all -- --check
- cargo test --offline --all-features --lib workflows::sashiko_patch_review::tests::
  (13 tests)
- cargo test --offline --all-features
  (1085 passed, zero failed, two ignored)
- cargo clippy --offline --all-targets --no-default-features -- -D warnings
- cargo clippy --offline --all-targets --no-default-features --features cache -- -D warnings
- Signed-off-by and git diff --check
- Four compiled mutations failed the intended regression assertions:
  dropped selected guides, reversed guide order, finding discarded before
  reporting, and an unselected guide injected into requests.

Not passed:

- Strict all-feature Clippy and make check-pr fail on four unchanged
  result_large_err diagnostics in src/server.rs. The exact untouched base and
  candidate produce identical diagnostic codes, messages and locations.
  No lint waiver or unrelated production fix was added.
- Required Sashiko agent self-review was attempted once with a bounded budget.
  The provider returned HTTP 503 on its first generation; no review completed.
  Further execution is disabled. This draft is not submitted while that gate
  remains outstanding.

[Reproducible validation and scope](https://github.com/OllieinCanada/sashiko/blob/codex/pr455-guidance-validation-20261021/.github/pr455/STATUS.md)

## References

- #455
- [Kees Cook's feedback concerning --project sashiko](https://github.com/sashiko-dev/sashiko/pull/455#issuecomment-6158258696)
