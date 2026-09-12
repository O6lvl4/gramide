#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
compiler="${ALMIDE_BIN:-almide}"
"$compiler" test
"$compiler" build
python3 ci/smoke.py
python3 ci/symbols.py
python3 ci/packages.py
python3 ci/python_layout.py
python3 ci/python_strings.py
python3 ci/python_numbers.py
python3 scripts/gen_python_identifiers.py --check
python3 ci/python_identifiers.py
python3 ci/python_lexer.py
python3 ci/python_expressions.py
python3 ci/python_statements.py
python3 ci/python_symbols.py
python3 ci/python_recovery.py
python3 ci/python_string_recovery.py
python3 ci/python_interpolation_recovery.py
python3 ci/python_delimiter_recovery.py
python3 ci/python_isolated_errors.py
python3 ci/recovered_symbols.py
python3 ci/recovery_comparison.py
python3 ci/allocation_profiler.py

# A per-file ratchet, not a target: `parse_rule` is the worst function in any of these repositories.
# Each file is held where it stands, so a clean one cannot rot up to the worst
# one. Numbers only ever fall; --write-baseline records a fall.
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
