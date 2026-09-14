#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compiler="${ALMIDE_BIN:-almide}"

"$compiler" test
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
