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
