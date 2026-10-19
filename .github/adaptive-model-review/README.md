# Bounded Sashiko self-review

The repository secret is configured and provider authentication works.
The required review is **incomplete**, not clean.

| Attempt | Source-only candidate | Model | Outcome | Reserved upper cost |
| --- | --- | --- | --- | ---: |
| [Initial](https://github.com/OllieinCanada/sashiko/actions/runs/39336060768) | 6667a81cd25a69feca76e65d94aacb4c83b2ce72 | gemini-3.8-flash | One returned response; next generation failed; safe proxy halted. Original failure HTTP status was not recorded. | $0.06647850 |
| [Single follow-up](https://github.com/OllieinCanada/sashiko/actions/runs/39336513028) | same candidate | gemini-3.6-flash | generateContent returned HTTP 503; proxy halted. | $0.03363225 |

Combined reservation: **$0.10011075** for these two review attempts.
This is not a billing measurement. One returned response reports 1835 input,
49 candidate and 640 thinking tokens; the two failed generation requests have
no returned usage. Earlier smoke requests are separate historical attempts.

Both runs use the exact three-commit checked bundle on base
f6e2e172e1e669b6767a4c74fe91d062b41fd71c. Empty findings from a partial/error
result are not evidence of a clean review. No complete patch review is claimed.

Both authorized review attempts are used. The workflow is manual-only with
its job disabled; there are no automatic retries or further provider calls.
Reactivation requires a new review decision.

The user authorized the public candidate diff and delegated conservative
provider/model choice. [Official pricing](https://ai.google.dev/gemini-api/docs/pricing)
was rechecked 2026-10-19: both allowlisted Flash models have standard rates of
$0.75/million input and $3.75/million output including thinking through
2026-12-31. The proxy refuses calls after that date without revised pricing.

Per attempt: maximum $2.25 reservation, 10 minutes, 30 generation calls,
150000 counted input tokens and 8192 output/thinking tokens per call.
Requests are serialized. The complete request is counted first, including
system instructions and tool schemas; framing slack and full output are
reserved before dispatch, without refunds for uncertain failures.

The real credential remains in the loopback proxy process; the Sashiko child
receives a placeholder. The proxy only accepts the fixed allowlisted model's
generateContent endpoint. It rejects paid/remote tools, remote data, multiple
candidates, redirects and requests outside the caps. Safe failure diagnostics
record action and HTTP status/type, not provider bodies, URLs or credentials.

Offline tests exercise budget exhaustion, permanent stop, endpoint/model/tool
restrictions, token/call limits and reflected secret/private canaries. These
tests do not satisfy model-assisted self-review.

Command, for a separately authorized attempt:

    python3 .github/adaptive-model-review/run.py CHECKED_DIRECTORY BASE HEAD

The runner invokes the actual source-built Sashiko agent command. The first
and follow-up artifacts preserve manifests, agent output and sanitized logs;
raw artifacts expire after 14 days. Current completion evidence preserves their
outcomes and returned usage without committing raw logs or credentials.
