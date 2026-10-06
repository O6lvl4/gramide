# Recorded comparison: 2026-10-05

This is a correctness-gated workload result, not a claim of complete language or tree parity. All selected real files remain in the denominator. The next optimization target is the structural/recovery, cold-process and memory losses shown below.

Final timing ran serially on CPU 0, AMD EPYC 9V74, Linux x86-64, 2026-10-05 15:27–15:29 UTC. No concurrent model/compiler jobs. The reference is official Tree-sitter v0.27.0 with the exact grammars in `references.lock.json`. Candidate source pins are in `source-pins.json`; all raw samples and original build provenance are in `evidence/*.json.gz`.

## Quality gates

- 70 frozen files: 25 real, 3 generated scaling, 29 coverage probes, 13 malformed. One optional TSX probe is explicitly untested by the TypeScript-only adapter
- All 25 real files are accepted by both engines and exactly match the selected declaration names, kinds, UTF-8 ranges and derived line ranges
- Across all categories: 45 parse-eligible and 44 exact-symbol-equal cases. The matrix below retains unsupported, invalid, unknown-oracle and mismatch cases
- Java remains a core reader, not complete javac validation. A Java 25 probe lacks an appropriate independent oracle on this Java 21 host
- The separate 32-case strict JSON gate matches the Python oracle for Gramide. Official Tree-sitter JSON accepts 13 oracle-invalid inputs by design; it would need extra strict-validation checks. These are not timed as competitive successes
- Every incremental step is checked against a fresh parse from that engine, including positions. The edit harness additionally checks Gramide node IDs; separate regression tests assert fallback immutability. Valid streams must remain strict-valid at every step. Recovery trees across engines are not asserted equivalent

## Real-file aggregate

Ratios are Tree-sitter median / Gramide median; greater than 1 favors Gramide. Aggregates are geometric means of per-file ratios, not throughput weighted by file size. Warm: 5 process batches × 31 full-tree iterations after warmup. Cold: 11 balanced randomized paired fresh-process samples with warm filesystem cache.

| Task | Language | Geomean ratio | Gramide wins | Per-file range |
|---|---|---:|---:|---:|
| Warm full parse | json | 4.391× | 9/9 | 3.623–5.812× |
| Warm full parse | typescript | 1.912× | 8/8 | 1.373–2.275× |
| Warm full parse | java | 1.809× | 8/8 | 1.530–2.467× |
| Cold process full parse | json | 1.280× | 5/9 | 0.922–2.754× |
| Cold process full parse | typescript | 1.117× | 4/8 | 0.845–1.866× |
| Cold process full parse | java | 1.007× | 2/8 | 0.878–1.343× |
| Cold selected symbols | json | 1.479× | 7/9 | 0.957–2.158× |
| Cold selected symbols | typescript | 1.305× | 6/8 | 0.853–2.065× |
| Cold selected symbols | java | 1.181× | 4/8 | 0.867–1.803× |

Warm full parse wins on all 25 selected real files. Cold results are mixed. These adapters construct different full-tree representations; equal selected-symbol output does not prove full AST/CST equivalence. Gramide source/path copying remains inside its full-parse timer. Declaration serialization uses the same schema but different implementations.

## Incremental update kernel

Fixed development-file streams only, not a held-out editing study. Token-preserving edits modify long ASCII words in identifiers/strings/comments. The timer includes tree update, reparse, fallback and disposal, but excludes source application, point calculation and output materialization on both sides. Five replay runs per eligible stream.

| Language | Stream | Gramide median µs | Tree-sitter median µs | TS/G ratio | Gate |
|---|---|---:|---:|---:|---|
| java | token_preserving | 6.415 | 56.609 | 8.8246× | pass |
| java | valid_structural | 2690.407 | 9.585 | 0.0036× | pass |
| java | temporary_broken | 6011.840 | 34.652 | 0.0058× | pass |
| typescript | token_preserving | 7.641 | 26.756 | 3.5013× | pass |
| typescript | valid_structural | 86.089 | 12.444 | 0.1445× | pass |
| typescript | temporary_broken | 8454.851 | 23.616 | 0.0028× | pass |
| json | token_preserving | 19.239 | 86.120 | 4.4763× | pass |
| json | valid_structural | 15860.657 | 79.695 | 0.0050× | pass |
| json | temporary_broken | — | — | — | Gramide recovery unsupported; no speed claim |

Structural edits and malformed intermediates remain substantial losses, and one JSON recovery stream fails. Token-preserving wins cannot stand in for all editor operations.

## Every real file: timing and memory

Peak RSS uses three separate native fork/exec/wait4 runs per engine; below are median peaks in MiB. The launcher `/bin/true` control was 0.375 MiB. This measures whole processes, not parser-owned allocation. The earlier Python-launcher RSS experiment had an inherited floor and is not used. Memory generally favors Tree-sitter. Incremental RSS was not measured.

| File | Split | Warm TS/G | Cold TS/G | Symbols TS/G | RSS G MiB | RSS TS MiB |
|---|---|---:|---:|---:|---:|---:|
| java/real/JsonNull.java | development | 1.634× | 0.908× | 0.903× | 1.926 | 1.145 |
| java/real/Strictness.java | heldout | 2.263× | 0.878× | 0.911× | 1.867 | 1.016 |
| java/real/ExclusionStrategy.java | development | 2.467× | 0.922× | 0.867× | 1.926 | 1.062 |
| java/real/JsonParser.java | heldout | 1.530× | 0.937× | 0.971× | 1.926 | 1.129 |
| java/real/JsonElement.java | development | 1.826× | 0.972× | 1.803× | 1.926 | 1.129 |
| java/real/JsonPrimitive.java | heldout | 1.630× | 0.994× | 1.573× | 2.051 | 1.273 |
| java/real/LinkedTreeMap.java | development | 1.627× | 1.181× | 1.332× | 2.289 | 1.523 |
| java/real/JsonReader.java | heldout | 1.694× | 1.343× | 1.444× | 2.676 | 2.129 |
| typescript/real/corePublic.ts | development | 2.014× | 0.866× | 0.881× | 2.488 | 1.922 |
| typescript/real/performance.ts | heldout | 1.601× | 0.980× | 1.068× | 2.426 | 2.230 |
| typescript/real/watchUtilities.ts | development | 2.087× | 1.096× | 1.505× | 2.680 | 2.793 |
| typescript/real/core.ts | heldout | 2.024× | 1.696× | 1.831× | 4.180 | 4.609 |
| typescript/real/lib__lib.es2015.symbol.d.ts | development | 1.373× | 0.889× | 0.853× | 2.488 | 1.727 |
| typescript/real/lib__lib.es2021.promise.d.ts | heldout | 1.987× | 0.845× | 1.593× | 2.488 | 1.719 |
| typescript/real/lib__lib.es2015.iterable.d.ts | development | 2.114× | 1.095× | 1.157× | 2.613 | 2.176 |
| typescript/real/lib__lib.es5.d.ts | heldout | 2.275× | 1.866× | 2.065× | 4.102 | 4.414 |
| json/real/tree-sitter-json__tree-sitter.json | development | 4.270× | 0.947× | 1.839× | 1.613 | 0.750 |
| json/real/tree-sitter-json__package.json | heldout | 4.972× | 0.922× | 0.958× | 1.676 | 0.750 |
| json/real/tree-sitter-json__src__node-types.json | development | 3.623× | 0.954× | 0.957× | 1.766 | 0.750 |
| json/real/tree-sitter-json__src__grammar.json | heldout | 4.369× | 1.112× | 1.105× | 1.914 | 0.875 |
| json/real/tree-sitter-java__src__node-types.json | development | 3.866× | 1.649× | 1.724× | 2.926 | 2.125 |
| json/real/tree-sitter-typescript__typescript__src__grammar.json | heldout | 3.981× | 2.754× | 2.158× | 4.859 | 4.625 |
| json/real/package.json | development | 5.165× | 0.976× | 2.047× | 1.613 | 0.750 |
| json/real/lib__typesMap.json | heldout | 5.812× | 1.254× | 1.360× | 1.863 | 1.000 |
| json/real/lib__ja__diagnosticMessages.generated.json | heldout | 3.908× | 1.791× | 1.752× | 3.070 | 2.375 |

## Complete acceptance matrix

Expected source intent is separate from observed independent oracle validity. Acceptance alone is not a conformance claim. Parse eligibility requires both engines and the oracle to accept.

| Input | Category | Oracle valid | Gramide accepts | Tree-sitter accepts | Parse eligible | Symbols equal |
|---|---|---|---|---|---|---|
| java/real/JsonNull.java | real | True | yes | yes | yes | True |
| java/real/Strictness.java | real | True | yes | yes | yes | True |
| java/real/ExclusionStrategy.java | real | True | yes | yes | yes | True |
| java/real/JsonParser.java | real | True | yes | yes | yes | True |
| java/real/JsonElement.java | real | True | yes | yes | yes | True |
| java/real/JsonPrimitive.java | real | True | yes | yes | yes | True |
| java/real/LinkedTreeMap.java | real | True | yes | yes | yes | True |
| java/real/JsonReader.java | real | True | yes | yes | yes | True |
| typescript/real/corePublic.ts | real | True | yes | yes | yes | True |
| typescript/real/performance.ts | real | True | yes | yes | yes | True |
| typescript/real/watchUtilities.ts | real | True | yes | yes | yes | True |
| typescript/real/core.ts | real | True | yes | yes | yes | True |
| typescript/real/lib__lib.es2015.symbol.d.ts | real | True | yes | yes | yes | True |
| typescript/real/lib__lib.es2021.promise.d.ts | real | True | yes | yes | yes | True |
| typescript/real/lib__lib.es2015.iterable.d.ts | real | True | yes | yes | yes | True |
| typescript/real/lib__lib.es5.d.ts | real | True | yes | yes | yes | True |
| json/real/tree-sitter-json__tree-sitter.json | real | True | yes | yes | yes | True |
| json/real/tree-sitter-json__package.json | real | True | yes | yes | yes | True |
| json/real/tree-sitter-json__src__node-types.json | real | True | yes | yes | yes | True |
| json/real/tree-sitter-json__src__grammar.json | real | True | yes | yes | yes | True |
| json/real/tree-sitter-java__src__node-types.json | real | True | yes | yes | yes | True |
| json/real/tree-sitter-typescript__typescript__src__grammar.json | real | True | yes | yes | yes | True |
| json/real/package.json | real | True | yes | yes | yes | True |
| json/real/lib__typesMap.json | real | True | yes | yes | yes | True |
| json/real/lib__ja__diagnosticMessages.generated.json | real | True | yes | yes | yes | True |
| json/scaling/rows-00008.json | generated | True | yes | yes | yes | True |
| json/scaling/rows-00512.json | generated | True | yes | yes | yes | True |
| json/scaling/rows-08192.json | generated | True | yes | yes | yes | True |
| json/coverage/scalar-string.json | coverage_probe | True | yes | yes | yes | True |
| json/coverage/numbers.json | coverage_probe | True | yes | yes | yes | True |
| json/coverage/escapes.json | coverage_probe | True | yes | yes | yes | True |
| json/coverage/duplicate-names.json | coverage_probe | True | yes | yes | yes | True |
| json/coverage/unicode.json | coverage_probe | True | yes | yes | yes | True |
| json/coverage/nested-128.json | coverage_probe | True | yes | yes | yes | True |
| java/coverage/CoreDeclarations.java | coverage_probe | True | yes | yes | yes | True |
| java/coverage/CoreStatements.java | coverage_probe | True | yes | yes | yes | True |
| java/coverage/TextBlocksUnicode.java | coverage_probe | True | yes | yes | yes | True |
| java/coverage/module-info.java | coverage_probe | True | no | yes | no | — |
| java/coverage/SwitchExpression.java | coverage_probe | True | no | yes | no | — |
| java/coverage/RecordPattern.java | coverage_probe | True | no | yes | no | — |
| java/coverage/TypeUse.java | coverage_probe | True | no | yes | no | — |
| java/coverage/Receiver.java | coverage_probe | True | no | yes | no | — |
| java/coverage/NonSealed.java | coverage_probe | True | no | yes | no | — |
| java/coverage/IntersectionCast.java | coverage_probe | True | no | yes | no | — |
| java/coverage/ClassLiterals.java | coverage_probe | True | no | yes | no | — |
| java/coverage/QualifiedInner.java | coverage_probe | True | no | yes | no | — |
| java/coverage/UnicodeEscapes.java | coverage_probe | True | no | no | no | — |
| java/coverage/CompactUnit.java | coverage_probe | None | no | yes | no | — |
| typescript/coverage/types.ts | coverage_probe | True | yes | yes | yes | True |
| typescript/coverage/generics.ts | coverage_probe | True | yes | yes | yes | True |
| typescript/coverage/expressions.ts | coverage_probe | True | yes | yes | yes | True |
| typescript/coverage/namespace-enum.ts | coverage_probe | True | yes | yes | yes | True |
| typescript/coverage/class-private.ts | coverage_probe | True | yes | yes | yes | True |
| typescript/coverage/async-generator.ts | coverage_probe | True | yes | yes | yes | True |
| typescript/coverage/decorators.ts | coverage_probe | True | yes | yes | yes | False |
| typescript/coverage/import-attributes.ts | coverage_probe | True | yes | yes | yes | True |
| typescript/coverage/jsx.tsx | coverage_probe | untested TSX | — | — | no | — |
| java/malformed/JsonNull.missing-final-brace.java | malformed | False | no | no | no | — |
| java/malformed/JsonReader.missing-final-brace.java | malformed | False | no | no | no | — |
| typescript/malformed/corePublic.missing-final-brace.ts | malformed | False | no | no | no | — |
| typescript/malformed/performance.missing-final-brace.ts | malformed | False | no | no | no | — |
| json/malformed/tree-sitter-json__package.missing-final-brace.json | malformed | False | no | no | no | — |
| json/malformed/tree-sitter-json__src__grammar.missing-final-brace.json | malformed | False | no | no | no | — |
| json/malformed/trailing-comma.json | malformed | False | no | no | no | — |
| json/malformed/leading-zero.json | malformed | False | no | no | no | — |
| json/malformed/unterminated-string.json | malformed | False | no | no | no | — |
| java/malformed/MissingInitializer.java | malformed | False | no | no | no | — |
| java/malformed/UnterminatedString.java | malformed | False | no | no | no | — |
| typescript/malformed/missing-initializer.ts | malformed | False | no | no | no | — |
| typescript/malformed/unterminated-string.ts | malformed | False | no | no | no | — |

## Reproduction and scope

Follow [README.md](README.md) and [PROTOCOL.md](PROTOCOL.md). Corpus provenance, selection made before parser runs, development/held-out split, source hashes and licenses are retained. This is a small purposive sample, not a random ecosystem study. Java real inputs are from Gson; TypeScript inputs are from TypeScript; JSON includes parser metadata.

The original unmodified core/grammar baseline is pinned in `gramide-harness/almide.lock` and can be rebuilt with the same adapter. Earlier diagnostic timings are deliberately not used as optimized-vs-original speedup evidence. Final results compare the correctness-fixed candidate with the unchanged official Tree-sitter reference.

Native compiler version, compiler/binary hashes, generated Cargo profile and source hashes are recorded. The measured Almide 0.62.0 binary uses generated Cargo release opt-level 3, LTO and one codegen unit; C uses -O3 -flto=1 -DNDEBUG. The nearby compiler checkout commit is metadata, not proof of the binary source identity. Host-specific paths inside raw build records describe the original run, not required reproduction paths.
