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
