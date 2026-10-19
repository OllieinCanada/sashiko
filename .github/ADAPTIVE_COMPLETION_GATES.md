# Adaptive cooldown completion gates

**Not ready for an upstream code PR.** The required completed Sashiko model
review and maintainer policy decisions are still absent. No upstream PR was
opened and no deployment or real email was sent.

## Requested work and outcomes

| Requested work | Outcome |
| --- | --- |
| Complete Sashiko self-review | Two real source-built agent attempts were incomplete. The follow-up returned HTTP 503. Both bounded attempts are used; automatic and manual provider execution are disabled. |
| Resolve or explicitly justify partial scenarios | All10 were assessed individually. Strict cancellation and stopped-daemon rollback gaps are closed within their scopes. Eight policy/resource/privacy scenarios remain partial;[technical justifications and required decisions](ADAPTIVE_REMAINING_GATES.md) do not waive them. |
| Historical replay | Real2005 Gmane message preserved in Git's pinned corpus replayed in3 native processes. One frozen admission, read-only write rejection, source DB hash and tracked tree unchanged. This is a maintained fixture copy, not a modern full archive dataset. |
| Maintainer agreement | Complete RFC prepared; upstream issue creation returned403 Resource not accessible by integration. No issue or agreement exists. [Proposal ready to post](ADAPTIVE_MAINTAINER_POLICY_RFC.md). |
| Inspect bundle and verify final candidate | Independent refreshed-bundle inspection passed. Full strict native run passes1,111 tests/2 ignored, fmt and 3 Clippy profiles. Exact final production-tree metadata check is scheduled with this evidence commit. |

Acceptance matrix: ** 55 VERIFIED / 8 PARTIAL / 1 BLOCKED**. Each verified row
has a recorded scope. The single blocked row is model self-review; maintainer
agreement remains a separate open completion gate.

## Reproducible evidence

| Check | Exact checkpoint or source | Result and artifact |
| --- | --- | --- |
| Refreshed bundle inspection | ede0490fa12efd78fbe9f16f44f6e004858dea9e | [PASS; 12 mutation negatives inspected](https://github.com/OllieinCanada/sashiko/actions/runs/39335945493/artifacts/12226558113) |
| Strict cancellation and complete native suite | ab5c5685d04e7e3134cd28f767a9a94a1dad99df | [PASS; 8 focused fixtures, 2 guard mutants plus1111 restored-source tests](https://github.com/OllieinCanada/sashiko/actions/runs/39336545890/artifacts/12227336043) |
| Real historical message replay | 8d86c4937f17864e6cfb162ca992971b8cc379fb | [PASS; three restarted replays and protected-state checks](https://github.com/OllieinCanada/sashiko/actions/runs/39336256859/artifacts/12226673831) |
| Actual stopped-daemon rollback | 80f53560be72fd206514d63130d5061b9434ed6f | [PASS; candidate/old/candidate daemon health, startup, stop, untouched restore and pending selection](https://github.com/OllieinCanada/sashiko/actions/runs/39338177473/artifacts/12227831905) |
| First real model attempt | Bundle 6667a81cd25a69feca76e65d94aacb4c83b2ce72 | [INCOMPLETE; first returned response then proxy failure](https://github.com/OllieinCanada/sashiko/actions/runs/39336060768/artifacts/12225604864) |
| Single model follow-up | Same bundle | [INCOMPLETE; generateContent HTTP 503](https://github.com/OllieinCanada/sashiko/actions/runs/39336513028/artifacts/12227036289) |

Production runtime remains **bd59059f1864aea81b11b5de0eb97e5d2ec53667**.
The checked source-only bundle HEAD is
**6667a81cd25a69feca76e65d94aacb4c83b2ce72**, tree
**d38b668f511e2e0972aa4588174a2c55f3582b30**, on upstream
**f6e2e172e1e669b6767a4c74fe91d062b41fd71c**. These are bundled commits,
not a published remote source branch. The refreshed bundle contains three
properly signed-off native commits and passed make check-pr before each.

Hosted Ubuntu 24.04; Rust 1.99.1; two Cargo build jobs. No production source changed
in this completion round. Current upstream was rechecked unchanged at
2026-10-19 22: 58: 52 UTC. [PR 685](https://github.com/sashiko-dev/sashiko/pull/685)
is still open and introduces migration 014; the candidate uses014/015, so it
needs renumbering and revalidation if that branch lands first.

## Exact historical and rollback scope

The historical mail is Message-ID u5tacjjdpxq.fsf@lysator.liu.se,
dated 2005-08-15, from the Gmane archive copy in Git's t/t5100/sample.mbox.
Its identity and decoded patch are checked against immutable corpus blob
4a54ee517198cf218d330bdc4cd93cd279abcf0e, with provenance in Git commit
b0921331030d52febf52839753eee1b2b9ca1f24. Git has adjusted fixture encoding
syntax over time; this is not an untouched direct archive download.
Raw selected-message SHA256:
a191fcedd79cb128e8e01287ce811e47cd1220e37fea775b62cee67f3ae3570c.
The protected database is a seeded isolated source snapshot, not supplied
production state. No review/publication worker runs in the replay.

Rollback uses real daemon binaries on loopback, waits for health and reviewer
startup, and stops each process group. Review concurrency0 pauses computation;
SMTP is dry-run, NNTP/forge are disabled and runtime egress is refused. An
unsafe native old-code claim runs only on a separate copy. Quiesced old access
accepts no new work. Restoring the untouched backup preserves every recorded
pending-state row before and after candidate restart, and native pending-work
selection resumes. This does not demonstrate a live rolling downgrade or
remote delivery acknowledgement.

## Model review and spending evidence

The key works: the first model returned one response with usage 1835 input,
49 candidate and 640 thinking tokens. The next generation failed; the first
runner did not retain its upstream HTTP status. The independent diagnosis
preserves that uncertainty. The follow-up records generateContent HTTP 503.

Combined conservative reservation for these two attempts: **$0.10011075**.
This is not actual billing. Two generation requests have no returned usage;
earlier smoke probes are separate historical requests. Empty findings in a
partial/error result are not a clean review. The workflow remains disabled;
no automatic retries or extra calls are running. See the
[bounded review record](adaptive-model-review/README.md).

## Preserved negative results

- [Initial historical fixture](https://github.com/OllieinCanada/sashiko/actions/runs/39336225271):
  generated byte/regex escapes invalidated the corpus check. This was a harness
  defect, not evidence of network unavailability. Corrected before the PASS run.
- [First daemon rehearsal](https://github.com/OllieinCanada/sashiko/actions/runs/39336822289):
  mail-link base URL used loopback; the daemon correctly rejected it. The
  listener remains loopback while generated links use a reserved example host.
- [Second daemon rehearsal](https://github.com/OllieinCanada/sashiko/actions/runs/39337623161):
  the zero-part incomplete fixture was correctly failed by interrupted-fetch
  startup recovery. The final fixture contains one actual part of two and
  checks exact pending-state equality before taking a backup.
- Earlier clock-retention, release-state, WAL-cursor, performance and packaging
  negatives remain in [prior deterministic evidence](ADAPTIVE_DETERMINISTIC_EVIDENCE.md)
  and the historical analytical JSON. None is relabelled a passing run.

The current [machine-readable report](adaptive-completion-gates.json) preserves
commands, identities, manifests, scopes and outcomes. Raw artifacts expire after 14 days;
raw logs and credentials are not committed. Requirements came from the user's
pasted 64-row checklist; the inaccessible original attachment was not reread.
