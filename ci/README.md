# Reproducible checks

Run `bash ci/check.sh` from a checkout with Almide installed, or set
`ALMIDE_BIN` to an absolute compiler path. This runs the engine's tests, builds
a binary from the contract test's demo language (`ci/demo_cli.almd`) and drives
it through every command, and calibrates the allocation profiler the board's
measurements used. No model API or credentials are used; no language package is
needed.

CI pins Almide to `dff9a458f2e581631bb6537c856a7974036e4153` and Rust to
`1.94.0`. Upgrade these deliberately and rerun the checks together. The compiler
binary cache is keyed by both versions.
