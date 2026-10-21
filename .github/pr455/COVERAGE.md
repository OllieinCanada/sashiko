# PR455 replacement coverage audit

Base: 9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b (current main at task start, 2026-10-21).
PR455 is closed and unmerged; PR447 and PR467 are open and are not dependencies.

Kees Cook's feedback:
https://github.com/sashiko-dev/sashiko/pull/455#issuecomment-6158258696
The author's proposed narrower replacement:
https://github.com/sashiko-dev/sashiko/pull/455#issuecomment-6321581109

## Existing functionality and coverage

| Objective | Existing proof | Narrow gap addressed |
| --- | --- | --- |
| A: selection | src/main.rs CLI parser/effective_project tests; src/project.rs default/name/prompt_dir tests; src/prompt_bundle.rs bundle and guide-index integrity tests | Use the actual project_prompts_path(Sashiko) result to run a first-party workflow against a recording provider; preserve complete bundled guide contents and selected-guide order |
| B: requests | Generic PromptTemplate rendering tests; workflow temperature forwarding records parameters | Observe actual AiRequest.system and messages at AiProvider::generate_content; check exact complete content once, selected order, no cross-field duplicate and absence of an unselected stage-owned guide |
| C: finding lifecycle | Sashiko verification-only preexisting routing, reducer, schema and report validators | Raise a nonempty concern in analysis, verify it, inspect the structured finding in the report provider request, and assert final fields and plain-text report/summary |
| D: no unintended injection | Generic optional-file rendering and project-default tests | Execute complete Sashiko workflows with no selected guides and with a missing optional guide; neither eligible guide enters analysis; clean review skips verification/report and retains summary |

The new tests start at the resolved ProjectId rather than adding a CLI
subprocess harness. Existing CLI tests cover --project sashiko parsing and
precedence; the new workflow fixture calls the same installed-bundle selector
used by production. No separate project-context mechanism is introduced.

Stage-exclusive guides are filtered by the real pre-screen reducer. The
fixture deliberately offers rust-async.md alongside the eligible
resource-limits.md and git-ops.md guides, then checks only the eligible guides
are selected and propagated. It does not change this existing policy.

Provider payload here means the actual generic AiRequest crossing the
AiProvider boundary, including system and user messages; it is not a direct
template render or a configuration-only assertion. Provider-specific HTTP
serialization is outside this test's scope.

The guide oracle reads complete first-party files via include_str!, so no
copies of the guidance are maintained. Assertions do not snapshot dates,
global system-prompt wording, or concurrent stage execution order.

## Change and regression checks

Candidate contribution: only additions inside the existing cfg(test) module in
src/workflows/sashiko_patch_review.rs. No production code, prompts, dependency,
workflow architecture or unrelated branch changes.

The validator compiles four mutations and requires actual test assertion
failure: missing selected guides, reversed selected-guide order, finding
discarded before report, and unselected guidance injected into the system
prompt. A compile error is not treated as a killed mutation.

## Validation history

- Superseded first fixture: run 39656044400 was cancelled after discovering
  stage-exclusive selection rules. No pass is claimed for it.
- Run 39656216662: formatting passed, 12 focused tests passed, one new positive
  test failed because it incorrectly required core guidance to precede selected
  guides. The generic renderer actually inserts dynamic guides at @includes and
  appends the static core include. The corrected test protects selected-guide
  ordering without fixing the core's absolute position.
- Final commands/results and native source hash will be in the validation
  manifest artifact. No external model API, provider credential, or Linux
  quality benchmark is used by these regression tests.

Required separate model-assisted local review is governed by AGENTS.md and
CONTRIBUTING.md. An offline test pass is not a substitute for that review.
