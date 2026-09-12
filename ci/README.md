# Reproducible checks

Run `bash ci/check.sh` from a checkout with Almide installed, or set
`ALMIDE_BIN` to an absolute compiler path. This runs the existing tests, builds
`gramide`, and checks the built CLI against temporary fixtures. No model API or
credentials are used.

`python3` must be CPython 3.14. The Python package is checked against CPython
itself — its tokenizer, its standard library and its Unicode 16 tables — and
the tokenizer changed in 3.12, so an older interpreter turns these checks into a
token diff that looks like a gramide defect and is not one. `ci/check.sh` says
so before it runs anything.

CI pins Almide to `dff9a458f2e581631bb6537c856a7974036e4153` and Rust to
`1.94.0`. Upgrade these deliberately and rerun the checks together. The compiler
binary cache is keyed by both versions. Smoke fixtures are regression coverage,
not a competitive benchmark or proof of general language correctness.
