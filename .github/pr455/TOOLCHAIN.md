# Repository toolchain investigation

Earlier supplemental validation explicitly exported RUSTUP_TOOLCHAIN=stable
and used rustc 1.99.1. That bypassed this repository's rust-toolchain.toml,
which pins 1.90.0 with rustfmt and Clippy.

The upstream CI action installs stable and changes the default toolchain.
It does not export RUSTUP_TOOLCHAIN or set a directory override. The
checkout-local file therefore still selects 1.90.0 in upstream CI.

The four result_large_err diagnostics occur on async functions in
src/server.rs. Rust 1.99.1 Clippy inspects the async Future output before
checking Result; the 1.90.0 implementation does not perform that peeling.
This explains the extra diagnostics. Those newer-toolchain failures remain
recorded as failures, but they do not justify unrelated server edits or lint
suppression in a deterministic test-only contribution.

## Reproduction and evidence

- Source: 0eedc1d48af6af589a5be042c007cb27661e8120
- Base: 9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b
- [Pinned toolchain](https://github.com/sashiko-dev/sashiko/blob/9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b/rust-toolchain.toml)
- [Stable action inspected](https://github.com/dtolnay/rust-toolchain/blob/b725eda525362e7cf34af9a7243cac1e3f01a7ec/action.yml)
- [Rustup precedence](https://github.com/rust-lang/rustup/blob/main/doc/user-guide/src/overrides.md)
- [Clippy 1.90 implementation](https://github.com/rust-lang/rust/blob/1.90.0/src/tools/clippy/clippy_lints/src/functions/result.rs)
- [Clippy 1.99.1 implementation](https://github.com/rust-lang/rust/blob/1.99.1/src/tools/clippy/clippy_lints/src/functions/result.rs)
- [Pinned validation and one additional authorized review](https://github.com/OllieinCanada/sashiko/actions/runs/39671889391)

The pinned run exports RUSTUP_TOOLCHAIN=1.90.0, fetches locked dependencies,
then runs make check-pr RANGE=9d2bf58b17817b2cb4719fd4e1a14ca755b0dd6b..HEAD
with CARGO_NET_OFFLINE=true in a clean clone of the exact published commit.
It checks the full source hash, production prefix, tree and current upstream.

At the time this investigation note was written the pinned checks were still
running. No passing result or completed model review is claimed here.
The separate review runs only after the required checks pass. It reuses the
previously tested dollar, time, request and completion controls, with a fresh
maximum of one dollar and ten minutes. No automatic follow-up is authorized.
Future execution was disabled at 6322c18e712034a4bcc47e2e65881804d7542166.
