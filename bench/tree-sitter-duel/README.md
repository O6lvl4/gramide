# Gramide / Tree-sitter duel

[Recorded results](REPORT.md) include both wins and losses. [Protocol](PROTOCOL.md),
[frozen corpus](CORPUS.md), input/license hashes, exact references, both adapters,
explicit edit streams, correctness gates and every final timing sample are retained.
The 2026-10-05 candidate pins are a reproducible baseline for further improvements.

## Reproduce

Requirements: Linux, Git, Python 3, a C compiler with LTO, Node/npm, JDK 21
(including jdk.compiler), Rust 1.94.0, and Almide 0.62.0. Install Almide from its
official source; set ALMIDE_BIN to the verified executable. Build metadata records
its binary hash; a different compiler build can change performance. Nothing here
installs a compiler, changes credentials, or configures an account.

Run from this directory. Keep compilations sequential and reserve a quiet CPU/RAM
window. Set TMPDIR on disk rather than memory-backed /tmp on constrained hosts.

```sh
python3 verify_frozen.py
python3 setup_sources.py  # fetches only the public official pinned repositories
npm install --ignore-scripts --no-audit --no-fund
java -m jdk.compiler/com.sun.tools.javac.Main oracles/JavaParseOracle.java
bash build_tree_sitter.sh
cc -O2 -std=c11 -D_GNU_SOURCE resource_probe.c -o bin/resource-probe
python3 prepare_candidate.py
export ALMIDE_BIN=/absolute/path/to/almide
export GRAMIDE_BENCH_TMPDIR="$PWD/build-cache"
HARNESS_DIR=gramide-harness-candidate OUTPUT_BIN=../bin/gramide-candidate bash build_gramide.sh
python3 build_manifest.py --candidate --binary bin/gramide-candidate
mkdir -p results
python3 - <<'PY'
import json,subprocess
from pathlib import Path
measurements=[json.loads(subprocess.check_output(['bin/resource-probe','/bin/true'])) for _ in range(5)]
Path('evidence/rss-control.json').write_text(json.dumps({'command':['/bin/true'],'measurements':measurements},indent=2)+'\n')
PY
python3 run_duel.py --gramide "$PWD/bin/gramide-candidate" --gate-only --out results/gates.json
python3 run_edits.py --gramide "$PWD/bin/gramide-candidate" --gate-only --out results/edit-gates.json
python3 json_conformance.py --gramide "$PWD/bin/gramide-candidate" --out results/json-conformance.json
# Select an available isolated CPU (the recorded run used CPU 0).
taskset -c 0 python3 run_duel.py --gramide "$PWD/bin/gramide-candidate" --cold-samples 11 --warm-samples 31 --warm-batches 5 --out results/duel.json
taskset -c 0 python3 run_edits.py --gramide "$PWD/bin/gramide-candidate" --repeats 5 --out results/edits.json
```

The scripts retain failed/unsupported cases rather than aborting the whole report.
Review their gates before interpreting timings. Structural/broken editing is
currently slower, and the broken JSON stream cannot recover one edit shape.
Strict JSON conformance failure does exit nonzero.

For the unmodified baseline, run `bash build_gramide.sh` without HARNESS_DIR or
OUTPUT_BIN overrides, then `python3 build_manifest.py --binary bin/gramide-baseline`.
Its lockfile freezes the original core and grammar dependencies. Both builds use
the same adapter source. `src/main.almd.in` is materialized verbatim by the build
script to keep optional benchmark dependencies out of the repository's unit-test
source discovery. Candidate overlays live only in ignored generated directories.

## Evidence and licenses

Raw final JSON is compressed losslessly as `evidence/*.json.gz` to keep the
repository small. Read it with `gzip -dc`, Python's gzip module, or run
`python3 summarize.py` to regenerate REPORT.md. SHA-256 values for compressed
and original bytes are in `evidence/checksums.json`. No sample was removed.
The original compiler/API source paths remain in build provenance for audit;
portable setup does not require them. Input files are frozen independently.

Fixture licenses/notices are in `corpus/licenses/` and referenced per input in
`corpus/manifest.json`. Official Tree-sitter runtime/grammar licenses are verified
against `references.lock.json` when fetched. New harness code uses Gramide's
existing repository license. The corpus generation script and provenance cache
are retained for audit; use `verify_frozen.py` for offline reproduction without
regenerating or changing the frozen selection.
