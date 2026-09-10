# Structured symbols, schema 1

`gramide symbols FILE` writes one JSON object to stdout on success. It supports
Almide, Go and Rust. Unlike the display outline, it exits nonzero without JSON
when lexing/parsing requires recovery. `complete` describes parser completion,
not semantic validity or a proof that every possible declaration is modeled.

The object contains `schema_version: 1`, `complete: true`, `lang`, `total_lines`
and `symbols`. Each symbol has:

- `kind`, `syntax_kind`, `name`, `owner`: a display category, grammar node kind,
  name and type owner. Methods are qualified (`Box::read`, `Box.Read`). `owner`
  is empty for free functions; this is not module/name resolution.
- `start`, `end`: one-based, inclusive physical line ranges.
- `start_byte`, `end_byte`: zero-based UTF-8 offsets, end exclusive.

Rust item envelopes retain attributes and visibility modifiers for function
ranges. Line ends account for multiline literal tokens. Existing text outline
formatting stays available; `parse` now exposes Rust `item_envelope` nodes.

## Reference comparison

The Go AST contract uses `Pos()` at the first token and `End()` immediately after
the declaration. The oracle in `ci/reference_ranges.go` uses the standard parser,
independently of gramide, and compares concrete function/method declarations.
Interface method signatures are not `ast.FuncDecl` and are outside this oracle.

At Go reference commit `e51216de8e26247ee0f3d2cfa576233b0d29f542`, the 38 `.go`
files under `src/go/ast`, `src/go/parser` and `src/go/token`, excluding `testdata`,
matched on all 551 function/method names, line ranges and byte ranges. There were
no reference-invalid files or gramide rejections. See
[evidence with source hashes](evidence/go-ranges.json).

Reproduce with a checkout of that Go commit and Go installed:

```sh
almide build
python3 ci/reference_corpus.py /path/to/go /tmp/go-ranges.json
```

CI runs smaller independent-oracle fixtures plus Rust attributes, multiline
signatures, raw strings, ownership, Almide multiline literals and rejection of
incomplete source. These checks establish a bounded baseline, not tree-sitter
feature parity or accuracy across all languages.
