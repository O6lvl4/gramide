# gramide

Syntax trees for coding agents, written in [Almide](https://github.com/almide/almide).
This is the engine: a lexer over bytes, a parser that interprets a grammar
value, the syntax tree, the readers over it — outline, tags, structured
symbols, a repository map, a delimiter balance — and the command line as a
library. No language lives here. A language is a package of its own that
hands this engine one value, and a binary — the `gramide` command everyone
runs is [gramide-cli](https://github.com/O6lvl4/gramide-cli) — is whichever of
those packages it composes.

[日本語](README_ja.md)

```
gramide                 this repository: engine, contract, readers, command line
gramide_almide   .almd       one repository per language, each depending on the engine
gramide_go       .go         https://github.com/O6lvl4/gramide-go
gramide_rust     .rs         https://github.com/O6lvl4/gramide-rust
gramide_python   .py .pyi    https://github.com/O6lvl4/gramide-python
gramide-cli                  the `gramide` command: every package above, composed in one file
```

That is tree-sitter's shape — a runtime, one repository per grammar, a CLI —
with one difference the language forces. Almide links statically, so a binary
names the languages it ships in its own `main.almd` instead of loading them at
run time; a language package therefore also carries a small binary of its own,
so that it can be tested, measured and regenerated without the others.

## What is here

```
source ──lexer──▶ tokens ──parser(grammar)──▶ tree ──▶ outline / symbols / tags / map
```

- **`src/lex.almd`** — one lexer over bytes for every language a table can
  describe. A package hands it a `Spec`: keywords, operators, comment markers,
  what a newline means, and a named family for the two things a table cannot
  say, how numbers are written and how string literals end. Go is 32 lines
  of spec.
- **`src/parser.almd`** — the engine. A grammar is a `Grammar { start, rules }`
  of `Rule` values (`Tok`, `Lit`, `Seq`, `Alt`, `Rep`, `Opt`, `Wrap`, `Field`,
  `Left`, lookahead, recovery). Ordered choice, greedy repetition, no left
  recursion. The value is compiled once into a flat arena of three-integer
  nodes, and a run reads that arena from a package's committed table rather
  than compiling anything. The parser remembers the farthest token anything
  failed at, which is the error `check` prints, and a reader that fails asks
  again recovering, with an `ERROR` node over each part the grammar gave up;
  a file whose brackets do not balance goes to recovery straight away.
- **`src/tree.almd`**, **`src/names.almd`** — `Node { kind, field, start, end, kids }`
  over token indices, with kinds and fields as numbers into one name table.
- **`src/package_api.almd`** — the contract: `Definition` and `SymbolRules`.
  [docs/language-packages.md](docs/language-packages.md) is the whole of it.
- **`src/registry.almd`**, **`src/lang.almd`** — the host. A list of
  definitions in, a `Reading` out: the tree, whether it is the recovered one,
  and what the package says about names.
- **`src/tags.almd`**, **`src/symbols.almd`**, **`src/map.almd`**,
  **`src/balance.almd`** — the readers. Definitions and references per file;
  the versioned JSON hew reads ([docs/symbols.md](docs/symbols.md)); a ranked,
  budgeted map of a repository; and the delimiter check a language with no
  grammar can still have.
- **`src/cli.almd`** — every command, as a library. A binary composes a
  `Program` and calls `run`; the only thing it writes itself is the parallel
  `check` over many files, for a reason recorded there.
- **`src/tables.almd`** — writes a compiled grammar down as Almide source,
  which is how every package's `src/table.almd` is made.
- **`src/incremental.almd`**, **`src/keystrokes.almd`** — a parsed file kept
  as recover items nested in recover items, so that an edit re-reads the
  smallest item it touched ([docs/incremental.md](docs/incremental.md)); and
  the keystroke benchmark `reparse-bench` runs, the same edit sequence the
  tree-sitter harness in each language package replays.

## Reading a file after an edit

The parser stamps every node a `recover` or `recover_all` site read with
that site. `incremental.from_parsed` cuts the tree there: each item keeps
only its own tokens, in runs between its child items, every offset
relative to the run; a child's size is read where the child stands. An edit walks
down to the deepest item that holds it whole, re-lexes that sibling window
through the first token after it, parses the window with the site's body
until it reaches that token, and puts the new items in; the bases above
are sums of integers. If the lexer or the parser disagree with what was
there — the token after the window came out different, or the window did
not end where it starts — the answer is "read the whole file", and so is
an edit beside an `ERROR` item, because recovery is not local. What comes
out is checked against a whole parse of the same text, token for token
and node for node, in the engine's tests and in each language package's
random-edit check over its corpora.

On `compiler/checker.ts` of TypeScript 5.9 (3.1 MB, one function of
2.9 MB) a keystroke inside an identifier costs 54 µs at the median
against 561 µs for tree-sitter's incremental parse and 58 ms for a whole
parse ([gramide-typescript](https://github.com/O6lvl4/gramide-typescript),
`docs/evidence/incremental-typescript-src.json`). A reader that wants the
whole tree again materializes it, which is one pass and no parsing.

Two kinds of edit read nothing at all: one in a comment or in blank space,
and one that retypes a single name — the run of the item's own tokens is
lexed again, must give the same tokens, and only positions move. Every
item carries an id that the edits leaving it alone do not change; an item
read again in place of itself keeps it; over 1,000 edits on each file the
packages measure, no item was renamed (`reparse-bench` counts them). The
same reader serves Python, whose statements are `recover_lines` items and
whose indentation a slice lexed on its own cannot place — so a run's
layout tokens are kept where they were when no line break was typed or
deleted.

Every node carries an id as well, and an id stands for one text: a node
keeps its id exactly when the edit left its text alone, where it was or
moved by the edit, and every node whose text the edit changed — what was
read again and came out different, and every node that holds the edit —
is named anew; no id is given twice, not even when the file has to be
read whole. `reparse --nodes` prints every node with its id. Each
package's random-edit check holds that rule on every edit of its corpora;
on `checker.ts` an edit renames 15 of its 338,851 nodes at the median.

A document read and edited holds about twice what tree-sitter's tree does
(127 MB against 62 on `checker.ts`), since the parse and the document cut
from it stand side by side while it is cut; `check` holds a third to over
half less than tree-sitter from a few hundred kilobytes up, and a file read
once is within 4% of it ([docs/incremental.md](docs/incremental.md),
[evidence](docs/evidence/memory.json)).

## Reading a file that does not parse

A file whose brackets do not balance is paired first, by kind and by
indentation: a closer that begins its line pairs with the open bracket of
its kind on a line indented as its own, and a nearer one on a deeper line is
the bracket that lost its closer. That bracket ends before the next line
indented no deeper than its own — the body of an `if` whose `}` went missing
ends where the `if`'s next statement begins, and the function around it
reads on as written. Such a file is not read strictly at all, since no
grammar reads a lone bracket, and the reader names the bracket the pairing
left open: ``21493:26: `{` is never closed``. Where an item still fails, a
recover site skips to the next place the item rule reads, reads it again
with one closer taken as there where it failed farthest, or keeps a body
left open at the end of the file, whichever puts fewer tokens under
`ERROR`. Python's layout pass closes a bracket left open where a dedented
statement begins. [docs/recovery.md](docs/recovery.md) is the model, and the measurement: each
package breaks every file of its corpus four ways and compares the
declarations gramide and tree-sitter still list with their own listings of
the whole file. Kept is the share of declarations still listed; clean is the
share of breaks that lost nothing beyond the break and invented nothing:

| corpus | files, breaks | kept: gramide / tree-sitter | clean breaks: gramide / tree-sitter |
|---|---:|---:|---:|
| JavaScript, Node `lib/` | 427, 1,694 | 99.4% / 95.9% | 98.3% / 90.6% |
| TypeScript, TypeScript `src/` | 697, 2,588 | 99.2% / 99.0% | 98.1% / 94.6% |
| Go, Go `src/` | 8,010, 30,927 | 99.8% / 91.1% | 99.3% / 82.9% |
| Rust, Almide compiler `crates/` | 663, 2,632 | 100.0% / 97.5% | 100.0% / 94.9% |
| Python, CPython `Lib/` | 1,450, 5,193 | 99.0% / 96.3% | 98.2% / 82.3% |

A broken file costs little more than a whole one. `compiler/checker.ts` with
a `)` or `}` deleted, or a `(` or `{` typed, from once to at every place there
is one, reads its outline in 0.03 to 0.12 s, against 0.07 to 0.89 s for
tree-sitter, and at no count in more than 67% of tree-sitter's time; the
whole file takes 0.07 to 0.08 s against 0.14 s ([evidence](https://github.com/O6lvl4/gramide-typescript/blob/main/docs/evidence/recovery-cost-checker-ts.json)).

## Writing a language package

```
gramide-go/
  almide.toml        name = "gramide_go"; gramide is the one dependency
  src/mod.almd       definition()
  src/lexer.almd     the Spec, or a scanner of its own
  src/grammar.almd   fn rules() -> parser.Grammar, and its tests
  src/symbols.almd   symbol_rules(): which nodes declare a name, own methods, mention a type
  src/table.almd     generated: `./gramide_go gen-table > src/table.almd`
  cli/main.almd      the package's own binary, twenty lines
  ci/check.sh        almide test; the table check; the binary's smoke test; the language's oracles
```

[docs/language-packages.md](docs/language-packages.md) walks through each
file, and `src/package_contract_test.almd` is a complete package in forty
lines — a made-up syntax with its own lexer, grammar and rules — that the
engine's own tests and `ci/smoke.py` drive through every command.

## Composing a binary

```
import gramide.cli
import gramide_go

fn packages() -> List[package_api.Definition] = [gramide_go.definition()]

effect fn main() -> Unit = {
  let argv = env.args()
  match cli.batch_of(argv) {
    some((cmd, paths)) => cli.report(parallel(cmd, paths)!),   // eight slices in a fan block
    none => cli.run(cli.Program { name: "mine", version: "0.1.0", packages: packages() }, argv),
  }
}
```

[gramide-cli](https://github.com/O6lvl4/gramide-cli) is exactly this over
four packages; `parallel` is the twenty lines every binary carries, and the
contract page says why the engine cannot.

## What was measured

[docs/design.md](docs/design.md) records each rule the engine's shape follows
and the measurement that forced it — one took a 116k-line generated Go file
from 188 s to 7.6 s — and what the native backend taught it about copying.
[bench/README.md](bench/README.md) is the board: every performance change
since, with its evidence in `docs/evidence/`. The per-language corpora,
oracles, the comparisons against tree-sitter and the keystroke benchmarks
live with each language.

## Build

```
almide test          # 100 tests, the contract test included
bash ci/check.sh     # the same, then the demo binary through every command
```

Requires Almide 0.62 or later. A package depends on this one with

```toml
[dependencies]
gramide = { git = "https://github.com/O6lvl4/gramide", tag = "v0.1.2" }
```

## License

MIT or Apache-2.0, at your option.
