#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
: "${ALMIDE_BIN:=almide}"
if [[ -n ${GRAMIDE_BENCH_HOME:-} ]]; then export HOME="$GRAMIDE_BENCH_HOME"; fi
export TMPDIR="${GRAMIDE_BENCH_TMPDIR:-$PWD/build-cache}"
export CARGO_BUILD_JOBS=1
mkdir -p bin evidence "$TMPDIR"
cd "${HARNESS_DIR:-gramide-harness}"
if [[ ! -f src/main.almd && -f src/main.almd.in ]]; then cp src/main.almd.in src/main.almd; fi
"$ALMIDE_BIN" check --deny-warnings src/main.almd
"$ALMIDE_BIN" build src/main.almd --release -o "${OUTPUT_BIN:-../bin/gramide-baseline}"
