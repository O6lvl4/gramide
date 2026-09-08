# gramide

Syntax trees for coding agents, written in [Almide](https://github.com/almide/almide).
`gramide` turns a source file into a tree an agent can ask questions of: does this
file still parse, where does each declaration start and end, what is this node's
name. A grammar is an ordinary value in the language, the parser interprets it, and
there is no generator step and no native library between the agent and the tree.

[日本語](README_ja.md)

```
gramide check   src/main.almd     exit 0 if it parses, else `file:line:col: unexpected X (expected …)`
gramide outline src/main.almd     one line per declaration: L12-40 function_declaration parse
gramide parse   src/main.almd     the whole tree as an s-expression
gramide tags    src/main.almd     `def function parse L40-58`, `ref call list.map L44`, `ref type Node L12` — a repo map's input
gramide tokens  src/main.almd     the token stream, one per line
```

## Why

An agent that edits code needs two things from a parser: a fast, honest answer to
"did I just break the file", and a map of what is where so it can read only the part
it needs. It does not need a full compiler front end, and it should not need a
different native library for each language it touches. gramide is the smallest thing
that gives an agent those two answers, in the same language the agent's tools are
written in, so a grammar can be read, patched and tested like any other module.

## Status

Almide only, at this stage. Measured against every `.almd` file in the Almide
repository (3,382 files after excluding two directories of deliberately
non-Almide syntax experiments):

| files | result |
|---|---|
| 3,317 well-formed files | all parse |
| 65 `broken.almd` diagnostic fixtures | all rejected, each also rejected by the compiler |
| 720 other `broken.almd` fixtures | parse, and fail in the compiler at type checking as intended |

Whole-corpus `check` takes about 7 seconds on 8 cores, roughly 2 ms per file.

The guarantee runs one way: **a file gramide rejects is broken for the compiler
too.** The reverse is not promised. The grammar is more permissive than the compiler
in a few known places (chained comparisons, `|>` with an arbitrary right-hand side,
angle-bracket generics, a `todo` without a string) and it does not parse the inside
of `${…}` interpolations. See [docs/design.md](docs/design.md) for the list.

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
- **`src/lang_almide.almd`** — the Almide grammar as a value, following
  `docs/GRAMMAR.md` in the Almide repository.
- **`src/tree.almd`** — `Node { kind, field, start, end, kids }` spanning token
  indices, with `child(n, "name")`, `text_of`, `sexp`, and `collect`.

A note on the engine: `parse_rule` is one self-recursive function with the loops for
sequence, choice and repetition inside it. The Almide native backend passes a list
parameter by reference only when the function is not part of a mutually recursive
group; with helper functions every call copied the grammar and the token list and a
280-line file took 21 s. Inlined, the same file takes 0.15 s.

## Build

```
almide build            # → ./gramide
almide test             # 16 tests across the five modules
```

Requires Almide 0.61 or later.

## License

MIT or Apache-2.0, at your option.
