# Required model review: blocked after bounded timeout investigation

The deterministic source remains unchanged: review head
d7f7a5516cc805444f23c534199af7e65d51e551, tree
9a92a08ab85001d30c037811f4546381e22dbeab. Its 1126 native tests and scoped
validation remain valid. No upstream PR was opened.

## What was investigated

The first final-source attempt used a 60-second proxy timeout despite a
600-second overall budget. The resumed attempt coordinates a 120-second
generation timeout with a 130-second Sashiko client timeout. The existing
$1, 600-second, 24-request and 500000-counted-input-token limits remain.

[Offline controls 39375505623](https://github.com/OllieinCanada/sashiko/actions/runs/39375505623)
passed budget, input, request, redaction, timeout-selection and expired-deadline
negative controls. A read-only model metadata request confirmed
models/gemini-3.8-flash supports generateContent. This probe generated no text.

[Resumed attempt 39375620121](https://github.com/OllieinCanada/sashiko/actions/runs/39375620121/artifacts/12243715494)
used immutable audit checkpoint
1ce85bc6af803b9d0b566e05db3017f1f0c924d4 and the exact review head.
Compilation, offline controls, exact native-tree proof and prerequisites passed.

Token counting succeeded at 1832 input tokens. The first generation timed out
at **120.093 seconds** with no response or usage returned. Its conservative
reservation is **$0.03363**, not actual billing. The agent reported all eight
patches incomplete. Empty findings/concerns are not a clean review.

The proxy stopped on this first failure. Future execution was already disabled
at 2dbbb74929d44c06d8d2775fdfc820d6f5e970ad while the immutable attempt ran.
No automatic or manual workflow retry is enabled. A longer timeout did not
establish a working generation path; the evidence does not identify the
provider-side root cause.

## Offline completion-check correction

The captured native agent output identifies existing range patches as
status=present, method=current-tree. The harness previously accepted only
status=applied, which would incorrectly reject a successful range review.

The corrected guard accepts both legitimate modes, requires exactly one
integer index for every expected patch, and rejects incomplete review status,
review/apply errors, partial results, missing/duplicate patches, nonzero exits,
missing provider calls and stopped proxies. Independently specified positive
and negative fixtures exercise these cases. No extra provider generation is
needed for this harness correction. It does not turn the timed-out review
into a pass.

## Remaining external gates

Required completed Sashiko model self-review is still blocked by the
unresponsive generation request. Provider execution remains disabled rather
than repeatedly spending against the same failure.

Maintainer policy agreement is also absent. The approved issue posting was
rejected with HTTP 403, Resource not accessible by integration; Discussions
are disabled upstream. No cooldown issue was found during this continuation.
The [prepared policy request](ADAPTIVE_MAINTAINER_POLICY_RFC.md) remains ready
for the user's GitHub account to submit through
https://github.com/sashiko-dev/sashiko/issues/new.

No new API key is requested: authenticated metadata and token counting work.
A working provider generation path or a completed maintainer-accepted local
review is needed before the code PR gate can be satisfied. The project
requires Sashiko review; an informal human/assistant review is not silently
substituted for it.

Offline completion guard controls passed on
[run 39375980733](https://github.com/OllieinCanada/sashiko/actions/runs/39375980733),
checkpoint c8cd1423f4d4d5642ee0d7fcb7cf9924ee81e1f7, with no provider calls.
