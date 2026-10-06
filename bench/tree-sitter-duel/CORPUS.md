# Frozen gramide / Tree-sitter input corpus

Prepared on 2026-10-05. Corpus ID: `gramide-duel-20261005-v1`.

## What is frozen

`corpus/manifest.json` is the input contract. Each entry includes `id`, `path`,
`language`, `grammar_variant`, `category`, `split`, `expected_valid`,
`expected_syntax`, `sha256`, `source_url`, `license_path`, `license_paths`,
`bytes`, provenance, and feature labels. Input and license paths are relative
to `corpus/`. Categories are `real`, `generated`, `coverage_probe`, and
`malformed`. Splits are `development` and `heldout`.

| Language | Real sources | Scaling | Coverage probes | Malformed | Total |
|---|---:|---:|---:|---:|---:|
| JSON | 9 | 3 | 6 | 5 | 23 |
| TypeScript | 8 | 0 | 9 | 4 | 21 |
| Java | 8 | 0 | 14 | 4 | 26 |
| Total | 25 | 3 | 29 | 13 | 70 |

One TypeScript coverage file is TSX. It keeps `language=typescript` and
`grammar_variant=tsx`, with `optional_variant=true`. A TypeScript-only adapter
must report it as `not_tested_grammar_variant: tsx`; it must not count as an
acceptance or rejection. That leaves 69 inputs in the current common grammar
scope, including 25 real sources.

No tested parser, TypeScript compiler oracle, javac oracle, build, or performance
test was executed while preparing this corpus. `expected_valid` is an input
expectation, not an oracle result. Upstream released sources are expected to be
syntactically valid. Generated probes have manually specified syntactic
expectations. Semantic/type correctness, dependency resolution and compiler
conformance have not been claimed.

## Selection and anti-cherry-picking rules

The real file list was written to `corpus/selection.json` before any of these
inputs were tested. Selection was purposive, by source role and approximate
size, not by gramide acceptance. All selected files were retained. Small means
under 4 KiB, medium 4 to under 32 KiB, large at least 32 KiB.

- JSON: official package and parser configuration, schema-like node metadata,
  nested grammar data, a types map, and a large Japanese diagnostic catalogue
- TypeScript: four shipped declaration libraries and four compiler source
  implementations, so declaration-heavy successes cannot stand in for runtime
  implementation coverage
- Java: public value class, enum and interface; parser/element/primitive APIs;
  a generic tree map; and a larger streaming reader implementation

This is a small role/size-stratified workload, not a random sample or an
ecosystem-wide acceptance study. Java sources come from one library; TypeScript
sources come from one compiler project; JSON source data includes Tree-sitter
metadata. These are limitations to disclose, not reasons to remove difficult
files after testing. Unchanged comments and documentation are part of source
bytes and timed workload.

Four Java and four TypeScript real files are development inputs; four each
are held out. JSON has four development and five held-out real inputs. The
partition was assigned before tested parser runs. Do not tune on held-out
files or silently move a failing held-out input into development. No claim
is made that these public sources were never seen in an earlier unrelated
task or in model training.

Report all fixed-set acceptance/error outcomes before timing. A parser
rejection is not a fast parse win. A successful parse with ERROR/MISSING nodes
must remain distinguishable from an error-free parse. Joint-success timing
may be reported, but it must name its denominator and show failures on the
full fixed set. Separate real-world timing, synthetic scaling, coverage and
malformed controls. Do not infer a general victory from synthetic JSON alone.

## Real input inventory

### Java: Gson 2.11.0

Pinned repository revision:
`828a97be0f8d58108b140b77df8dc76b657f4a87` (`gson-parent-2.11.0`).
Sources were fetched through the GitHub connector, not a full repository clone.
Each downloaded UTF-8 byte sequence was independently matched to its upstream
Git blob SHA-1, then SHA-256 frozen. Original copyright headers are untouched.

| File | Bytes | Split |
|---|---:|---|
| Strictness.java | 985 | heldout |
| JsonNull.java | 1,640 | development |
| ExclusionStrategy.java | 4,056 | development |
| JsonParser.java | 6,737 | heldout |
| JsonPrimitive.java | 10,367 | heldout |
| JsonElement.java | 16,156 | development |
| LinkedTreeMap.java | 19,692 | development |
| JsonReader.java | 59,285 | heldout |

Source paths and immutable origin URLs are in the manifest. Full Apache-2.0
license: `corpus/licenses/gson-APACHE-2.0.txt`.

### TypeScript 5.9.3

Pinned official repository revision:
`c63de15a992d37f0d6cec03ac7631872838602cb` (`v5.9.3`).
Compiler implementation files were fetched at that revision and matched to
Git blob hashes, preserving CRLF and UTF-8 bytes. Declaration libraries were
copied read-only from the existing official npm `typescript@5.9.3` installation.

| File | Bytes | Split |
|---|---:|---|
| src/compiler/corePublic.ts | 1,318 | development |
| lib/lib.es2015.symbol.d.ts | 1,649 | development |
| lib/lib.es2021.promise.d.ts | 2,262 | heldout |
| src/compiler/performance.ts | 6,146 | heldout |
| lib/lib.es2015.iterable.d.ts | 18,200 | development |
| src/compiler/watchUtilities.ts | 34,758 | development |
| src/compiler/core.ts | 92,353 | heldout |
| lib/lib.es5.d.ts | 218,439 | heldout |

The installed package version and its pnpm lock integrity are recorded.
The tarball was not re-downloaded or independently re-verified in preparation;
the actual installed file bytes are SHA-256 frozen. Package tarball/integrity
URLs identify that distinction in the manifest. Full Apache-2.0 license and
third-party notices are retained in `corpus/licenses/typescript-*`.

### JSON

Tree-sitter source snapshots are read directly from their committed Git blobs,
so any modified worktree file would not change the selected inputs.

| Source/file | Bytes | Split |
|---|---:|---|
| tree-sitter-json/tree-sitter.json | 676 | development |
| tree-sitter-json/package.json | 1,259 | heldout |
| tree-sitter-json/src/node-types.json | 2,698 | development |
| TypeScript/package.json | 3,620 | development |
| tree-sitter-json/src/grammar.json | 13,683 | heldout |
| TypeScript/lib/typesMap.json | 16,788 | heldout |
| tree-sitter-java/src/node-types.json | 81,249 | development |
| tree-sitter-typescript/typescript/src/grammar.json | 281,518 | heldout |
| TypeScript/lib/ja/diagnosticMessages.generated.json | 381,398 | heldout |

Pinned Tree-sitter revisions:

- tree-sitter-json: `254c42a6476413b776221e03982ac8ae159eeb72`
- tree-sitter-java: `e10607b45ff745f5f876bfa3e94fbcc6b44bdc11`
- tree-sitter-typescript: `75b3874edb2dc714fb1fd77a32013d0f8699989f`

Each repository's complete MIT license is retained separately. TypeScript JSON
files use the same installed-package provenance and notices as its libraries.

## Scaling and syntax breadth

JSON scaling uses one deterministic mixed-type object repeated 8, 512 and
8,192 times: 1,106, 70,658 and 1,130,498 bytes. UTF-8 text, escapes, numbers,
booleans, null, arrays and nested objects are present. The largest size is
held out. These inputs measure scaling for a repetitive structure and must
remain separate from the real-file result.

`corpus/coverage-plan.json` is an unexecuted coverage plan. It is not a result
or conformance certificate. JSON probes include scalar roots, numeric lexical
edges, all escape forms, duplicate names, escaped unpaired surrogates, UTF-8
and nesting depth 128. Duplicate names and escaped unpaired surrogates are
intentional JSON-syntax cases, not application-level validity claims.

TypeScript probes include mapped/conditional/template literal types, const
type parameters, indexed access, satisfies, optional chaining, nullish
coalescing, regex, namespaces/enums, import aliases, private fields, static
blocks, parameter properties, async generators, decorators, import attributes,
type-only exports, and the separately labeled TSX example. These are parse
tests; unresolved imports and type errors must not be conflated with syntax.

Java includes three core positive probes and eleven explicitly labeled
`declared_gramide_limit=true` probes based on the package's documented limits:

- Modules (Java 9)
- Switch expressions, arrow cases and yield (Java 14)
- Record/switch patterns (Java 21)
- Type-use annotations and explicit receiver parameters (Java 8)
- Non-sealed declarations (Java 17)
- Intersection casts (Java 8)
- Primitive and array class literals
- Generic inner-class creation
- Unicode escape preprocessing of keywords and identifiers
- Compact compilation units / instance main methods (Java 25)

These remain `expected_valid=true`. A known implementation limitation is
not a malformed-source label. Java release requirements are recorded per
probe; compiler checks would need an appropriate JDK. The corpus does not
assume Tree-sitter accepts every modern probe either.

## Malformed controls and change notices

Six controls each remove exactly the final required `}` byte from an existing
real file. File names prominently include `.missing-final-brace`. Their
manifest entries identify the parent ID/hash, exact byte offset, removed byte,
unchanged upstream attribution, and reason the edit is expected to be invalid.
These six files are modified benchmark copies, not upstream originals:

- Java: JsonNull.java and JsonReader.java
- TypeScript: corePublic.ts and performance.ts
- JSON: tree-sitter-json package.json and src/grammar.json

Seven original malformed snippets add absent initializer expressions,
unterminated strings, JSON trailing commas, and a JSON leading-zero number.
All thirteen controls are `expected_valid=false`, separate from coverage
limits. Their rejection only shows detection of those syntax errors; it is
never evidence of semantic validation or compiler equivalence. Upstream
licenses continue to apply to edited copies. Original generated probes and
scaling files carry the retained MIT license for this benchmark.

## Integrity and reproduction

Run from the benchmark directory:

    python corpus_prepare.py --verify

This verifies the retained-file checksum list, every manifest input's byte
count/hash, and license availability without any original source installation.
It executes no tested parser. `corpus/checksums.sha256` covers input bytes,
licenses, selection, source lock, fetched source responses, the manifest and
coverage plan. The manifest SHA-256 should be recorded in the run results.

Running `python corpus_prepare.py` rematerializes the corpus using the retained
GitHub responses and the pinned source checkouts/TypeScript installation. It
refuses silently changed upstream source locks. It does not download code,
build, parse benchmark inputs, or modify other tasks. Generated content is
deterministic. Keep the corpus unchanged after a benchmark begins; material
corrections require a new version and an explicit disclosure.
