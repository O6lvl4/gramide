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
