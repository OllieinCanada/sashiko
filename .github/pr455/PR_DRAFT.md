## Summary

Adds two deterministic regression tests connecting existing first-party
--project sashiko guidance, analysis requests, verification and reporting.

## Motivation

Retains the test-related value of closed #455, following Kees Cook's feedback
about the existing first-party profile. No production code, prompts, dependencies
or workflow architecture change. This does not depend on #447 or #467.

## Coverage

- Complete bundled core and selected guide contents reach actual analysis
  AiRequest payloads once, preserving selected-guide order.
- Prescreening filters stage-exclusive guides; unselected and missing optional
  guides stay out of analysis.
- A nonempty concern reaches verification, preserves structured severity,
  lineage, stage and location fields, and reaches the report request and output.
- Clean reviews skip verification/report and retain their summary.

Existing CLI tests cover project parsing/precedence. The new tests begin at
ProjectId::Sashiko, use the production bundle selector and in-process providers,
and make no external provider calls.

## Validation

Source: 0eedc1d48af6af589a5be042c007cb27661e8120
Base: 9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b

Passed make check-pr RANGE=9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b..HEAD
on Ubuntu 24.04 with repository-pinned Rust/Cargo 1.90.0, after locked dependency
fetching and with offline Cargo execution:

- Formatting and Clippy across all-feature, minimal and cache profiles
- 1085 tests passed, zero failed, two ignored
- Signed-off-by, git diff --check and clean source checkout

Earlier execution passed all 13 focused workflow tests. Four compiled mutations
failed the intended assertions for missing/reversed guidance, dropped findings
and unintended guide injection. The candidate source hash is unchanged.

Required separate Sashiko agent review remains blocked: the additional authorized
attempt's first generation returned HTTP 503. No clean review is claimed and this
prepared description remains unsubmitted while that gate is outstanding.

[Reproducible evidence and limitations](https://github.com/OllieinCanada/sashiko/blob/codex/pr455-guidance-validation-20261021/.github/pr455/STATUS.md)

## References

- #455
- [Kees Cook's feedback concerning --project sashiko](https://github.com/sashiko-dev/sashiko/pull/455#issuecomment-6158258696)
