# Deterministic wall-clock coverage

Status: **PASS**, 2026-10-19. This is a completed sub-result; the broader deterministic routing/cancellation/privacy batch is recorded separately.

Production runtime source remains `bd59059f1864aea81b11b5de0eb97e5d2ec53667`. Tested audit checkpoint: `ce22d185f20acb98284eaf026849a589c6b3962b`. Upstream's later `f6e2e172e1e669b6767a4c74fe91d062b41fd71c` changes only PRESS.md and was incorporated in merge `f6d1a756f3bded22a8b93fe79a90cf399c977cb6`; it changes no runtime code.

- [Run 39328125251](https://github.com/OllieinCanada/sashiko/actions/runs/39328125251), job 118319127092: PASS.
- [Reproducible artifact](https://github.com/OllieinCanada/sashiko/actions/runs/39328125251/artifacts/12222538821), 14-day retention.
- [Machine-readable result](adaptive-clock-evidence.json) records source, fixture, shim and native test-binary hashes.
- Commands and fixtures: `.github/adaptive-clock/run.py`, `fixture.rs`, `realtime.c`, and `.github/workflows/adaptive-clock.yml` at the tested checkpoint. Run only in an isolated throwaway checkout.
- Environment: GitHub-hosted Ubuntu 24.04; stable Rust 1.99.1; two Cargo build jobs; UTC and America/New_York; no provider credentials supplied.

## What actually executed

Each timezone used a separate native test process with a calibrated LD_PRELOAD wall-clock shim. The test exercises parsed NNTP ingestion, two unique admissions, a completed review fixture with a finding, the real Reviewer release loop, and local recording sendmail.

| State | Unix time | Independently expected behavior |
| --- | ---: | --- |
| Admission | 2000000000 | Second admission earns a frozen 3600-second delay |
| Deadline minus one | 2000003599 | Real selector executes; no eligible review or queued email |
| Backward before admission | 1999999000 | Real selector executes; no early publication |
| Deadline | 2000003600 | Real selector selects exactly one review; one notification is queued and recorded |
| Large forward jump after delivery | 2500000000 | Replay retains the decision and does not duplicate notification |
| Backward jump after delivery | 1999999000 | Replay cannot reinstate the hold or duplicate notification |

The test asserts both chrono and SystemTime observe every controlled timestamp. Calibration independently confirms wall time is controlled while monotonic time still advances. An ephemeral observer records the actual production eligibility query's timestamp and selected count; the test waits for that record before checking early-release behavior. This avoids a false pass caused by worker startup delays.

The final frozen admission/count/extra/deadline tuple stays unchanged across both post-release replays. The patchset remains released, one outbox item exists, and the recording transport sees the expected finding and recipient. Exact test selection and the final case marker are required. Clippy with all features and all targets passes. Both instrumented source files are restored, as the manifest records.

## Scope

The host clock is never changed. Only the owned native test process and its local recording MTA see the shim; monotonic process timeouts remain real. Review output is a fixture; no model request, SMTP server or real external delivery is involved. This does not prove arbitrary kernel/NTP behavior, performance under instrumentation, or exactly-once remote SMTP acceptance. Combined with existing backward-admission, overflow, window-boundary, untrusted-date and timezone checks, it closes the previously missing forward/backward production scheduling coverage for C06.
