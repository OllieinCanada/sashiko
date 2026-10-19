# Bounded Sashiko self-review preparation

Status: blocked, not executed. The readiness check at commit
3e29986fd6b118388dd19125f48e60ac830178f4 found no LLM_API_KEY.
The user has since confirmed that no provider key is available.
No model call or review finding is claimed.

The user authorized the public candidate diff and delegated a conservative
provider/model choice. Google Gemini 3.8 Flash standard pricing was checked
against https://ai.google.dev/gemini-api/docs/pricing on 2026-10-19:
$0.75 per million input tokens and $3.75 per million output tokens, including
thinking, through 2026-12-31.

run.py is prepared for a clean, checked source-only checkout. It is deliberately
not connected to an automatic paid workflow. Before use, required deterministic
checks must pass and the provider secret must be configured on the fork.

Command:

    python3 .github/adaptive-model-review/run.py CHECKED_DIRECTORY BASE HEAD

The runner builds the minimal local-review binary, then invokes:

    sashiko --project sashiko review --settings EXTERNAL_SETTINGS --agent BASE..HEAD

The provider key stays in the proxy process; the review child receives a loopback
placeholder. The proxy only forwards the fixed model's unary generateContent
endpoint. It counts the complete request first, reserves input plus framing slack
and maximum output cost, never refunds uncertain calls, blocks paid/remote tools,
disallows redirects and non-text payloads, and permanently stops after a failure.
Requests are serialized and each network operation has a timeout.

Limits per attempt: $2.25 reserved cost, 10 minutes of review time, 30 provider
generation calls, 150000 counted input tokens and 8192 output/thinking tokens
per call. At most one separately activated follow-up is authorized at the same
limits, so the two attempts total at most $4.50 and 20 minutes. No automatic
retry or job rerun is authorized. Record the first manifest before any follow-up.

An API rejection, timeout, exhausted budget, incomplete patch results, partial
review or accounting mismatch must remain incomplete. Advisory concerns and
findings require human/code review; a successful process exit alone is not
evidence of a clean review.

Offline controls:

    python3 .github/adaptive-model-review/selftest.py

These replace provider transport entirely. They check allowed requests, exhausted
budgets, permanent stop, endpoint/model restrictions, remote/paid tools, multiple
candidates, call limits and input-token limits. They do not validate credentials,
model availability, provider billing behavior or completion of a real review.

Keep this fork-only preparation out of the upstream source patch.

## Free-tier setup option

The user can create a Gemini API key in https://aistudio.google.com/apikey
without enabling billing, then save it as LLM_API_KEY in the fork's Actions
secrets. Do not paste it into chat. Account creation cannot be performed on
the user's behalf here. Recheck model/free-tier availability and limits before
running; stop on provider/rate-limit errors. No paid fallback is enabled.

GitHub Models is not a keyless alternative: it retired on 2026-07-30.
See https://github.blog/changelog/2026-07-01-github-models-is-being-fully-retired-on-july-30-2026/ .
