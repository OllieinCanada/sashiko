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

The corrected pinned run 39673050262 passed the full make check-pr suite:
formatting, all three strict Clippy profiles, 1085 tests passed, zero failed,
two ignored, Signed-off-by and clean/diff checks. No server changes or waiver
were needed. Exact source stayed at 0eedc1d48af6af589a5be042c007cb27661e8120.

The first pinned run 39671889391 exposed a harness target-directory mismatch
in three existing CLI tests; all lint profiles and both new tests passed.
The corrected run supplied the existing CARGO_BIN_EXE_sashiko override for the
shared target path, without changing repository source. Its full results:
https://github.com/OllieinCanada/sashiko/actions/runs/39673050262

The additional bounded self-review ran only after the required checks passed.
Its first generation returned HTTP 503 after 0.584 seconds and stopped the
proxy. Required review remains incomplete. No further calls are scheduled.
Future execution is disabled at 3f4156d62978380c1088a5476be251a118c4ba22.
