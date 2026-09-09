# gramide

Syntax trees for coding agents, written in [Almide](https://github.com/almide/almide).
`gramide` turns a source file into a tree an agent can ask questions of: does this
file still parse, where does each declaration start and end, what is this node's
name. A grammar is an ordinary value in the language, the parser interprets it, and
there is no generator step and no native library between the agent and the tree.

[日本語](README_ja.md)

```
gramide check   src/main.almd     exit 0 if it parses, else `file:line:col: unexpected X (expected …)`
gramide check   src/*.almd        any number of files: each grammar is compiled once, not once per file
gramide outline src/main.almd     one line per declaration: L12-40 function_declaration parse
gramide parse   src/main.almd     the whole tree as an s-expression
gramide tags    src/main.almd     `def function parse L40-58`, `ref call list.map L44`, `ref type Node L12` — a repo map's input
gramide balance Widget.java       delimiters and literals only, for a language with no grammar here:
                                  it cannot see a missing semicolon, and it cannot reject valid code
gramide tokens  src/main.almd     the token stream, one per line
gramide map . --budget 1024 --task "fix parse_rule"
                                  a ranked map of the repository within the token budget:
                                  the definitions other files use most, personalised toward
                                  what the task mentions — what an agent reads before opening files
```

## Why

An agent that edits code needs two things from a parser: a fast, honest answer to
"did I just break the file", and a map of what is where so it can read only the part
it needs. It does not need a full compiler front end, and it should not need a
different native library for each language it touches. gramide is the smallest thing
that gives an agent those two answers, in the same language the agent's tools are
written in, so a grammar can be read, patched and tested like any other module.

## Status

Two languages: Almide (`.almd`) and Go (`.go`). Each is measured against a whole
reference corpus, and the guarantee is the same for both and runs one way: **a file
gramide rejects is broken for the reference parser too.** The reverse is not promised;
the grammars are more permissive than the compilers in a few known places listed in
[docs/design.md](docs/design.md).

**Almide** — every `.almd` file in the Almide repository (3,382 files after excluding
two directories of deliberately non-Almide syntax experiments):

| files | result |
|---|---|
| 3,317 well-formed files | all parse |
| 65 `broken.almd` diagnostic fixtures | all rejected, each also rejected by the compiler |
| 720 other `broken.almd` fixtures | parse, and fail in the compiler at type checking as intended |

**Go** — every `.go` file under `GOROOT/src` of Go 1.27 (8,077 files, standard
library, compiler and toolchain, test data included):

| files | result |
|---|---|
| 8,042 files | all parse |
| 35 files, all under `testdata` | rejected, each also rejected by `gofmt -e` |
| 11 `testdata` files `gofmt` rejects | parse (gramide is more permissive than `gofmt` here) |

Whole-corpus `check` on 8 cores: 2.5 s for the Almide corpus, 23 s for the Go corpus;
the largest file, a 116k-line generated Go source, takes 7.6 s alone.

## How it works

```
source ──lexer──▶ tokens ──parser(grammar)──▶ tree ──▶ check / outline / parse
```

- **`src/lexer.almd`** — a hand-written lexer over bytes. Newlines are tokens (Almide
  separates statements with them), comments and blank-line runs are dropped, a string
  literal with `${…}` interpolation, a heredoc or a raw string is one token.
- **`src/parser.almd`** — the engine. A grammar is a `Grammar { start, rules }` whose
  rules are `Rule` values (`Tok`, `Lit`, `Seq`, `Alt`, `Rep`, `Opt`, `Wrap`, `Field`,
  `Left`, lookahead). Ordered choice, greedy repetition, no left recursion: binary
  operators are `Left(kind, operand, op)` and fold to the left after matching. The
  parser remembers the farthest token anything failed at and what was expected there,
  which is the error `check` prints.
- **`src/lang_almide.almd`**, **`src/lang_go.almd`** — the grammars as values. The Go one
  builds its expression ladder twice from one function, with and without a trailing
  composite literal, which is how `if x == T{…} {` is kept unambiguous.
- **`src/lex_go.almd`** — the Go lexer; semicolon insertion lives here, so the grammar
  only ever sees a separator where Go sees one.
- **`src/tree.almd`** — `Node { kind, field, start, end, kids }` spanning token
  indices, with `child(n, "name")`, `text_of`, `sexp`, and `collect`.
- **`src/tags.almd`**, **`src/map.almd`** — definitions and references per file, and the
  repository map: files referencing a name another file defines are edges, PageRank
  personalised toward the task ranks the definitions, and the best are rendered file by
  file until the budget is spent.

A note on the engine: the grammar value is compiled once into a flat arena of
three-integer nodes and `parse_rule` is one self-recursive function with the loops
for sequence, choice and repetition inside it. Both shapes come from how the Almide
native backend copies values, and [docs/design.md](docs/design.md) records each rule
with the measurement that forced it (the last one took a 116k-line file from 188 s
to 7.6 s).

## Build

```
almide build            # → ./gramide
almide test             # 22 tests across the nine modules
```

Requires Almide 0.61 or later.

## License

MIT or Apache-2.0, at your option.
