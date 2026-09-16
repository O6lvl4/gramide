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
  again recovering, with an `ERROR` node over each part the grammar gave up.
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
relative to the run, and the children's sizes beside them. An edit walks
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
2.9 MB) a keystroke inside an identifier costs 126 µs at the median
against 566 µs for tree-sitter's incremental parse and 57 ms for a whole
parse ([gramide-typescript](https://github.com/O6lvl4/gramide-typescript),
`docs/evidence/incremental-typescript-src.json`). A reader that wants the
whole tree again materializes it, which is one pass and no parsing.

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
