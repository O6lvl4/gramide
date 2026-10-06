#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compiler="${ALMIDE_BIN:-almide}"

python3 bench/tree-sitter-duel/verify_frozen.py
# Explicitly include every engine module, independent of file discovery.
"$compiler" test ci/duel_all_tests.almd
# Compile the original helper signatures from a separate dependent package.
(cd ci/compat-client && "$compiler" test src/main.almd)
# Release-mode v2 loading must fail closed; v1 rendering stays byte-exact.
ALMIDE_BIN="$compiler" python3 ci/paired_tables.py
ALMIDE_BIN="$compiler" python3 ci/smoke.py
python3 ci/allocation_profiler.py

# A per-file ratchet, not a target: `parse_rule` is the worst function in any
# gramide repository. Each file is held where it stands, so a clean one cannot
# rot up to the worst one. Numbers only ever fall; --write-baseline records a fall.
#
# Both spellings are tried: `almide install` takes the binary name from the
# package, and Almide package names cannot contain a hyphen.
if command -v codopsy-almd >/dev/null; then cx=codopsy-almd
elif command -v codopsy_almd >/dev/null; then cx=codopsy_almd
else cx=""; fi
if [ -n "$cx" ]; then
  "$cx" --quiet --baseline .codopsy-almd.json src/
else
  echo "codopsy-almd not on PATH: structural check skipped (almide install github.com/O6lvl4/codopsy-almd)"
fi
