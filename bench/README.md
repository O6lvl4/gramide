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
