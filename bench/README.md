# Structured-read comparison

This benchmark measures fresh-process file reading, full parsing, and JSON
function-range output. It does not measure incremental parsing, editor latency,
error recovery, memory, or language breadth. Both implementations are warmed,
then run in deterministic alternating order, three samples per size. Startup is
included. The generated Go inputs contain only top-level function declarations,
so both outputs can be checked for identical names and byte/line ranges before
any timing is accepted. Gramide additionally emits its normal document metadata
and semantic fields; the C baseline emits only the compared range fields.

Clone `tree-sitter/tree-sitter` and `tree-sitter/tree-sitter-go` under
`../almide-references` and record their commits. Build the reference with:

```sh
cc -O2 -I ../almide-references/tree-sitter/lib/include \
  -I ../almide-references/tree-sitter/lib/src \
  bench/tree_sitter_go.c ../almide-references/tree-sitter/lib/src/lib.c \
  ../almide-references/tree-sitter-go/src/parser.c -o /tmp/tree-sitter-go-ranges

python3 bench/symbols.py --gramide ./gramide --before /path/to/previous/gramide \
  --tree-sitter /tmp/tree-sitter-go-ranges \
  --tree-sitter-source ../almide-references/tree-sitter \
  --go-grammar-source ../almide-references/tree-sitter-go \
  --output /tmp/symbols-benchmark.json
```

The committed [measurement](../docs/evidence/symbol-walk-benchmark.json) includes
binary hashes, platform, source hashes, raw timings, and reference commits.
It is a focused regression benchmark, not a general parser ranking.

## Python declaration comparison

The Python baseline emits functions, classes and type aliases with lexical names,
method owners and decorator-inclusive byte/line ranges. Both outputs must match
CPython's AST before that input is timed. Optional final suite semicolons are the
only range normalization. Failed parses and mismatches remain in the report and
receive no competitive timing. The C adapter excludes trailing comment extras
from declaration ends; it does not repair the grammar or recovered trees.

Build from the pinned references recorded in the evidence (the Python scanner
is required as well as its generated parser):

```sh
cc -O2 -Wall -Wextra \
  -I ../almide-references/tree-sitter/lib/include \
  -I ../almide-references/tree-sitter/lib/src \
  -I ../almide-references/tree-sitter-python/src \
  bench/tree_sitter_python.c ../almide-references/tree-sitter/lib/src/lib.c \
  ../almide-references/tree-sitter-python/src/parser.c \
  ../almide-references/tree-sitter-python/src/scanner.c \
  -o /tmp/tree-sitter-python-ranges
python3 bench/python_symbols.py --gramide ./gramide \
  --tree-sitter /tmp/tree-sitter-python-ranges \
  --references ../almide-references \
  --output /tmp/python-symbols-benchmark.json
```

Use Python 3.14 for the corpus and AST oracle. The report records its exact
version, corpus hashes, binary hashes and reference commits. Five shuffled time
samples include process startup and file reading; two separate `/usr/bin/time`
runs record peak RSS in bytes (macOS `-l`, Linux `-v`). Memory instrumentation is
excluded from the time samples. macOS may require permission for the timer's
sysctl calls. Peak RSS includes runtime/process overhead, not just parser memory.
The normal gramide JSON also contains metadata and syntax kinds; the C output
contains only compared fields. Neither implementation reuses an old tree.

[Initial evidence](../docs/evidence/python-symbols-benchmark.json) covers three
generated function files and 12 complete standard-library files. All 15 inputs
match CPython's declaration contract. Gramide loses on both time and memory for
all of these inputs: 800 functions take about 77 ms versus 7.5 ms and peak RSS is
about 18.2 MB versus 3.7 MB. Inspect.py takes about 122 ms versus 10.5 ms and
21.7 MB versus 4.8 MB. These are measured gaps to address, not a general claim
about all Python syntax. Recovery, edit sequences, incremental parsing and
broader corpora require separate evaluation.

## Borrowing symbol subtrees

The native output walk previously cloned each child subtree twice when deciding
whether to include a declaration envelope (for example Rust attributes). It now
passes only the effective start-token index separately and borrows the original
child. Leaves cannot have the required declaration-name child, so the walk skips
them. Names, owners, envelopes and end positions retain the same contract.

Pass `--before /path/to/previous/gramide` to include the old binary in the same
shuffled sample sequence. The [paired evidence](../docs/evidence/python-symbols-subtree-borrow.json)
compares the final change with the pre-change binary and tree-sitter on the same
15 sources, after the full test suite finished. All three outputs match CPython.

| Input | Before | After | tree-sitter |
| --- | ---: | ---: | ---: |
| 800 functions | 82.23 ms | 65.90 ms | 7.61 ms |
| inspect.py | 129.81 ms | 95.26 ms | 10.55 ms |
| typing.py | 128.18 ms | 94.85 ms | 10.63 ms |

Every case improved in this local run (1.12–1.36×), but tree-sitter remains faster
and uses less peak RSS throughout. Memory gains are modest: generated-file RSS
is effectively unchanged; typing.py drops from about 20.7 MB to 20.3 MB. The
report retains both RSS samples, including observed variation, and all raw time
samples. This is a full-file structured-read improvement, not an incremental
parsing result or a claim that grammar parsing itself is faster.

## Looking up declaration fields without copying siblings

The pinned compiler lowers `list.find` on a node's children by cloning the
whole child list and candidate nodes. Looking up `name`, `trait` or `receiver`
therefore also copied function bodies that were never selected. The lookup now
scans borrowed fields, records the first matching index and retrieves only that
node. Declaration-kind lookup also avoids creating a copied list for `find`.
The first-match and missing-field contracts are unchanged. This shared helper
also serves outline and tags; the measurements here still cover symbols only.

[Paired measurements](../docs/evidence/python-symbols-field-lookup.json) compare
against the preceding subtree-borrow change, with the same 15 inputs and oracle.
All outputs match CPython; 24 complete Python symbol/outline JSON/text outputs
are additionally byte-identical to the previous binary. The full suite and real
hew integration passed.

| Input | Before | After | tree-sitter |
| --- | ---: | ---: | ---: |
| inspect.py | 98.87 ms | 79.80 ms | 11.54 ms |
| typing.py | 97.00 ms | 80.46 ms | 11.44 ms |
| reprlib.py | 15.32 ms | 11.74 ms | 3.86 ms |

14 of 15 measured medians improved. Keyword.py increased from 4.13 to 4.32 ms;
small-file startup samples and RSS vary, and memory does not improve uniformly.
All raw samples are retained. Tree-sitter remains ahead; this is a reduction in
structured-read overhead, not a general grammar or incremental-parser victory.
