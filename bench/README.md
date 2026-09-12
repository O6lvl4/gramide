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

## Exact capacity for parser node drains

Wrapping rules, field labels and left folds already know how many nodes they
must move. Their temporary vectors now reserve that exact count, including the
forward vector retained as a node's children. The move-only pop/push algorithm
and ordering remain unchanged. This avoids growth reallocations and spare
capacity in the resulting tree; it does not introduce a copy-based reversal.

The [Python paired run](../docs/evidence/python-tree-capacity.json) preserves
all 15 CPython comparisons. Typing.py changes from 78.25 to 73.00 ms and from
19.94 MB peak RSS to 15.27 MB. Inspect.py changes from 79.19 to 73.11 ms and from
20.23 MB to 15.43/17.27 MB in the two RSS samples. Small-input timing and RSS
still vary; keyword.py's median increased by about 0.02 ms. Tree-sitter remains
faster and smaller throughout this corpus.

A separate [Go comparison](../docs/evidence/go-tree-capacity.json) retains
identical ranges at 100, 400 and 800 generated functions. Its timings are
roughly unchanged (800 functions: 21.03 to 21.08 ms); this is not a claimed Go
speed win. All raw samples and binary/source hashes are retained.

## Python recovery comparison

`python_recovery.py` compares declaration extraction from 20 known-edit inputs.
Expected names, owners, inclusive line ranges and exclusive UTF-8 byte ranges
are specified from intact source fragments, independently of either parser.
This is a small corpus biased toward gramide's existing recovery tests, not a
representative accuracy ranking. Invalid Python has no CPython AST oracle; the
expected recovery policy is a product choice, not a Python language requirement.

Build the tree-sitter adapter from the pinned checkouts recorded in the evidence:

```sh
refs=/path/to/almide-references
cc -O2 -Wall -Wextra \
  -I "$refs/tree-sitter/lib/include" -I "$refs/tree-sitter/lib/src" \
  -I "$refs/tree-sitter-python/src" \
  bench/tree_sitter_python.c "$refs/tree-sitter/lib/src/lib.c" \
  "$refs/tree-sitter-python/src/parser.c" \
  "$refs/tree-sitter-python/src/scanner.c" -o /tmp/tree-sitter-python
python3 bench/python_recovery.py --gramide ./gramide \
  --tree-sitter /tmp/tree-sitter-python --references "$refs" \
  --output /tmp/python-recovery.json
```

The adapter's default mode still rejects error trees. Its explicit `--recover`
mode skips ERROR subtrees and missing nodes. It omits declarations containing
errors, but traverses bodies under intact headers to preserve nested lexical
names. Broken headers and decorators cannot establish owners. These rules are
implemented by our adapter, not a tree-sitter symbol API. A stronger consumer
could use additional source analysis, changing the results. Gramide uses its
production `symbols-recovered` interface. Both parse the full input from scratch;
this experiment measures neither latency, memory nor incremental editing.

The [initial evidence](../docs/evidence/python-recovery-comparison.json) records
all inputs, expected and actual rows, failures, binary/source hashes and reference
commits. Gramide matches 17/20 cases and cannot return a document for 3;
tree-sitter with this adapter matches 16/20, returns documents for all 20,
and has one missing declaration, two spurious declarations and one incorrect
range. Missing/spurious/range counts cover **returned documents only**; an
unavailable result is a failed case, never an empty successful document.

Gramide's gaps are an unmatched bracket at EOF and unterminated f/t strings.
Tree-sitter retains the expected declarations in both f/t string cases, so these
are concrete losses to address. This adapter loses a nested helper, drops a
decorator from a range, and exports declaration-looking text from an unclosed
triple string or bracket. The latter expectations intentionally favor
conservative lexical containment; another editor may prefer speculative symbols.

Use `python_symbols.py` for the separate CPython-backed valid-input comparison
and time/RSS measurement. Neither experiment establishes overall superiority.

The runner also checks both tree-sitter modes against CPython declaration ranges
for 12 complete stdlib files (634 declarations in Python 3.14.4). Run it with
Python 3.14; it uses the existing AST oracle and records source hashes.

After atomic interpolation rollback, the same unchanged 20-case corpus gives
[19 exact gramide cases and one unavailable result](../docs/evidence/python-interpolation-recovery.json).
The f/t-string losses are resolved; the unmatched outer bracket remains
unsupported. The tree-sitter adapter results are unchanged. The broader 239-case
recovery gate also covers conservative tail omission for damaged replacements
and nested strings; this is still not general recovery or incremental parity.

After EOF delimiter recovery, the same unchanged corpus gives
[20 exact gramide cases, with no unavailable results](../docs/evidence/python-delimiter-recovery.json).
The adapter remains at 16 exact cases. This only closes the gaps in these 20
hand-selected inputs, not general recovery accuracy: mismatched closers, other
lexical failures and ambiguous damaged replacement fields remain gaps, while
incremental parsing and the measured speed/RSS deficit are unchanged.

## Generated stdlib edit corpus

`python_edit_corpus.py` expands recovery comparison beyond the original 20
fixtures. It inserts five kinds of invalid line at module start and up to four
evenly sampled function/class body starts in each of the same 12 stdlib files.
Anchors are chosen before invoking either parser, including nested/decorated
bodies; inline suites are excluded. Python 3.14.4 gives 55 anchors and 275 edits.

The oracle starts from the unedited CPython AST, omits declarations containing
the insertion, and shifts every other declaration's name/owner/range unchanged.
Both unedited parsers must match that AST. A `pass` insertion control verifies
the range transformation against a new CPython AST, and every actual damaged
input must be rejected by `ast.parse`. These controls do not make the desired
invalid-input recovery policy a Python language requirement. In particular,
keeping lexical owners and treating the inserted line as isolated damage are
consumer choices. The tree-sitter adapter may group errors differently.

```sh
python3 bench/python_edit_corpus.py --gramide ./gramide \
  --tree-sitter /tmp/tree-sitter-python --references /path/to/almide-references \
  --output /tmp/python-edit-corpus.json
```

Evidence records source and binary hashes, insertion offsets/text, all
missing/spurious/incorrect rows, unavailable results and per-edit totals.
Original files are identified by stdlib filename and hash; use the recorded
Python version to reproduce. Every edit is a fresh full-file parse, without
incremental reuse, timing or memory measurements. Missing/spurious counts apply
only to returned documents; unavailability is a failed case.

Before isolated-error recovery, gramide matched 165/275 and could not return 110
documents, while the tree-sitter adapter matched 217/275 and returned all 275.
After recovering unknown ASCII characters and unmatched closing delimiters with
an empty bracket stack, gramide matches 275/275. Tree-sitter adapter results
remain unchanged (227 missing and 49 spurious declarations under this policy).
See [before](../docs/evidence/python-edit-corpus-before.json) and
[after](../docs/evidence/python-edit-corpus.json).

This measures five invalid-line insertion families, not arbitrary character
edits, representative editor traffic or all Python. The existing stdlib corpus
also favors syntax already covered by gramide. Overall accuracy, performance,
incremental editing and language breadth remain separate unfinished goals.

## Python operator lookup without candidate copies

With pinned Almide `dff9a458f2e581631bb6537c856a7974036e4153`, the Python
lexer lowered `list.find(ops, ...)` to `(ops.clone()).into_iter().find(...)`,
cloned each candidate inside the predicate, and captured the mutable cursor.
The lexer now scans the unchanged longest-first table in place and retains only
the matching byte width. Generated Rust uses `for op in ops.iter()` and a plain
integer cursor. A helper taking the list by value still cloned the whole table
at its call site, so that intermediate approach was not retained.

The [paired evidence](../docs/evidence/python-operator-lookup.json) compares the
merged isolated-error recovery binary with this change. All three binaries
match CPython declaration names, owners and ranges on all 15 inputs before
measurement. Five shuffled wall-time samples include startup/read/full parse/
JSON output; two separate RSS samples per binary retain the original method.

| Input | Before ms | After ms | tree-sitter ms |
| --- | ---: | ---: | ---: |
| 800 generated functions | 52.16 | 45.31 | 8.24 |
| inspect.py | 73.73 | 64.62 | 11.41 |
| typing.py | 72.46 | 64.11 | 11.27 |
| dataclasses.py | 37.09 | 33.20 | 8.13 |

All 15 median times decrease by 3.6–13.1% in this run. Peak RSS does **not** show
consistent improvement: most samples are identical, while the after binary has
higher individual samples for textwrap (4.36 vs 3.94 MiB), inspect (16.42 vs
14.77 MiB) and dataclasses (10.08 vs 8.03 MiB). Both original samples are retained;
this change makes no memory-reduction claim. Tree-sitter remains faster and uses
less peak memory on every input, and no incremental reuse is measured. The
full token/grammar/recovery gates and real hew integration also pass.

## Allocation-guided outline work (#37)

`instrument_allocations.py` instruments the pinned compiler's generated Rust
function headers with a diagnostic Rust global allocator. Each alloc/alloc_zeroed
and realloc request is charged to the innermost generated function, including
uninstrumented runtime calls beneath it. These are **exclusive function counts**,
not sampled stacks, exact source call sites, live heap, peak RSS, or all libc
allocations. Instrumentation can affect optimization; do not time this binary.
It targets this generated Rust layout, not arbitrary Rust source. Reports require
normal return from main; process::exit does not run the reporting guard.
`ci/allocation_profiler.py` calibrates attribution with one known 64-byte request.

Generate a separate diagnostic binary with the generated program's compatible
runtime rlib and the same release flags, then require output equivalence:

```sh
ALMIDE_RUN_PROJECT_DIR=/tmp/native almide build
python3 bench/instrument_allocations.py /tmp/native/almide_gen_main.rs /tmp/profile.rs
rustc /tmp/profile.rs --edition=2021 -C opt-level=3 -C overflow-checks=no \
  --extern almide_rt=/path/to/libalmide_rt.rlib -o /tmp/profile
python3 bench/profile_outline.py --gramide ./gramide --profiled /tmp/profile \
  --generated-rust /tmp/native/almide_gen_main.rs \
  --runtime-rlib /path/to/libalmide_rt.rlib --output /tmp/allocations.json
```

[Before](../docs/evidence/python-outline-allocations-before.json) and
[after](../docs/evidence/python-outline-allocations-after.json) record the
instrumented/normal binaries, generated source, runtime rlib and instrumenter
hashes. Both profiles use the same runtime rlib. On all five inputs, instrumented
stdout equals the corresponding normal binary; before/after output hashes also
match. The normal binary is measured separately below.

Three newline predicates in Python physical scanning constructed `[10, 13]`
repeatedly (comment scanning, continuation checks and physical line counting).
Replacing them with an integer predicate gives these allocation-count deltas:

| Input | Total before | Total after | Fewer requests |
| --- | ---: | ---: | ---: |
| inspect.py | 1,451,554 | 1,309,507 | 142,047 |
| typing.py | 1,426,778 | 1,279,121 | 147,657 |
| argparse.py | 1,322,917 | 1,201,475 | 121,442 |
| _pydecimal.py | 2,272,229 | 2,012,359 | 259,870 |
| pydoc_data/topics.py | 638,220 | 56,710 | 581,510 |

All reductions are attributed to `lexer.physical_with`; each removed request
accounts for exactly 16 requested bytes, consistent with the two-i64 temporary
list at those three sites. Reallocation counts are unchanged. These cumulative
requested-byte savings are not a measurement of resident memory. Large remaining
contributors include `tags.decl_kind`, `parser.take_from`, string preparation and
other physical-scanner work, so this does not resolve #37.

### Identical outline work, without instrumentation

The C Python adapter now has a strict `--outline` mode alongside its existing
JSON modes. `python_outline.py` independently renders the CPython AST as nested
outline text (including decorator starts). Every normal old/new/tree-sitter
output must equal it before timing. All 15 inputs pass; the original JSON modes
also retain their CPython/range and recovery comparisons.

```sh
python3 bench/python_outline.py --gramide ./gramide --before /path/to/old-gramide \
  --tree-sitter /path/to/tree-sitter-python --references /path/to/almide-references \
  --output /tmp/outline-timing.json
```

[Five shuffled samples](../docs/evidence/python-newline-outline.json) include
process startup, read, full parse and identical outline output. The code-heavy
examples improve modestly: inspect 64.87→62.83 ms, argparse 59.62→57.24 ms,
_pydecimal 92.95→89.09 ms; ast.py is effectively unchanged. The string-heavy
topics.py control improves 14.34→6.82 ms. Tree-sitter remains faster on every
input (inspect 11.59 ms, _pydecimal 15.91 ms, topics 5.45 ms).
This Python 3.14.4 sample is not the reported 700-file Python 3.13 workload or its
ctxgate-outline binary. No startup subtraction, incremental reuse, RSS claim or
general victory is implied. The full regression suite, real hew integration and
the per-file codopsy-almd complexity baseline pass without relaxing the baseline.

## Borrowable declaration lookup table

The allocation profile identified `tags.decl_kind` as another large source of
requests. Native tuple iteration cloned both candidate strings, and the optional
lookup/closure added work even when no declaration matched. An indexed tuple
lookup and a destructuring loop were inspected but still copied candidates, so
neither was retained.

The CLI and public `SymbolRules.declarations` tuple format stay the same. Each
`of_tree`, `outline` or `symbol_rows` traversal prepares a small record table once
and shares it through recursion. Generated Rust borrows the table and each entry;
only a matched kind is cloned for the return value. A separate match flag retains
first-match semantics even if the first mapped kind is empty. A regression covers
empty maps, unknown syntax and duplicate mappings with an empty first result.

Compared with the preceding newline-predicate profile, the
[new same-runtime profile](../docs/evidence/python-kind-borrow-allocations.json)
reduces declaration-lookup allocations on inspect.py from 206,313 to 162 and on
typing.py from 200,587 to 253. The prepared Python table costs 19 allocation
requests once per traversal. Total instrumented allocations drop from 1,309,507
to 1,103,375 on inspect and 2,012,359 to 1,688,636 on _pydecimal; all five normal
output hashes and source hashes match the baseline. These remain diagnostic
request counts, not timing or peak-RSS measurements.

[Normal Python outline timing](../docs/evidence/python-kind-borrow-outline.json)
requires CPython-equivalent output for all 15 old/new/tree-sitter runs. Fourteen
medians decrease: inspect 63.16→60.00 ms, typing 65.47→61.83 ms, argparse
61.63→55.58 ms, _pydecimal 105.66→92.14 ms. genericpath increases 7.27→7.48 ms;
that sample is retained. Tree-sitter is still faster throughout.

Because the lookup is shared, a [Go structured-symbol comparison](../docs/evidence/go-kind-borrow-symbols.json)
also checks 100/400/800 generated functions against unchanged old/new/tree-sitter
ranges. The 800-function median decreases 19.68→18.03 ms (tree-sitter 6.89 ms).
This small generated Go corpus is not general Go or Rust performance evidence.
The full multi-language regression suite, real hew integration and unchanged
per-file codopsy-almd baseline pass. Issue #37, the complete 700-file workload,
peak memory, incremental reuse and general superiority remain unfinished.

## Scalar Python scanner dispatch

The Python physical scanner previously built an unexpected-character diagnostic
and used `option.map` with a default `"normal"` string on every iteration.
Fallback diagnostics now live in the branches that consume them, with saved
starting byte coordinates. A scalar mode classifier replaces the map/default
string without changing the interpolation frame representation. Generated Rust
matches the frame's borrowed mode text and returns an integer; ordinary source
uses the allocation-free `None` branch. Existing frame copies within active
interpolations remain. The 21 strict-command diagnostic checks cover Unicode,
CRLF, invalid continuations, f/t strings and excessive interpolation nesting.

The [same-runtime allocation profile](../docs/evidence/python-scalar-mode-allocations.json)
compared with the preceding declaration-table change reports:

| File | Total allocations before → after | Physical scanner before → after |
| --- | ---: | ---: |
| inspect.py | 1,103,375 → 969,938 | 232,957 → 99,520 |
| typing.py | 1,078,806 → 961,793 | 217,773 → 100,760 |
| argparse.py | 1,023,829 → 894,248 | 219,689 → 90,108 |
| _pydecimal.py | 1,688,636 → 1,480,180 | 356,034 → 147,578 |
| pydoc_data/topics.py | 49,393 → 46,954 | 2,867 → 428 |

Source/output hashes and the diagnostic runtime hash match the preceding
profile. Counts attribute Rust allocation requests to the innermost generated
function, not exact call sites, live memory, RSS or all libc allocations.
Instrumentation can affect optimization; timings use normal binaries instead.

The [paired normal-binary outline comparison](../docs/evidence/python-scalar-mode-outline.json)
checks identical text against CPython AST for all 15 files before timing.
Fourteen medians improve; token.py increases from 5.283 to 5.314 ms and is retained.
inspect.py improves from 58.02 to 56.00 ms, argparse.py from 54.59 to 52.60 ms,
and _pydecimal.py from 84.41 to 81.30 ms. The tree-sitter adapter remains faster
on every file (11.28, 10.66 and 15.95 ms respectively for those three examples).
These five-sample, startup-inclusive Python 3.14 comparisons are not the
700-file Python 3.13 workload in issue #37, which remains unresolved.

## Borrowed Python token preparation

The next profile identified whole-list copying into escape validation and indexed
per-token cloning in the conversion-adjacency check. A `TokenBuffer` record now
owns the input once. Generated Rust passes `&buffer` to validation and iterates
`buffer.items.iter()` for adjacency checks, then consumes the items for lexical
kind refinement. Escape validation still precedes adjacency diagnostics. Copies
inside escape validation and the final map remain; this is not a zero-copy claim.

Reference inspection: CPython at `f715d25a8f0f0d57ecd2ae0dfe56c2ee01752733`
uses buffer-relative positions in `Parser/lexer/buffer.h`; tree-sitter at
`de98c6c970f4c5d3a725ee48199c478090d614af`, `lib/src/tree.c`, retains its root
subtree when copying a tree. These are examples of avoiding repeated deep data
copies, not evidence that gramide shares their ownership or incremental design.
The internal record here addresses the actual generated native call convention;
the public token preparation input and output remain lists.

[Same-runtime allocation evidence](../docs/evidence/python-token-preparation-allocations.json)
compared with scalar scanner dispatch:

| File | Total allocations before → after | Preparation before → after |
| --- | ---: | ---: |
| inspect.py | 969,938 → 872,566 | 131,494 → 34,122 |
| typing.py | 961,793 → 866,821 | 128,316 → 33,344 |
| argparse.py | 894,248 → 809,074 | 114,851 → 29,677 |
| _pydecimal.py | 1,480,180 → 1,328,802 | 204,706 → 53,328 |
| pydoc_data/topics.py | 46,954 → 45,000 | 3,085 → 1,131 |

Source, output and diagnostic runtime hashes match the preceding profile.
Counts remain exclusive generated-function Rust allocation attribution, not
exact call sites, live heap, RSS or all libc allocations. Instrumentation may
change optimization.

[Uninstrumented paired timing](../docs/evidence/python-token-preparation-outline.json)
validates all 15 outlines against CPython AST before taking five shuffled
samples with startup included. Fourteen medians decrease, with stat.py effectively
unchanged. copyreg.py increases from 6.59 to 7.28 ms; that result is retained.
inspect.py decreases from 55.52 to 53.02 ms, argparse.py from 51.06 to 49.15 ms,
and _pydecimal.py from 80.22 to 77.18 ms. Tree-sitter remains faster throughout,
including 11.22, 10.05 and 15.65 ms respectively for those three files.
The full regression suite, unchanged structural complexity gate and real hew
integration pass. Issue #37's 700-file Python 3.13 workload, incremental parsing,
peak memory and general tree-sitter superiority remain unresolved.

## Single-child drain reuse

`parser.take_from` moved children through two lists to recover their original
order. Zero/one child already has the correct order, so that branch now returns
the first list directly. Generated Rust moves it without cloning; multi-child
drains retain the existing ordering algorithm. A direct regression covers an
untouched prefix, empty drain, nested single child, multiple ordered siblings
and draining the whole list.

Reference: tree-sitter `de98c6c970f4c5d3a725ee48199c478090d614af`,
`lib/src/subtree.c:ts_subtree_new_node`, takes ownership of its child array and
allocates node data at its end, reallocating only when capacity is insufficient.
Gramide does not use that compact representation; avoiding a redundant child
buffer is one step toward lower allocation costs, not equivalent architecture.

[Same-runtime profiles](../docs/evidence/single-child-allocations.json) compared
with token preparation borrowing preserve all source/output hashes:

| File | Total allocations before → after | take_from before → after |
| --- | ---: | ---: |
| inspect.py | 872,566 → 815,957 | 131,266 → 74,657 |
| typing.py | 866,821 → 810,229 | 131,922 → 75,330 |
| argparse.py | 809,074 → 750,852 | 134,766 → 76,544 |
| _pydecimal.py | 1,328,802 → 1,249,602 | 184,584 → 105,384 |
| pydoc_data/topics.py | 45,000 → 41,731 | 7,188 → 3,919 |

These are exclusive generated-function Rust allocation requests, not exact
call sites, live heap, RSS or all libc allocations; instrumentation can affect
optimization. The normal binary used for timing has a recorded matching hash.

[Normal Python outline comparison](../docs/evidence/single-child-outline.json)
requires CPython-equivalent output for all 15 files. Eleven medians decrease;
token.py, stat.py, copyreg.py and topics.py increase and are retained. In this
five-sample startup-inclusive run inspect.py is 53.14 → 52.07 ms, argparse.py
49.81 → 48.12 ms and _pydecimal.py 77.65 → 75.53 ms. Tree-sitter is still faster
throughout (11.08, 10.13 and 16.10 ms for those three files).

The shared engine also passes the [generated Go comparison](../docs/evidence/single-child-go.json):
all 100/400/800-function symbol ranges agree with the old binary and tree-sitter.
The 100/400 medians decrease; 800 increases 16.43 → 16.93 ms (tree-sitter 6.48 ms).
This is a consistent allocation reduction, not a universal timing improvement.
The full regression suite, unchanged structural baseline and real hew integration
pass. Full issue #37 reproduction, incremental performance and superiority across
languages remain unresolved.

## Full installed Python stdlib outline survey

Run the correctness survey independently of timing:

```sh
python3 bench/python_stdlib.py --gramide ./gramide \
  --tree-sitter /tmp/gramide-tree-sitter-python-outline \
  --references ../almide-references --output /tmp/python-full-stdlib.json
```

The harness uses the running interpreter's stdlib and excludes directory components
`test`, `tests`, `lib2to3`, `site-packages` and `__pycache__`. It reads source using
Python's declared-encoding rules, renders CPython AST using the same shared oracle
as `python_outline.py`, and requires exact outline text, zero exit status and empty
stderr. It records every file's raw source hash and byte size, oracle/output hashes,
failures, binary hashes and reference revisions. Oracle errors and gramide mismatches
fail the command after saving the report; comparator mismatches are retained in the
report without hiding otherwise valid gramide results. An empty corpus fails.

The [Python 3.14.4 result](../docs/evidence/python-full-stdlib.json), using gramide
from PR #43, covers **721 files / 12,175,027 bytes** with no oracle errors:

| Implementation | Exact CPython outline matches |
| --- | ---: |
| gramide | 721 / 721 |
| tree-sitter Python + repository outline adapter | 720 / 721 |

The difference is `unittest/mock.py`: its two `type(mock).attribute = value`
assignments become extra type declarations in the tree-sitter result. A minimized
`type(mock).__signature__ = sig` parses in CPython as an `Assign` to an `Attribute`
whose object is a `Call`, and gramide produces no outline declaration. Dumping the
pinned tree-sitter root with `ts_node_string` produces:

```text
(module (type_alias_statement left: (type (attribute object: (parenthesized_expression (identifier)) attribute: (identifier))) right: (type (identifier))))
```

Thus the incorrect type-alias classification already exists in the pinned grammar's
tree, and the adapter exposes it as `L1-1 type mock`. The corpus report retains both
extra lines rather than suppressing this case. This finding concerns the pinned
`tree-sitter-python` revision, not every release or every tree-sitter consumer.

The 15-file timing harness still passes after extracting its AST renderer into
`python_outline_oracle.py`. This survey proves outline equality on valid source,
not full semantic equivalence, malformed-input recovery, incremental reuse or
performance. It is Python 3.14.4, not the exact 700-file Python 3.13 workload in
issue #37; that issue remains open.

## Scalar outline depth and borrowed membership checks

The outline walker previously passed and copied an indentation string at every
syntax node. It now passes integer declaration depth and materializes indentation
only when emitting a declaration. Scope/callable membership uses a direct borrowed
scan: generated Rust accepts `&str` and iterates borrowed candidates, avoiding the
owned-string argument required by the previous `list.contains` call. Membership
is still boolean, including empty lists and duplicate entries. Owner rules,
output formatting and declaration nesting are unchanged.

Reference inspection: tree-sitter at `de98c6c970f4c5d3a725ee48199c478090d614af`
uses an integer depth in `lib/src/tree_cursor.c:ts_tree_cursor_current_depth`.
Its visible-node depth differs from gramide's declaration depth; the relevant
representation choice is keeping traversal depth separate from output text.

[Same-runtime allocation counts](../docs/evidence/outline-depth-allocations.json)
compared with the single-child drain change:

| File | Total allocations before → after | outline_walk before → after | scope_under before → after |
| --- | ---: | ---: | ---: |
| inspect.py | 815,957 → 700,856 | 88,306 → 32,072 | 59,269 → 564 |
| typing.py | 810,229 → 701,023 | 84,995 → 32,995 | 57,873 → 920 |
| argparse.py | 750,852 → 649,821 | 78,745 → 28,455 | 51,006 → 438 |
| _pydecimal.py | 1,249,602 → 1,067,291 | 140,554 → 50,686 | 92,738 → 553 |
| pydoc_data/topics.py | 41,731 → 39,635 | 1,047 → 1,047 | 2,096 → 0 |

Source/output and diagnostic-runtime hashes agree with the baseline. Counts are
exclusive generated-function Rust allocation requests, not exact call sites,
live heap, RSS or all libc allocations. Instrumentation can affect optimization.

The [full stdlib survey](../docs/evidence/outline-depth-stdlib.json) still matches
CPython outlines on 721/721 Python 3.14.4 files. The pinned tree-sitter adapter is
unchanged at 720/721, with the same mock.py mismatch. The full regression suite,
unchanged structural baseline and real hew integration pass.

[Python timing](../docs/evidence/outline-depth-timing.json) and
[Go comparison](../docs/evidence/outline-depth-go.json) retain all raw samples
and output equality checks, but **do not support a speedup or ranking claim**.
The machine was under concurrent load: after the Python run, load average was
14.42 and a process-name/CPU inspection showed another rustc plus busy system
services; after the Go run the one-minute load average was 22.00. Both comparators
showed large timing swings. For example, the tree-sitter Go 800-function median
was 106.30 ms, compared with 6.48 ms in the preceding run. Do not present that
as a gramide victory, discard regressions selectively or subtract a historical
startup estimate. A quiet paired run is required for timing conclusions.
This change is justified by native code inspection, allocation reduction and
output equivalence; issue #37 and the broader tree-sitter goal remain open.

## Borrowed, combined parser token numbering

`parse_with`, `verify` and `parse_recovering` previously cloned the entire token
stream for each of the kind/text numbering passes. A `TokenInput` record now
owns the stream once; `number_tokens` borrows it and produces both exactly-sized
integer arrays in one pass. Generated Rust borrows those arrays during parsing
and moves the original tokens into `Parsed` on success. The old `kind_ids` and
`text_ids` helpers remain available, but the three parser entry points no longer
use their two-pass path. Unknown kind/text values still map to -1, independently.
Map lookup key strings still clone; this is not a zero-allocation numbering pass.

Reference inspection: tree-sitter at `de98c6c970f4c5d3a725ee48199c478090d614af`,
`lib/src/parser.c`, consumes the lexer's numeric `result_symbol` and maps external
scanner symbols to grammar symbols. Gramide still performs map-based numbering
after lexing. This change removes redundant token ownership transfers around
that numbering; direct lexer symbol IDs remain a separate design opportunity.

[Same-runtime allocation profiles](../docs/evidence/token-numbering-allocations.json)
compared with scalar outline depth preserve source/output hashes:

| File | Total allocations before → after |
| --- | ---: |
| inspect.py | 700,856 → 635,940 |
| typing.py | 701,023 → 637,707 |
| argparse.py | 649,821 → 593,037 |
| _pydecimal.py | 1,067,291 → 966,371 |
| pydoc_data/topics.py | 39,635 → 38,331 |

`parse_with` itself now accounts for one allocation on each file; numbering
allocations move into `number_tokens` (32,459 on inspect.py). Total reductions,
not changes in function attribution alone, establish the savings. Reallocation
counts also decrease because the integer vectors have exact token-count capacity.
These are exclusive generated-function Rust allocation requests using the same
diagnostic runtime, not exact call sites, live heap, RSS or all libc allocations.
Instrumentation may affect optimization.

The [final-binary stdlib survey](../docs/evidence/token-numbering-stdlib.json)
passes 721/721 CPython outlines, with the pinned tree-sitter adapter retaining its
known 720/721 result. Full local CI, the unchanged structural complexity baseline
and real hew integration pass. The normal binary hash matches between the corpus
and allocation reports. No new wall-time result is claimed: the machine's load
average remained elevated (12.35 after validation), following the noisy preceding
run. Quiet paired timing, the exact issue #37 workload and incremental parsing
remain unfinished.

## Repeated timing after the two copy reductions

`python_outline.py` now accepts `--samples N` (positive integer, default 5), records
the selected count and still checks every timed output against CPython. This lets
noisy runs be investigated without editing the harness or dropping earlier data.

Following the high-load run above, the load average had fallen to 3.99. A
[five-sample comparison](../docs/evidence/combined-copy-timing-five.json) still had
mixed results, so a [21-sample comparison](../docs/evidence/combined-copy-timing-21.json)
was run with the same binaries. Both reports are retained. The baseline is PR #43;
the current binary includes scalar outline depth/borrowed membership (PR #45) and
combined borrowed token numbering (PR #46). Binary hashes match their allocation
profiles. This comparison measures their combined effect, not either change alone.

All 945 timed outputs (15 files × 3 implementations × 21 samples) match CPython.
Fourteen file medians improve; keyword.py increases from 4.267 to 4.313 ms.
Representative medians, including startup, reading and identical outline output:

| File | Before (ms) | After (ms) | tree-sitter (ms) |
| --- | ---: | ---: | ---: |
| inspect.py | 53.86 | 50.42 | 12.68 |
| typing.py | 54.22 | 51.19 | 12.39 |
| argparse.py | 50.53 | 46.88 | 11.36 |
| _pydecimal.py | 78.02 | 72.12 | 17.11 |

The changes reduce these medians by approximately 5.6–7.6%, while tree-sitter
remains about four times faster. More samples do not make a shared machine an
isolated benchmark environment, and these medians are not a statistical-significance
claim. This is still the selected 15-file Python 3.14 corpus, not issue #37's exact
Python 3.13 corpus, nor incremental or peak-memory evidence. The earlier noisy
measurements remain valid records of those runs, not results to hide.

## String prefixes and delimiters decided from the bytes

Physical Python scanning lowered the text of every identifier and tested it
against `["f", "fr", "rf", "t", "tr", "rt"]` before it looked for a quote, so
each name in the file built that list of spellings and a lowered copy of
itself. The layout pass did the same with punctuation, testing `t.text`
against `["(", "[", "{"]` and then `[")", "]", "}"]`. Neither question needs
the text. The prefix that opens an interpolated literal is one or two ASCII
letters glued to a quote, and a delimiter is a single byte: `prefix_code`
reads the letters and the quote, `single_byte`, `opens_bracket` and
`opener_of` read the delimiter. The ordinary identifier and the ordinary
operator — most of the tokens in a file — now leave the allocating path.

The accepted language is unchanged. The prefix set is still `f` and `t`, in
either order with `r`, case-insensitively, and byte and unicode prefixes stay
with `strings.opening` where they were; the bracket pairs are the same three,
and a token longer than one byte is still never a delimiter. Token kinds,
byte ranges, diagnostics and the recovery rules are untouched.

Same-runtime allocation profiles,
[before](../docs/evidence/scanner-constants-allocations-before.json) and
[after](../docs/evidence/scanner-constants-allocations.json), with equal
source and output hashes on every file:

| File | Total allocations before → after | Fewer |
| --- | ---: | ---: |
| inspect.py | 635,940 → 498,266 | 21.6% |
| typing.py | 637,707 → 504,411 | 20.9% |
| argparse.py | 593,037 → 469,911 | 20.8% |
| _pydecimal.py | 966,371 → 756,727 | 21.7% |
| pydoc_data/topics.py | 38,331 → 36,863 | 3.8% |

The reduction sits where the change is. On inspect.py `physical_with` falls
from 99,520 requests to 17,164 and `apply_with` from 90,284 to 36,256; no
other function moves by more than 1,500. The string-heavy control barely
moves, which is the shape of the thing: it is one enormous literal with
almost no names and almost no punctuation. These are exclusive
generated-function Rust allocation requests under the same diagnostic
runtime, not exact call sites, live heap, RSS or all libc allocations, and
instrumentation can affect optimization.

[Timing](../docs/evidence/scanner-constants-timing.json): 21 shuffled samples
per binary, fresh process, startup included, no incremental reuse. All 945
timed outputs (15 files × 3 implementations × 21 samples) match CPython.

| File | Before (ms) | After (ms) | tree-sitter (ms) |
| --- | ---: | ---: | ---: |
| inspect.py | 47.80 | 45.49 | 10.81 |
| typing.py | 46.71 | 44.68 | 10.73 |
| argparse.py | 44.85 | 42.40 | 9.91 |
| _pydecimal.py | 69.93 | 65.92 | 15.71 |
| ast.py | 12.59 | 12.16 | 4.23 |

Fourteen of the fifteen medians improve, by 1.5% to 5.7%; the string-heavy
control is flat at 6.21 → 6.22 ms, which is what a file with almost no names
and almost no punctuation should do. The share is smaller than the 21% of
allocations removed because every median includes process startup, and on the
small files that is most of the measurement. The one-minute load average was
3.30 before the run and 3.19 after. These are medians on a shared machine, not
a significance claim, and tree-sitter is still about four times faster on the
same measurement.

The [full stdlib survey](../docs/evidence/scanner-constants-stdlib.json) still
matches CPython outlines on 721/721 Python 3.14.4 files, with the pinned
tree-sitter adapter at its known 720/721 and the same mock.py mismatch. Full
local CI passes, including the CPython oracles this change is nearest to:
2,020 ordinary string boundaries, 409 lexer cases, and 25 layout cases with
51 rejections. The structural complexity baseline is unchanged, and issue #37
and the broader tree-sitter goal remain open.

## A token's kind is a number

Six passes walk the token stream for one Python file: the physical scanner
builds it, the layout pass rewrites it into logical lines, `escapes.validate`
checks literals, `string_expressions.prepare` refines two kinds, the reader
hands the stream to the parser, and `number_tokens` numbers it. A `Token` held
two owned strings, so every one of those passes allocated a string per token
for the kind alone.

`tree.almd` now numbers the kinds. `kind_names` is the one table — an id is a
position in it — and `kind_id` and `kind_name` read it in both directions, so
a grammar naming a terminal `tok("identifier")` resolves to the number the
lexer already wrote on the token. The terminals the engine tests itself move
with them: `eof`, `newline`, `indent`, `dedent`, `string` and `neg` are kinds
and now come from that table, which leaves `compile`'s text numbering to the
spellings literals actually ask for, and `SEEDS` pins those seven. A kind the
table does not name answers -1, which no token carries, so a grammar that
misspells a terminal matches nothing — exactly as it did when the name was
interned and never found.

Same-runtime allocation profiles,
[before](../docs/evidence/token-kind-ids-allocations-before.json) and
[after](../docs/evidence/token-kind-ids-allocations.json), source and output
hashes equal on every file:

| File | Total allocations before → after | Fewer |
| --- | ---: | ---: |
| inspect.py | 498,266 → 391,165 | 21.5% |
| typing.py | 504,411 → 397,189 | 21.3% |
| argparse.py | 469,911 → 374,995 | 20.2% |
| _pydecimal.py | 756,727 → 589,771 | 22.1% |
| pydoc_data/topics.py | 36,863 → 35,468 | 3.8% |

The per-function moves say what the change is. inspect.py holds 16,963 tokens,
and on it `apply_with`, `read_lang`, `prepare`, `number_tokens` and `validate`
each lose between 16,963 and 16,979 requests — one per token — while
`physical_with` loses the 16,857 it still had and `code_end` loses 3,030.
`kind_names` gains 806: the table is rebuilt for each terminal the grammar
compile resolves, once per process. These are exclusive generated-function
Rust allocation requests under the same diagnostic runtime, not exact call
sites, live heap, RSS or all libc allocations.

What remains is the other string. `text_at` (102,032 requests on inspect.py),
`take_from` (74,657) and `lexer_make` (50,513) are now the three largest, and
the first two are about the tree, not the token stream.

Two test-only probes renamed their local `node` helper to `node_value`: with
the larger `tree.almd`, the unqualified recursive call in
`ci/python_expressions_probe.almd` began resolving to `tree.node` rather than
to the probe's own function. Nothing under `src/` depends on that name, and
the probes' JSON output is unchanged.

[Timing](../docs/evidence/token-kind-ids-timing.json), 21 shuffled samples per
binary against the merged previous change, startup included, all 945 timed
outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) |
| --- | ---: | ---: | ---: |
| inspect.py | 46.37 | 44.16 | 11.34 |
| typing.py | 45.59 | 43.37 | 11.27 |
| argparse.py | 43.52 | 41.49 | 10.48 |
| _pydecimal.py | 67.44 | 63.09 | 16.13 |
| dataclasses.py | 24.54 | 23.43 | 8.34 |

Fourteen of the fifteen medians improve, by 0.2% to 6.5%; token.py reads 1.5%
slower and is a 4.8 ms file where startup is most of the measurement. An
earlier run of the same comparison was discarded for timing: another process
on the machine took the one-minute load average from 3.7 to 10.5 mid-run and
doubled tree-sitter's own medians. This one ran at 3.7 to 3.9. Medians on a
shared machine are not a significance claim, and tree-sitter is still about
four times faster with startup included.

The [full stdlib survey](../docs/evidence/token-kind-ids-stdlib.json) matches
CPython outlines on 721/721 Python 3.14.4 files, with the pinned tree-sitter
adapter at its known 720/721. Full local CI passes — the four-language smoke
check, the Go parser range oracle, and the CPython layout, string, number,
identifier, lexer, expression, statement, symbol and recovery oracles — and
the structural complexity baseline is unchanged.

## A token is a range, not a copy

Every construction site already wrote the same text: `lex.mk` and the Python
scanner both cut `source[start..end]`, a layout marker is empty with
`start == end`, and the two error tokens cover exactly the bytes they name. So
the `text` field said nothing the offsets did not, and cost an allocation per
token at every hand-off — the lexer built it, the layout pass rebuilt it, the
reader's match arms cloned the stream, `prepare` rebuilt it again.

`Token` is now `{ kind, start, end, line, col }`: five scalars, copied without
touching the heap. `tree.token_text(source, t)` cuts the text when something
actually wants it, and the source travels beside the tokens — the parser takes
it so a failure can quote what it found, `tags` takes it so a declaration can
be named, and the reader passes the bytes it already read.

Two consequences worth naming. `escapes.validate` no longer copies a literal
out of its token to index it: it reads the source where the token sits, so
numeric escape validation allocates nothing at all. And `tags`'s local copies
of the tree helpers now have their own names — `leaf_word`, `joined_words`,
`last_line`, `first_line`, `named_child` — because they no longer share a
signature with the module's, and a local function that merely shares a name
with an imported one is not reliably the one an unqualified call resolves to.

Same-runtime allocation profiles,
[before](../docs/evidence/token-text-allocations-before.json) and
[after](../docs/evidence/token-text-allocations.json), source and output hashes
equal on every file:

| File | Total allocations before → after | Fewer |
| --- | ---: | ---: |
| inspect.py | 391,165 → 304,479 | 22.2% |
| typing.py | 397,189 → 310,693 | 21.8% |
| argparse.py | 374,995 → 297,617 | 20.6% |
| _pydecimal.py | 589,771 → 454,374 | 23.0% |
| pydoc_data/topics.py | 35,468 → 32,148 | 9.4% |

The passes over the stream now cost nothing to walk. On inspect.py `lexer_make`
falls from 50,513 requests to 0, `apply_with` from 18,129 to 6,
`escapes_validate` from 17,050 to 1, `number_tokens` from 15,496 to 2 and
`read_lang` from 16,638 to 1,146. Against that, `token_text` is new and costs
48,476: two requests for each of the 16,963 tokens the parser still numbers by
its text, plus the names the outline cuts. Numbering a token without
materialising its text is the next thing to do, and it is worth about 34,000
requests on this file.

The [full stdlib survey](../docs/evidence/token-text-stdlib.json) matches
CPython outlines on 721/721 Python 3.14.4 files, with the pinned tree-sitter
adapter at its known 720/721. Full local CI passes, including the byte-range
oracle that checks every layout token still spans exactly the source it
reports, and the structural complexity baseline is unchanged.

[Timing](../docs/evidence/token-text-timing.json), 21 shuffled samples per
binary, startup included, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) |
| --- | ---: | ---: | ---: |
| inspect.py | 43.95 | 41.26 | 11.25 |
| typing.py | 43.31 | 40.95 | 11.22 |
| argparse.py | 41.35 | 39.58 | 10.48 |
| _pydecimal.py | 63.27 | 59.71 | 16.27 |
| dataclasses.py | 23.49 | 22.32 | 8.16 |

Fourteen of the fifteen medians improve, by 0.5% to 6.1%; textwrap.py reads
0.5% slower and is a 7 ms file. The load average was 3.89 before the run and
3.71 after. Medians on a shared machine are not a significance claim.

Taken with the two changes before it, inspect.py has gone from 635,940
allocation requests to 304,479 and from 48.98 ms to 41.26 ms, while
tree-sitter has stayed at about 11.3 ms on the same measurement: 4.3x to 3.7x.
The remaining requests are no longer about the token stream at all. `text_at`
(102,032) clones a node's kind name out of the grammar for every leaf the
parser keeps, `take_from` (74,657) builds each node's child list in two
allocations, and `token_text` (48,476) is mostly the parser numbering tokens
it could number from the bytes.

## Numbering a token without cutting a string out of the source

`number_tokens` asked `Map[String, Int]` what a token's text was worth, which
meant cutting that text out of the source first: two allocations for every
token, and a string hash for a question that is "no" for every ordinary name
in the file.

`compile` now packs the terminal spellings it has interned — every literal a
rule asks for — into one byte list in atom order, with a bucket chain keyed by
a spelling's first byte and its length. `atom_at` reads the source where the
token sits: a token whose first byte and width no literal shares lands in an
empty bucket and answers -1 having touched nothing, and one that shares them
is compared byte by byte against the packed spelling. The answers are the same
by construction — the same interned set, compared for equality — and the dead
`text_ids` helper, which numbered a stream the entry points stopped using two
changes ago, is gone.

Same-runtime allocation profiles,
[before](../docs/evidence/atom-lookup-allocations-before.json) and
[after](../docs/evidence/atom-lookup-allocations.json), source and output
hashes equal on every file:

| File | Total allocations before → after | Fewer |
| --- | ---: | ---: |
| inspect.py | 304,479 → 256,817 | 15.7% |
| typing.py | 310,693 → 264,143 | 15.0% |
| argparse.py | 297,617 → 255,871 | 14.0% |
| _pydecimal.py | 454,374 → 380,065 | 16.4% |
| pydoc_data/topics.py | 32,148 → 31,461 | 2.1% |

One function moves: `token_text` falls from 48,476 requests to 525 on
inspect.py, and nothing else changes by more than 300. What is left of it is
the names the outline actually prints. Reallocation counts rise from 697 to
728, which is the packed table growing as it is built, once per process.

The [full stdlib survey](../docs/evidence/atom-lookup-stdlib.json) matches
CPython outlines on 721/721 Python 3.14.4 files, with the pinned tree-sitter
adapter at its known 720/721, and full local CI passes.

[Timing](../docs/evidence/atom-lookup-timing.json), 21 shuffled samples per
binary, startup included, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) |
| --- | ---: | ---: | ---: |
| inspect.py | 40.79 | 39.89 | 11.13 |
| typing.py | 39.87 | 38.90 | 10.76 |
| argparse.py | 38.31 | 37.64 | 10.29 |
| _pydecimal.py | 58.68 | 57.12 | 15.78 |
| dataclasses.py | 21.86 | 21.24 | 7.91 |

Twelve of the fifteen medians improve, by 1.0% to 5.7%; three small files read
0.2% to 1.7% slower. The gain is smaller than the 15.7% of allocations removed,
and that is the useful part of the result: a short-lived 8-byte string costs
tens of nanoseconds, so what is left to win in this engine is no longer in the
allocator. A CPU sample of a 2.5 MB parse puts 47% of the time inside
`parse_rule` itself and 20% in `miss`, against 8.5% in malloc and free
together — the engine visits the grammar arena about seventy times per token,
and that count, not the heap, is what stands between it and tree-sitter.

## The pass that succeeds stops recording where it failed

`miss` is the engine's busiest path: every alternative that does not match
goes through it, and a CPU sample of a 2.5 MB parse put 20% of the time
there. What it did was maintain `far`, the farthest token anything failed at,
and the set of what was expected there.

Neither is ever read from the pass that computes it. A parse that fails runs a
second time with `collect` on, and `parse_with`, `verify` and
`parse_recovering` all take `far` and the expectation set from *that* run.
The first run's copy is thrown away — as is the whole of it for a file that
parses, which is the case every reader is timing. So `miss` now returns the
state it was given unless the pass is collecting, and `noted` runs only on the
pass whose answer somebody reads.

Nothing about the messages changes: the collecting pass is untouched, and
`check` prints the same "unexpected X (expected …)" for the same files.

[Allocation profiles](../docs/evidence/failure-tracking-allocations.json) are
identical to the change before it on all five files — 256,817 requests on
inspect.py, to the request — which is the point: this one buys time, not heap.

[Timing](../docs/evidence/failure-tracking-timing.json), 21 shuffled samples
per binary, startup included, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 40.00 | 35.46 | 11.12 | 3.2x |
| typing.py | 39.20 | 34.85 | 10.79 | 3.2x |
| argparse.py | 37.81 | 33.63 | 9.91 | 3.4x |
| _pydecimal.py | 57.16 | 50.53 | 15.59 | 3.2x |
| dataclasses.py | 21.38 | 19.30 | 7.93 | 2.4x |

Thirteen of the fifteen medians improve; the four code-heavy files all improve
by 11.1% to 11.6%, which is the most any single change in this file has bought.
keyword.py reads 6.7% slower and is a 4 ms file that is almost all startup.
A fresh CPU sample shows `miss` down from 20% to 13% of a 2.5 MB parse: what
is left of it is the call itself, not the work it used to do inside.

The [full stdlib survey](../docs/evidence/failure-tracking-stdlib.json) matches
CPython outlines on 721/721 Python 3.14.4 files and full local CI passes,
including the 21 diagnostic checks that pin the failure messages.

## A literal terminal holds a set of spellings

`name`, the rule behind every Python identifier, is
`seq([nott(lits(HARD_KEYWORDS)), tok("identifier")])`, and `lits` is an
alternation: 35 branches, each a `Lit`, each a call into `parse_rule` that
compares one integer and returns. Every name in a file paid for all of them,
and so did the operator ladders — `keeps(["==", "!=", "<=", "<", ">=", ">",
"in", "is"])` and its neighbours.

A literal op now carries a run rather than a single atom: `a` starts `b` atom
numbers followed by the `b` node ids they came from, and `compile` folds an
alternation whose every branch is a literal into one such op. Matching is a
walk of `b` integers with no call per branch, and a literal that fails names
each of its spellings through the ids in the second half of the run — the same
expectations the branches used to note one by one, in the same order. An
ordinary single literal is a run of one.

Nothing about the messages changes. `check` prints the same
"unexpected X (expected …)" for the same files, and the 21 diagnostic checks
and 160 delimiter-recovery cases in CI pin that.

[Allocation profiles](../docs/evidence/literal-sets-allocations.json) are
unchanged at 256,817 requests on inspect.py; one extra reallocation is the
arena's child list growing at compile time.

[Timing](../docs/evidence/literal-sets-timing.json), 21 shuffled samples per
binary, startup included, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 35.58 | 33.78 | 11.02 | 3.1x |
| typing.py | 35.96 | 34.82 | 11.48 | 3.0x |
| argparse.py | 33.73 | 31.85 | 9.90 | 3.2x |
| _pydecimal.py | 53.40 | 50.37 | 16.74 | 3.0x |
| ast.py | 10.29 | 9.85 | 4.55 | 2.2x |

Thirteen of the fifteen medians improve, by 1.2% to 5.7%. A CPU sample of a
2.5 MB parse no longer shows `miss` at all — the alternation branches that
used to call it are gone — and `parse_rule` is now 79% of the time on its own,
with malloc and free together at 12%.

## A reference is followed once, at compile time

A grammar reference does nothing but stand in front of the rule it names. The
engine visited it, dispatched on its kind, and called `parse_rule` again on its
target: one full visit per `r("...")`, and the Python expression ladder is
fourteen levels of them before an atom is reached.

`compile` now follows them once, at the end, when every target is known. Each
field that pointed at a reference points at what the reference pointed at,
through a chain of aliases to its end — capped, so a cycle cannot spin. The
reference ops stay in the arena, unreferenced; a reference to a rule the
grammar never defines keeps its place, because its failure is what names the
missing rule. Only the child lists the rule trees emitted are followed:
`arena_kids` marks where those end, and the literal runs `compile` appends
after it hold atom numbers, not children.

Messages are unchanged. A reference's own failure never reached the
expectation set, because the reference delegated before it could fail.

[Allocation profiles](../docs/evidence/reference-shortcut-allocations.json)
move by three requests on each file — 256,817 → 256,820 on inspect.py — which
is the arena being rebuilt once at compile time.

[Timing](../docs/evidence/reference-shortcut-timing.json), 21 shuffled samples
per binary, startup included, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 35.15 | 31.47 | 11.36 | 2.8x |
| typing.py | 35.16 | 31.24 | 11.38 | 2.7x |
| argparse.py | 32.58 | 29.29 | 9.81 | 3.0x |
| _pydecimal.py | 49.90 | 44.82 | 16.23 | 2.8x |
| tokenize.py | 10.19 | 8.97 | 4.40 | 2.0x |

Thirteen of the fifteen medians improve; the code-heavy files by 9.9% to 12.0%.
The machine was not quiet — another build held the one-minute load average
between 5 and 10 through the run — so the tree-sitter column is the control:
at 11.36, 11.38, 9.81 and 16.23 ms it is within a few percent of the same
binary's medians in the quiet runs above, which is the reason to read this
comparison at all.

Since the session's first change, inspect.py has gone from 48.98 ms and
635,940 allocation requests to 31.47 ms and 256,820, and from 4.3x tree-sitter
to 2.8x. The engine is still an interpreter walking an arena, and that walk is
now nearly all of the remaining time.

## The dispatch chain is ordered by how often each kind is visited

`parse_rule` chooses what to do with an arena node through a chain of `else
if`s, and the chain was in the order the kinds were declared. `K_LEFT` — one
per precedence level, at every level of the Python expression ladder — was the
trailing `else`, reached only after fifteen comparisons; `K_SEQ` and `K_ALT`,
the two kinds that hold every rule together, were sixth and seventh.

The chain is now ordered by how often a kind is actually visited: sequence,
alternation, literal, token, left fold, wrap, option, repetition, field, and
then the ones a parse meets rarely — reference (`compile` now bypasses almost
all of them), lookahead, epsilon, any, and the recovery rules, which carry the
`else`. Nothing else changes: the arms are the same arms, and the kinds are
disjoint, so the order they are tested in cannot change which one runs.
`parse_rule`'s recorded complexity falls by one, because the recovery arm no
longer needs its condition.

[Timing](../docs/evidence/dispatch-order-timing.json), 21 shuffled samples per
binary on a quiet machine (load average 2.7), all 945 timed outputs matching
CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 30.68 | 29.27 | 11.26 | 2.6x |
| typing.py | 30.82 | 29.03 | 11.00 | 2.6x |
| argparse.py | 29.04 | 27.80 | 10.14 | 2.7x |
| _pydecimal.py | 43.55 | 41.56 | 15.89 | 2.6x |
| dataclasses.py | 17.06 | 16.20 | 8.05 | 2.0x |

Twelve of the fifteen medians improve, the code-heavy files by 4.3% to 5.8%.
Three small files read 0.3% to 2.9% slower and are all under 7 ms.

The [full stdlib survey](../docs/evidence/dispatch-order-stdlib.json) matches
CPython outlines on 721/721 Python 3.14.4 files.

## A ladder of precedence levels is one rule

Python's binary operators are written as six rules, each a left fold whose
operand is the next one down: `bit_or` folds `bit_xor`, which folds `bit_and`,
and so on to `term`. Reaching a name inside an expression meant visiting all
six before the operand was tried, and each of them then asked its own operator
rule whether it was there. `or` and `and` are two more levels above.

`prec(kind, operand, levels)` says the same thing in one rule: the operand,
then one operator per level, lowest precedence first, all left-associative and
all making nodes of one kind. The engine parses the operand once and holds each
operator it finds on a stack until an operator of the same precedence or lower
arrives — which is exactly what nesting the folds achieved by returning. A
level's operator must be a literal terminal, because the ladder reads the token
to decide which level it belongs to before running anything; `leftf` stays for
the folds whose operator is a rule, as in Almide's `seq([nl, keep("or"), nl])`
and Rust's `alt([keep("<<"), seq([keep(">"), lit(">")])])`.

The trees are the same trees. `gramide parse` output is byte-identical on
mixed-precedence expressions, and the CPython expression oracle matches the
same 2,993 trees with the same digest as before the change.

Two terminals moved out of `parse_rule` to make room for the new arm:
`token_here` and `literal_here` are leaf functions that never call back into
it, so the engine's one big function is about choosing what to do rather than
doing it, and its recorded complexity is unchanged.

[Timing](../docs/evidence/precedence-ladder-timing.json), 21 shuffled samples
per binary on a quiet machine (load average 3.4), all 945 timed outputs
matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 29.12 | 27.34 | 11.21 | 2.4x |
| typing.py | 28.58 | 27.14 | 10.84 | 2.5x |
| argparse.py | 27.86 | 26.02 | 10.12 | 2.6x |
| _pydecimal.py | 41.47 | 39.06 | 15.77 | 2.5x |
| dataclasses.py | 16.21 | 15.20 | 7.92 | 1.9x |

Fourteen of the fifteen medians improve, the code-heavy files by 4.7% to 6.6%.

[Allocations](../docs/evidence/precedence-ladder-allocations.json) rise by
1,818 on inspect.py, to 258,638. The ladder keeps its pending operations on
four lists, and an expression that has an operator pays for them; this is the
first change in the session that buys time with heap rather than the other way
round, and at 0.7% it is worth it.

The [full stdlib survey](../docs/evidence/precedence-ladder-stdlib.json)
matches CPython outlines on 721/721 Python 3.14.4 files. Go, Rust and Almide
still use the nested form, and folding their ladders — the ones whose operators
are literals — is left for later.

## A branch the token cannot begin is not walked into

An alternation tried each branch by parsing it, and a repetition ended by
parsing its body one last time and failing. Both are how a PEG works, and both
mean walking a long way in to learn something the first token already said:
`simple_stmt` has fourteen branches, nine of which begin with a keyword, and
every `rep(seq([lit(","), item]))` in the grammar ends by descending into an
item that is not there.

`compile` now records, for each node, the terminal the rule it heads must
begin with — following the first child of a sequence, through wraps, fields,
folds and ladders — or -1 when the rule can begin in more than one way. An
optional, a repetition or a lookahead in front of the first element answers -1,
because then the rule can begin elsewhere. `may_start` reads the token against
that terminal, and an alternation branch, a repetition body or an optional that
cannot possibly match is skipped rather than entered.

The collecting pass never skips, so a file that fails is still described by
every branch that could have applied: the messages are the ones the 21
diagnostic checks pin, unchanged.

The table is built by repeated linear passes over the arena, not by walking
each chain: a node's answer is its first child's, and a child emitted before
its parent is already answered in the same pass, so two passes settle it.
Written recursively it cost 2.7 ms of startup — the whole table copied at every
node — which a file that parses in 3 ms cannot afford. Measured against a build
without the table at all, startup moves by 0.03 ms.

[Allocations](../docs/evidence/head-pruning-allocations.json) move by 13
requests on inspect.py, to 258,651.

[Timing](../docs/evidence/head-pruning-timing.json), 21 shuffled samples per
binary on a quiet machine (load average 2.6), all 945 timed outputs matching
CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 26.91 | 23.09 | 10.68 | 2.2x |
| typing.py | 26.85 | 23.00 | 10.59 | 2.2x |
| argparse.py | 25.63 | 22.07 | 9.79 | 2.3x |
| _pydecimal.py | 38.69 | 33.25 | 15.25 | 2.2x |
| dataclasses.py | 15.09 | 13.18 | 7.56 | 1.7x |

Fourteen of the fifteen medians improve, the code-heavy files by 12.6% to
14.3%; keyword.py reads 1.4% slower and is 3.3 ms of mostly startup. This is
the largest single change in the session.

The [full stdlib survey](../docs/evidence/head-pruning-stdlib.json) matches
CPython outlines on 721/721 Python 3.14.4 files.

## A necessary condition, checked by a scan

Two thousand expression statements cost 37 ms to check; two thousand
assignments cost 19 ms and two thousand `pass` statements 5 ms. The reason is
that `simple_stmt` tries `assignment` first, and all four of its forms —
annotated, annotated-with-target, plain and augmented — parse the whole
expression before finding out that no `:`, `=` or augmented operator follows.
An expression statement pays for the expression five times.

Every one of those forms needs one of those spellings somewhere on the logical
line, outside brackets. `needs(lits([…]))` says so, and the engine answers by
scanning the line — a depth-aware walk of integers, the same shape as the
recovery scans — instead of parsing four rules to the same conclusion. It
consumes nothing and decides nothing else: a line that has an `=` is parsed
exactly as before.

The collecting pass never refuses, so a file that fails is still described by
the branches themselves, and the messages are unchanged.

The rule is only sound where the set is a necessary condition for everything
behind it, which is why it is a grammar's statement rather than an engine's
guess.

| Input | Before (ms) | After (ms) |
| --- | ---: | ---: |
| 2,000 expression statements, `check` | 38.41 | 20.62 |
| 2,000 assignments, `check` | 19.32 | 19.29 |

[Allocations](../docs/evidence/line-guard-allocations.json) fall with the
parses that no longer happen: 258,651 → 239,227 on inspect.py, and 255,874 →
218,323 on argparse.py.

[Timing](../docs/evidence/line-guard-timing.json), 21 shuffled samples per
binary (load average 3.3), all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 23.26 | 21.41 | 10.98 | 1.9x |
| typing.py | 23.23 | 21.37 | 10.48 | 2.0x |
| argparse.py | 22.94 | 19.43 | 9.88 | 2.0x |
| _pydecimal.py | 33.39 | 31.22 | 15.66 | 2.0x |
| ast.py | 7.37 | 6.62 | 4.03 | 1.6x |

Twelve of the fifteen medians improve, the code-heavy files by 6.5% to 15.3%.
The three that do not are 3.6 to 5.3 ms files, where startup is most of the
measurement.

## A node's kind is a number too

Every node the parser built copied two strings out of the grammar — its kind
and, where the rule named it, its field. On inspect.py that was 102,032
requests for the kind alone, and it made every reader's test of what a node is
a string comparison.

A node now carries numbers. `compile` gives every distinct spelling in its text
table one number — the first entry that spells it answers for all of them — so
two nodes the grammar spelled the same compare equal without a string being
touched. `tags` resolves the names a language package states (its declarations,
scopes, namespaces, callables, envelopes, and the fields it reads) once per
file, and compares integers from then on.

The table travels with the parse, and how it is stored matters more than it
looks: a `List[String]` is copied string by string at every hand-off, and the
first version of this change cost 1,045 allocations each time a parse passed
from the engine to a reader — five hand-offs, and 0.3 ms of startup a file that
parses in 3 ms cannot afford. `names.almd` stores the table the way the lexer
stores a token stream: the names joined into one byte string, with their bounds
beside them. Copying it is three allocations, and reading a name out of it is
one — paid only where a name is actually printed.

Two things the tree is now careful about. A name the grammar never uses answers
-1, and so does "this child has no name": `child` and `named_child` refuse -1
rather than matching a positional child with it. And the module is imported
under an alias, because a parameter named `names` shadows a module named
`names` — the same resolution hazard that renamed `node` to `node_value` in the
probes earlier in this file.

[Allocations](../docs/evidence/node-kind-ids-allocations.json):

| File | Total allocations before → after | Fewer |
| --- | ---: | ---: |
| inspect.py | 239,227 → 145,486 | 39.2% |
| typing.py | 251,347 → 156,979 | 37.5% |
| argparse.py | 218,323 → 135,961 | 37.7% |
| _pydecimal.py | 377,115 → 220,267 | 41.6% |
| pydoc_data/topics.py | 31,567 → 30,510 | 3.3% |

`text_at` falls from 102,032 requests to none: nothing reads a name out of the
grammar while parsing any more.

[Timing](../docs/evidence/node-kind-ids-timing.json), 21 shuffled samples per
binary, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 21.19 | 18.22 | 10.60 | 1.7x |
| typing.py | 21.07 | 18.39 | 10.40 | 1.8x |
| argparse.py | 18.54 | 16.32 | 9.43 | 1.7x |
| _pydecimal.py | 31.44 | 26.45 | 15.23 | 1.7x |
| dataclasses.py | 12.17 | 10.89 | 7.53 | 1.4x |

The code-heavy files improve by 10.5% to 15.9%. The small ones read 0.3% to
6.3% slower in this run, which was taken at load average 6.75; measured on its
own, against the same binary and interleaved, startup is 3.42 ms before and
3.43 ms after.

The complexity baseline records three changes, all of them falls or a new file:
`parser.almd` 74 → 65, where the terminal, recovery and ladder arms moved out
of the dispatch; `layout.almd` 28 → 27; and `names.almd` at 7.

## What a rule answers is two words

A rule returned `Out { ok, pos, st }`, where `st` was `State { far, collect,
recover, build }`: six words, written to memory at every call because nothing
that large comes back in registers. Of those six, three are flags that never
change while a pass runs, and `far` is read only by the pass that collects
expectations.

So the flags are now one scalar argument — a mode the caller fixes before the
first rule is entered — and `far` is a one-place list the collecting pass
writes. What comes back from a rule is whether it matched and where it
stopped, and nothing else.

[Allocations](../docs/evidence/parser-state-allocations.json) move by one
request (the cell). [Timing](../docs/evidence/parser-state-timing.json), 21
shuffled samples per binary, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 18.67 | 17.96 | 10.99 | 1.6x |
| typing.py | 19.16 | 18.67 | 10.98 | 1.7x |
| argparse.py | 17.10 | 16.65 | 10.23 | 1.6x |
| _pydecimal.py | 26.89 | 26.43 | 15.96 | 1.7x |
| dataclasses.py | 11.25 | 10.98 | 8.14 | 1.3x |

Eleven of the fifteen medians improve, the code-heavy files by 1.4% to 3.8%.
Messages are unchanged: the collecting pass computes the same farthest
position and the same expectation set, and `check` prints what it printed.

## A token's two numbers side by side

The engine numbered a token stream into two arrays — the kinds in one, the
literal spellings in the other — and carried both into every rule. The two
were always read at the same position, a cache line apart, and they were two of
the nine arguments a rule takes, which is one more than the registers hold.

They are one array now, a token's kind at `2i` and its spelling number at
`2i + 1`.

[Timing](../docs/evidence/interleaved-numbering-timing.json), 21 shuffled
samples per binary, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 18.17 | 17.32 | 11.03 | 1.6x |
| typing.py | 18.57 | 18.00 | 10.95 | 1.6x |
| argparse.py | 16.75 | 16.13 | 10.31 | 1.6x |
| _pydecimal.py | 26.47 | 25.27 | 16.31 | 1.5x |
| dataclasses.py | 11.38 | 10.81 | 8.32 | 1.3x |

Thirteen of the fifteen medians improve, the code-heavy files by 1.5% to 5.0%.

## A rule that only stands in front of another says nothing

`x = 1` parsed to `(assign (identifier) (conditional (comparison (power
(primary (number))))))`. Four of those seven nodes exist because Python's
expression grammar is a ladder and each rung wraps what it matched, whether or
not it matched anything of its own. inspect.py's tree held 29,427 nodes.

`nest(kind, rule)` is `wrap` that keeps quiet when the rule left exactly one
node behind. The four rungs — `conditional`, `comparison`, `power`, `primary`,
and the two pattern rules that share the last one — use it, and the same file's
tree is 16,652 nodes. `x = 1` is now `(assign (identifier) (number))`.

Nothing a reader asks for changes. `outline`, `symbols`, `tags` and `check` are
byte-identical on six stdlib files, the CPython expression oracle matches the
same 2,993 trees with the same digest, and the statement oracle matches the
same 857 — because a node with one child and a name that only says which rule
ran is exactly what those oracles already looked through. `gramide parse` does
change, and for the better: the s-expression is now the shape of the code.

[Allocations](../docs/evidence/transparent-wraps-allocations.json):

| File | Total allocations before → after | Fewer |
| --- | ---: | ---: |
| inspect.py | 145,487 → 90,731 | 37.6% |
| typing.py | 156,980 → 100,067 | 36.3% |
| argparse.py | 135,962 → 88,560 | 34.9% |
| _pydecimal.py | 220,268 → 136,045 | 38.2% |

[Timing](../docs/evidence/transparent-wraps-timing.json), 21 shuffled samples
per binary, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 17.44 | 15.25 | 10.91 | 1.4x |
| typing.py | 16.96 | 15.27 | 10.54 | 1.4x |
| argparse.py | 15.16 | 13.91 | 9.69 | 1.4x |
| _pydecimal.py | 24.13 | 21.39 | 15.46 | 1.4x |
| dataclasses.py | 10.12 | 9.18 | 7.58 | 1.2x |

Thirteen of the fifteen medians improve, the code-heavy files by 7.1% to 12.6%.

## Two cuts to what the engine walks

A visit costs about ten nanoseconds and inspect.py took 788,325 of them — 46
per token. Two changes take that to 577,266, and the count is the measure here
because it is exact where a median on a shared machine is not.

**A wrap over a sequence is one node, not two.** Nearly every rule that names
something is `wrap(kind, seq([…]))`, and the engine visited the wrap, which
called the sequence, which did the work. `compile` now fuses the pair: the
fused op carries the child run itself and the arm walks it where it stands.
That is 112,412 visits on inspect.py, and it has to be taught to the head
table, which reads a sequence's first child — the first version of this change
forgot to, the table went blank, and the parse got *slower* by a third.

**A rule begins with a set of terminals, not one.** The head table held one
terminal per rule, which meant a branch beginning with an alternation could not
be skipped. It now holds a run: an alternation's set is the union of its
branches', and a set that cannot be known, or grows past 48, is empty, which
means "walk in and see". `strings` is the case that pays: every atom in a
Python file tried it and failed, 14,364 times in inspect.py, because its head
was three token kinds and not one.

Neither changes what the engine accepts. `outline`, `parse`, `symbols`, `tags`
and `check` are byte-identical on five stdlib files, and the diagnostics are
the same diagnostics: the collecting pass still walks every branch.

[Timing](../docs/evidence/visit-cuts-timing.json), 21 shuffled samples per
binary, all 945 timed outputs matching CPython:

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 15.47 | 14.25 | 10.96 | 1.3x |
| typing.py | 15.64 | 14.77 | 10.89 | 1.4x |
| argparse.py | 14.40 | 13.38 | 10.12 | 1.3x |
| _pydecimal.py | 22.20 | 20.74 | 15.97 | 1.3x |
| ast.py | 5.98 | 5.63 | 4.26 | 1.3x |

The code-heavy files improve by 4.7% to 7.8% — less than the 27% of visits
removed, which says the engine's remaining time is not in the visits it makes
but in what each one touches.

## The binary the benchmark was timing

`almide build` compiles the generated Rust into `target/debug`. `almide install`
— how anyone actually gets this program — builds `--release`. Every number
above was therefore a debug build of gramide against a `cc -O2` tree-sitter,
and the comparison was never the one it claimed to be.

Building it the way it ships is worth more than any single change in this file:

| File | Debug (ms) | Release (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 13.47 | 12.24 | 10.23 | 1.20x |
| typing.py | 13.83 | 12.62 | 10.05 | 1.26x |
| argparse.py | 12.59 | 11.46 | 9.19 | 1.25x |
| _pydecimal.py | 19.47 | 17.44 | 15.06 | 1.16x |
| dataclasses.py | 8.45 | 7.87 | 7.30 | 1.08x |
| pydoc_data/topics.py | 5.26 | 4.81 | 5.06 | **0.95x** |

[The full run](../docs/evidence/release-build-timing.json) is 21 shuffled
samples per binary across all 15 files; every timed output matches CPython, and
the [stdlib survey](../docs/evidence/release-build-stdlib.json) is unchanged at
721 of 721 against tree-sitter's 720.

topics.py is the first file gramide reads faster than tree-sitter does. It is a
string-heavy file and not the case the engine is judged on, but it is a real
one, and the code-heavy files are now within 20 to 26 per cent rather than 30
to 40.

`ci/check.sh` builds `--release` from here on, so what the tests check and what
the benchmark times is what `almide install` produces. It costs the CI job
about ten seconds.

## Two questions the engine stopped scanning for

A release profile of the parse loop put 20 per cent of it in `may_start` and
another 4 in hashing. Neither was doing anything a parser has to do.

**Can this token begin this rule?** The head table held a run of terminal nodes
per rule, and answering meant fetching each node and, for a literal set,
scanning its spellings — up to 48 nodes and a nested loop, at every alternative
branch, every option and every repetition. The runs are now turned once, at the
end of `compile`, into what the question actually needs: a bitmask of the token
kinds a rule can begin with, a 64-bit sketch of its spellings, and the
spellings themselves. A rule with no known head answers -1 for its kinds, so
the first test already says yes. The answer is exactly the answer it was —
the sketch only decides whether the exact list is worth reading — and
`may_start` falls from 20 per cent of the profile to 1.2.

**Which spelling is this token?** `atom_at` reached two `Map` lookups per token,
keyed by a first byte and a width and by an atom number. Both key spaces are
dense and small — 256 bytes by 17 widths, and one slot per spelling — so both
are now plain arrays read by index, and the SipHash that numbered every token
in the file is gone. Filling a 4,352-slot table needed care: `list.set` on this
backend copies the whole list, so the table is built by appending — the chain
looks backward for the last spelling in its slot, and the heads come off one
sorted pass.

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 12.51 | 11.76 | 10.44 | 1.13x |
| typing.py | 13.30 | 12.50 | 10.72 | 1.17x |
| argparse.py | 11.80 | 11.41 | 9.90 | 1.15x |
| _pydecimal.py | 18.35 | 17.04 | 15.58 | 1.09x |
| dataclasses.py | 8.30 | 8.09 | 7.97 | 1.02x |
| pydoc_data/topics.py | 5.22 | 5.18 | 5.35 | 0.97x |

[Timing](../docs/evidence/head-index-timing.json), 21 shuffled samples per
binary; [stdlib](../docs/evidence/head-index-stdlib.json) unchanged at 721 of
721. `outline`, `parse`, `symbols`, `tags` and `check` are byte-identical on
stdlib files and on malformed ones, diagnostics included.
[Allocations](../docs/evidence/head-index-allocations.json) barely move —
90,789 against 90,767 on inspect.py, the new tables — which is the point: this
change is about what the engine reads, not what it allocates.

## A list literal in a hot loop is an allocation

`list.contains([114, 98, 117], a)` builds a three-element list, asks it one
question and throws it away. The lexer did that on every string prefix, every
number suffix, every bracket inside an interpolation and every byte of a failed
literal's tail — 13,321 allocations on inspect.py, 22,002 on _pydecimal.py, all
of them to compare a byte against three constants. They are comparisons now.

| File | Allocations before | after |
| --- | ---: | ---: |
| inspect.py | 90,789 | 77,468 |
| typing.py | 100,125 | 86,406 |
| argparse.py | 88,618 | 76,267 |
| _pydecimal.py | 136,103 | 114,101 |

[The profile](../docs/evidence/no-literal-lists-allocations.json) is 15 per cent
fewer allocations and [the timing](../docs/evidence/no-literal-lists-timing.json)
does not move: 11.72 ms against 11.76 on inspect.py, inside the noise of 21
samples. That is the finding, not a disappointment — the allocator was not what
the remaining time was going into, and the 25,014 requests `take_from` makes for
node children are worth more than the 13,321 removed here. The change stands
because it is strictly less work for the same answer, not because it moved a
median.

## A leaf is not a visit, and the ladder was in the wrong order

`("name", seq([nott(lits(HARD_KEYWORDS)), tok("identifier")]))` is how a Python
grammar says an identifier is not a keyword, and the engine spent four visits on
it — the sequence, the negation, the keyword set, the token. It is the most
common rule in the language: 118,214 visits on inspect.py, a fifth of every
visit the file costs, to decide something a single pass over two integers
decides.

`compile` now folds both shapes. A negation of a terminal becomes one op, and a
sequence whose every member is a terminal test — negated or not — becomes one op
that runs them where it stands. Visits fall from 577,266 to **472,089**, and
failed visits from 167,600 to 115,979.

Then the dispatch. `parse_rule` is an if-ladder, and every visit pays for the
kinds it walks past. Counting what actually arrives says the order was wrong:
alternation is 26 per cent of visits and was second, the fused wrap-sequences
are 21 per cent and were eleventh, option and repetition are another 17 and were
twelfth and thirteenth. The ladder is now in the order the visits arrive, and
everything under one per cent moved into `uncommon_here` behind it. That second
part is worth as much as the first — and it takes `parse_rule`, the worst
function in this repository, from 65 to 35 on the complexity ratchet.

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 11.67 | 11.19 | 10.41 | 1.07x |
| typing.py | 12.01 | 11.45 | 10.29 | 1.11x |
| argparse.py | 10.80 | 10.39 | 9.28 | 1.12x |
| _pydecimal.py | 16.48 | 15.46 | 15.15 | 1.02x |
| dataclasses.py | 7.57 | 7.28 | 7.38 | **0.99x** |
| pydoc_data/topics.py | 4.90 | 4.94 | 5.17 | **0.96x** |

Two of the fifteen files are now read faster than tree-sitter reads them, and
_pydecimal.py — 220 KB of code — is within two per cent.
[Timing](../docs/evidence/leaf-ops-timing.json), 21 shuffled samples per binary;
[stdlib](../docs/evidence/leaf-ops-stdlib.json) unchanged at 721 of 721;
[allocations](../docs/evidence/leaf-ops-allocations.json) unchanged, which is
expected — no node is built or skipped that was not before, and `outline`,
`parse`, `symbols`, `tags` and `check` are byte-identical, diagnostics included.

## The set that says an identifier is not a keyword

With the terminal tests folded, the profile's second-hottest function was
`literal_here` at 14 per cent, and the reason is one set. `lits(HARD_KEYWORDS)`
has 35 members, `spelled` walks it looking for the token's spelling number, and
an ordinary identifier is spelled none of them — so every name in the file
walked all 35 and found nothing. Worse, a token no terminal spells carries -1,
which the walk compared against 35 numbers that are all non-negative.

Every literal set now carries a 64-bit sketch of the spellings in it, built
beside the ops in `compile`. A -1 fails without a comparison, a number outside
the sketch fails in a shift and a test, and only a possible hit walks the set —
where the answer is still the exact answer the walk gave.

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 11.16 | 10.68 | 10.44 | 1.02x |
| typing.py | 11.50 | 10.90 | 10.08 | 1.08x |
| argparse.py | 10.45 | 10.06 | 9.41 | 1.07x |
| _pydecimal.py | 15.51 | 14.54 | 15.04 | **0.97x** |
| dataclasses.py | 7.38 | 7.04 | 7.52 | **0.94x** |
| pydoc_data/topics.py | 4.82 | 4.83 | 5.17 | **0.94x** |

Three of the fifteen files are now read faster than tree-sitter reads them,
including _pydecimal.py, which at 220 KB is the largest and the one this
benchmark exists for. inspect.py is within two per cent.

[Timing](../docs/evidence/literal-mask-timing.json), 21 shuffled samples per
binary; [stdlib](../docs/evidence/literal-mask-stdlib.json) unchanged at 721 of
721; [allocations](../docs/evidence/literal-mask-allocations.json) unchanged.
The engine walks exactly what it walked before — the visit count is the same
472,089 — and `outline`, `parse`, `symbols`, `tags` and `check` are
byte-identical, diagnostics included.

## Forty-seven calls to decide that a comma is a comma

The lexer held its operators as a list of byte patterns and, at every character
no earlier branch claimed, walked all 47 of them — `matches(buffer, i, op.data)`
each time, and the loop did not even stop at the first hit. It was 10 per cent
of the profile, second only to `parse_rule`.

Each operator is now one integer — its bytes and its width — and the table is
grouped by first byte. A comma reads one entry. `**=` reads four, because four
operators begin with `*`, and they are still in longest-first order, so the
first that matches is still the longest.

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| inspect.py | 10.78 | 10.37 | 10.53 | **0.98x** |
| typing.py | 11.03 | 10.51 | 10.09 | 1.04x |
| argparse.py | 10.03 | 9.44 | 9.18 | 1.03x |
| _pydecimal.py | 14.58 | 14.09 | 14.93 | **0.94x** |
| dataclasses.py | 6.93 | 7.03 | 7.36 | **0.96x** |
| pydoc_data/topics.py | 5.05 | 5.02 | 5.33 | **0.94x** |

**inspect.py is read faster than tree-sitter reads it.** It is the file this
benchmark was built around — issue #37's example, 127 KB and 16,963 tokens — and
at the start of this file's history it took 48.98 ms against tree-sitter's 10.5.
Four of the fifteen files now win, and the token stream is byte-identical:
`tokens`, `outline`, `parse`, `symbols`, `tags` and `check` all are.

[Timing](../docs/evidence/operator-index-timing.json), 21 shuffled samples per
binary; [stdlib](../docs/evidence/operator-index-stdlib.json) unchanged at 721
of 721 against tree-sitter's 720.
||||||| parent of 04f601b (perf: write each grammar's compiled arena down instead of rebuilding it per run)
## The grammar is compiled once, not once per run

Every run of gramide built the Python grammar's rule tree and compiled it into
the engine's arena before opening the file: 0.18 ms to build the value, 0.63 ms
to compile it, measured in a fresh process and measured again on the second and
sixth compile in one process — it is work, not a cold start. On a 4 KB file
that was a quarter of the whole run.

The arena is a pile of integers and a list of names, so it can be written down.
`scripts/gen_grammar_tables.py` compiles each package's grammar once and writes
`src/packages/tables/<id>.almd`; `--check` regenerates and fails if what is
committed is no longer what the grammar compiles to, and `ci/check.sh` runs it.
The grammar value in `src/packages` is still the source of truth and still the
only thing anyone edits. This is what tree-sitter has always done — `grammar.js`
becomes `parser.c` — and there was never a reason for the arena to be rebuilt
17,000 times a day.

| File | Before (ms) | After (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: | ---: |
| keyword.py | 3.47 | 2.70 | 2.30 | 1.17x |
| genericpath.py | 3.62 | 2.77 | 2.54 | 1.09x |
| textwrap.py | 3.92 | 3.24 | 3.00 | 1.08x |
| ast.py | 4.59 | 3.84 | 3.71 | 1.03x |
| tokenize.py | 4.60 | 3.84 | 3.72 | 1.03x |
| pydoc_data/topics.py | 4.65 | 4.05 | 4.84 | **0.84x** |
| dataclasses.py | 6.85 | 6.08 | 7.19 | **0.85x** |
| argparse.py | 9.54 | 8.81 | 9.05 | **0.97x** |
| inspect.py | 10.48 | 9.67 | 10.28 | **0.94x** |
| typing.py | 10.52 | 9.80 | 9.81 | **1.00x** |
| _pydecimal.py | 14.36 | 13.56 | 14.69 | **0.92x** |

Every file is 0.7 to 0.85 ms faster, which is the whole of what compiling the
grammar cost. **Six of the fifteen are now read faster than tree-sitter reads
them, and they are the six largest.** What is left are the small files, where
the difference is no longer anything gramide does — it is the 0.4 ms more its
binary takes to load.

It costs build time: `almide build --release` goes from about 10 s to about
36 s, because 300 KB of integer literals is 300 KB of integer literals. A
parser generator paying that once per build to save 0.8 ms per run is the right
side of the trade.

[Timing](../docs/evidence/grammar-tables-timing.json), 21 shuffled samples per
binary; [stdlib](../docs/evidence/grammar-tables-stdlib.json) unchanged at 721
of 721. `outline`, `parse`, `symbols`, `tags`, `check` and `tokens` are
byte-identical, diagnostics included — the table is the same arena, so it had
better be.

## One copy of the names

`Compiled` carried the grammar's names twice: as `texts`, a list of 1,675
strings, and as `names`, the same strings end to end in one blob with their
bounds beside them. The blob is what every reader uses; `texts` was read by one
function, the one that builds an error message.

The table now ships the blob and nothing else — the bounds are one scan of it,
which is how they were derived in the first place — and `Compiled` is one field
shorter. That is 3,117 allocations per run on any file, because 1,675 string
literals are 1,675 allocations before they are joined and thrown away:

| File | Before | After |
| --- | ---: | ---: |
| inspect.py | 57,013 | 53,896 |
| typing.py | 65,951 | 62,834 |
| _pydecimal.py | 93,646 | 90,529 |
| pydoc_data/topics.py | 6,373 | 3,256 |

Timing is unchanged within the noise of 21 samples on the large files and about
0.1 ms better on the small ones, where 3,117 allocations are a larger share of
the run. The [board](../docs/evidence/one-name-table-timing.json) as it now
stands, against tree-sitter:

| File | gramide (ms) | tree-sitter (ms) | ratio |
| --- | ---: | ---: | ---: |
| pydoc_data/topics.py | 3.96 | 4.83 | **0.82x** |
| dataclasses.py | 5.93 | 7.07 | **0.84x** |
| _pydecimal.py | 12.96 | 14.58 | **0.89x** |
| inspect.py | 9.07 | 9.92 | **0.91x** |
| argparse.py | 8.32 | 8.87 | **0.94x** |
| typing.py | 9.39 | 9.85 | **0.95x** |
| ast.py | 3.72 | 3.71 | 1.00x |
| tokenize.py | 3.754 | 3.756 | 1.00x |
| reprlib.py | 3.09 | 2.86 | 1.08x |
| textwrap.py | 3.28 | 3.05 | 1.08x |
| genericpath.py | 2.73 | 2.48 | 1.10x |
| keyword.py | 2.81 | 2.50 | 1.12x |
| token.py | 2.66 | 2.38 | 1.12x |
| copyreg.py | 3.29 | 2.82 | 1.17x |
| stat.py | 3.03 | 2.54 | 1.19x |

Six of fifteen are faster, two are level, and the seven that are not are the
seven smallest — under 4 ms, where what separates them is no longer parsing.
gramide's binary takes about 0.2 ms longer to load than tree-sitter's, and a
2.5 ms run cannot hide that.

## A line is a write

Rust's stdout is a `LineWriter`: it flushes at every newline, whether or not
stdout is a terminal. Every command here printed its answer a line at a time, so
every line of every answer was a `write(2)`. `tokens` on `inspect.py` made
18,966 of them to say 19,346 lines; `outline` on `typing.py` made 253.

The lines are already a list when the command prints them. Joining them costs
one pass over bytes the command has just built, and the answer leaves in one
call. [`bench/count_writes.py`](count_writes.py) counts them exactly — a dyld
interposer on `write`, in the shape of the allocation profiler, and a
deterministic number rather than a timing:

| Command | File | Lines | Writes before | Writes after |
| --- | --- | ---: | ---: | ---: |
| `tokens` | _pydecimal.py | 31,212 | 29,455 | 2 |
| `tokens` | inspect.py | 19,346 | 18,966 | 2 |
| `tokens` | typing.py | 19,216 | 18,251 | 2 |
| `tokens` | ast.py | 4,268 | 4,143 | 2 |
| `outline` | _pydecimal.py | 258 | 258 | 2 |
| `outline` | typing.py | 253 | 253 | 2 |
| `outline` | inspect.py | 162 | 162 | 2 |

(Two, not one: the joined answer is larger than the `LineWriter`'s buffer, so it
goes straight out, and its closing newline follows.)

For `tokens` that is most of the command. Twenty-one shuffled samples per
binary, fresh process each, output required byte-identical
([evidence](../docs/evidence/one-write-tokens-timing.json)):

| File | Before (ms) | After (ms) | |
| --- | ---: | ---: | ---: |
| _pydecimal.py | 19.71 | 9.22 | **0.47x** |
| inspect.py | 13.59 | 6.77 | **0.50x** |
| typing.py | 13.68 | 6.79 | **0.50x** |
| ast.py | 4.93 | 3.32 | **0.67x** |
| stat.py | 3.37 | 2.84 | **0.84x** |

`outline` answers in tens to hundreds of lines, so the same change is worth
about 0.3 µs a line there — under the noise of 21 samples on this machine, and
claimed only as the write count above. The
[outline board](../docs/evidence/one-write-timing.json) is where it was.
`tags` answers at greater length, and the change is visible there
([evidence](../docs/evidence/one-write-tags-timing.json)): 1,818 lines for
`src/parser.almd`, 10.23 ms to say them and now 9.55; 1,293 lines for
`src/packages/gramide_rust.almd`, 6.52 ms and now 5.96.

It costs the answer's own size in memory while it is assembled: peak RSS for
`tokens` on `_pydecimal.py`, a 602 KB answer, goes from 6.11 MB to 6.34 MB.

`check` still prints a line at a time. Its answers interleave with the
diagnostics on stderr, and that order is part of the output.

[Correctness](../docs/evidence/one-write-stdlib.json) is unchanged: 721 of 721
stdlib outlines match CPython, against tree-sitter's 720, and `outline`,
`tokens`, `tags` and `parse` are byte-identical to the previous binary.

## What a run costs before the parser sees a byte

The seven smallest files on the board lose by less than half a millisecond, and
the note under them said gramide's binary takes about 0.2 ms longer to load.
That was a guess about a mechanism, and it was wrong.

[`bench/startup_floor.py`](startup_floor.py) builds controls that differ in one
thing at a time and reports the minimum of 151 shuffled runs each, because a
floor is what a startup cost is and the median only adds this machine's load:

| | ms over `/usr/bin/true` | |
| --- | ---: | --- |
| C, 33 KB, one `puts` | +0.116 | |
| the same C binary padded past 400 KB | +0.135 | mach-o size is not a startup cost |
| Rust, `write(2)` only, no `std::rt::init` | +0.106 | Rust itself is free |
| Rust, ordinary `main`, one `println!` | +0.350 | **+0.244** for the std runtime |
| Almide, one `println` | +0.337 | the same, to within this measurement |
| gramide, no arguments | +0.380 | +0.043 for its own 2.4 MB |
| gramide, a one-line file | +0.555 | +0.175 of its own work |
| tree-sitter, the same one-line file | +0.237 | +0.121 of its own work |

So the gap on a file with nothing in it is 0.32 ms, and 0.24 of it is the Rust
standard library starting up: `std::rt::init`, and the first `println!` building
the `Stdout` it flushes through. It is not the binary's size — 400 KB of padding
costs a C binary nothing — and it is not Almide, which is level with Rust to
within the noise here. It is what every binary the compiler emits pays before
`main` runs, and it is out of gramide's reach from Almide source.

The files that still lose are 1 KB to 25 KB and finish in about 4 ms or less.
Their gaps run from 0.17 ms to 0.51 ms, and 0.32 ms of every one of them is
already there before either program has read a byte. For six of the eight the
gap is smaller than that: gramide reads those files faster than tree-sitter
does and still loses, because it started later. It starts later on the files it
wins, too.
