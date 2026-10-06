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

The gate runs `almide test ci/duel_all_tests.almd`, an explicit aggregate
root importing the CLI, tables and package contract tests. Their transitive
imports cover every engine source module containing tests, including incremental
span/identity tests. This replaces recursive default discovery without removing any engine tests.

`ci/compat-client` is a separate package depending on this checkout by relative
path. Its explicit test root calls the original incremental helper signatures
with immutable inputs and checks their output and input-preservation contracts:

```sh
(cd ci/compat-client && almide test src/main.almd)
```

Neither root needs a language repository, network dependency or credentials.
The frozen benchmark verification, CLI smoke and allocation calibration remain
part of `ci/check.sh`.

`ci/paired_tables.py` builds one small probe with `--release`. It checks a valid
annotated v2 load and round trip, then uses separate processes to reject malformed
triples, an unknown opcode, and an invalid start index. Every refusal must exit
nonzero, print its exact diagnostic (allowing only source line numbers to move),
and produce no stdout. This catches validation accidentally disabled in release.

The same probe renders two ordinary v1 grammars and compares every output byte
with `ci/paired_tables_v1.almd.golden`. That golden was captured from the previous
core before the paired-head change. Review any compiler/table-format change
before deliberately updating it; this test never regenerates the golden.
Run this gate alone with `ALMIDE_BIN=/absolute/path/to/almide python3 ci/paired_tables.py`.
