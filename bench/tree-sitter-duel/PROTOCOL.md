# Gramide / Tree-sitter comparison protocol

Final protocol prepared after diagnostic runs and frozen before final timing,
2026-10-05. Earlier protocol hashes remain in the diagnostic evidence. The comparison covers JSON,
TypeScript and Java. It is not a claim of complete syntax/AST parity.

## Correctness before timing

- Every fixture is frozen by SHA-256 and provenance before either parser runs.
- All real files remain in the acceptance denominator. A rejection or symbol
  mismatch cannot be silently removed; both it and the reason remain in results.
- Gramide uses its production scanner plus `parser.parse_with` (a FULL tree),
  never tree-free `check`. Tree-sitter uses `ts_parser_parse_string` with no old
  tree for each whole parse. Their AST layouts are different.
- JSON validity is independently checked using Python's standard parser with
  nonfinite constants rejected. Tree-sitter JSON is intentionally permissive
  (comments/multiple values etc.); invalid acceptance is reported separately.
- Java is a documented core reader, not a complete syntax validator. Broader
  Java files/probes stay visible even when unsupported. Strict reader acceptance
  is not javac semantic validation.
- The matched declaration task outputs ONLY lexical names, normalized kinds,
  and exact declaration-core UTF-8 byte spans: JSON pairs; Java named types,
  methods and constructors; TypeScript functions, named types, methods, and type
  aliases. It is not the full production symbols API. Both adapters emit the
  identical JSON-array schema and include traversal/serialization for this task.
- Symbol timings require exact canonical records, not just declaration counts.
  Language-specific kind spelling mappings are explicit in both adapters.
  For TypeScript both adapters omit optional `declare` and trailing semicolon
  separators from declaration-core ranges; all other range differences remain
  mismatches. No function bodies or declaration contents are truncated.

## Measurement scopes

1. Fresh-process full parse: process startup, file read, language setup,
   tokenization, FULL tree creation and disposal. Input file cache is warmed;
   this is cold process startup, NOT cold disk I/O.
2. Warm in-process full parse: source and parser/language setup are outside the
   timer. Every iteration parses from scratch without old-tree reuse and drops
   the tree inside the timer. The Gramide API currently copies its input String/path per call;
   that cost is retained and disclosed, while Tree-sitter borrows its buffer.
   One untimed warmup precedes raw samples; five separately launched balanced
   warm batches distinguish process replicates from within-process samples.
3. Matched declaration read: same fresh-process scope plus equal-schema selected
   declaration extraction/serialization, only after exact-output gates pass.
4. Incremental parse-update kernel: replay identical explicit TSV edits. Source
   edits and position calculation are outside the timer on BOTH sides. Tree
   update, reparse, fallback and disposal are included. Whole-tree output
   materialization is not in this kernel metric. Token-preserving, valid
   structural and temporary-broken edits are reported separately.
5. Peak RSS: separate isolated native `fork` / `exec` / `wait4` runs, never mixed into timing samples (Linux ru_maxrss, converted from KiB).
   The launcher is C, avoiding Python’s inherited RSS floor. This is whole-process peak resident memory, NOT only parser-owned allocations.

Correctness and timing runs are separate. Every incremental step is compared
with a fresh parse from that engine in correctness mode, with exact positions;
final replayed source bytes must agree. Every mismatch fails the gate. Temporary
invalid intermediates may have different recovery trees across engines and are
not asserted equivalent merely because each engine is internally consistent.

## Execution controls

- Same hardware and CPU affinity, single-thread adapters, serial execution.
- No concurrent model timing or compiler workloads; coordinate the CPU/RAM slot.
- Release Gramide (Almide --release; generated Cargo release profile captured,
  currently opt-level 3 + LTO + one codegen unit); C reference -O3 -flto=1
  -DNDEBUG. Neither requests host-specific CPU instructions.
  Exact commands, compilers, references and binary hashes accompany results.
- Randomized balanced engine order with a fixed seed; retain all raw samples.
  Report medians and tail percentiles, not cherry-picked minima.
- Baseline binary is preserved. Optimization must keep correctness and broad
  coverage, and be evaluated on designated held-out fixtures as well.
- A bounded task/workload win is not universal Tree-sitter superiority.

## Supplemental strict JSON probes

`json_conformance.py` supplies 32 original fixed syntax probes, separate from the
70-file frozen performance/coverage corpus. It compares full parse acceptance
with Python's nonfinite-rejecting JSON oracle, exposing the permissive behavior
of Tree-sitter JSON without changing its grammar or counting rejection as speed.
Java25-only probes cannot be independently validated by the available Java21
parse oracle and are reported as oracle-unavailable, not invalid Java.

The first edit streams use development inputs only. They are not a held-out
editor benchmark; held-out claims apply only to the full-parse/declaration set.
Valid and token-preserving streams must remain strict-parse accepted at EVERY
step on both engines before timing them. Temporary-broken streams are separate.
