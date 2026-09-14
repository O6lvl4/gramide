# Language package contract

A language is an Almide package of its own that depends on `gramide` and
hands it one value, a `package_api.Definition`. The engine, the readers and
the command line know nothing else about it. This is the whole contract; the
rest of this page is what each field means and how a package repository is
laid out so that it can be tested, benchmarked and regenerated on its own.

```
type Definition = {
  id: String,                 // "go": what `symbols` reports as `lang`, and what names the table
  package_name: String,       // "gramide-go": what `languages` and `version` print
  version: String,
  extensions: List[String],   // [".go"]: how a path is resolved to this package
  capabilities: List[String], // which commands it answers for; see below
  lexer: () -> Tokenizer,     // prepared once per loaded language
  grammar: () -> parser.Compiled,
  sep: String,                // "." or "::": how a method is named with its type
  symbols: SymbolRules        // which nodes declare a name, own methods, or mention one
}
type Tokenizer = (String, Bool) -> Result[List[Token], LexError]   // the Bool asks for recovery
```

**`lexer`** returns a callback that turns source into tokens. Almide, Go and
Rust hand a `lex.Spec` to the shared lexer in `gramide.lex` — packed once
by `lex.prepare`, so that the keywords and operators are looked up by first
byte over the source bytes rather than compared as strings per token, and
the callback is `lex.tokenize_prepared` over that; Python has its own
scanner, because indentation, f-strings and Unicode identifiers are not
things a table can describe. The callback's boolean asks for recovery: an
unreadable run becomes an `error` token rather than a failure, so a reader can
still answer about the file.

**`grammar`** returns the compiled grammar. Every package ships it compiled,
in `src/table.almd`, and hands `() => table.compiled()`: compiling the rule
tree took 0.8 ms of every run before the file was opened, and a binary that
only reads tables never links a rule constructor, which was 38% of the
executable code of one that did. A package with only a rule tree may hand
`() => parser.compile(rules())`, which is what the contract test in
`src/package_contract_test.almd` does.

**`capabilities`** is checked by the host before a command runs, and by
consumers before they trust an answer: hew wants `symbols`, a write gate wants
`check`. A reader-only grammar must not advertise `check`. `symbols-recovered`
is advertised only by a package whose recovery never keeps a partial
declaration head, because that command exports declarations from a file that
does not parse.

**`symbols`** maps syntax to meaning for the readers in `tags.almd`:

```
type SymbolRules = {
  declarations: List[(String, String)],   // node kind → the word the output uses ("function", "type", …)
  scopes: List[String],                   // nodes whose name owns the methods inside them (impl, class, …)
  namespaces: List[String],               // nodes whose name qualifies what is inside (mod, …)
  callables: List[String],                // declarations that are functions: a body holds no methods
  lexical_owners: Bool,                   // Python: the namespace path already names the owner
  envelopes: List[String],                // nodes whose start a declaration inside them inherits (attributes)
  unnamed_envelopes: List[String],        // the same, only when the envelope itself declares nothing
  arguments: String,                      // the node that closes a call in a postfix chain
  field_access: String,                   // the node that reads a field
  type_mentions: List[String]             // nodes whose first child, if a bare name, mentions a type
}
```

Grammars use the shared tree field names `name`, `trait`, `receiver` and
`field`, which the readers look up by name. Almide, Go and Rust spell a call's
arguments `arguments`, a field read `field_access` and a type `type_name`;
Python spells them `call` and `attribute` and has no node meaning "a type", so
its type mentions are `annotation`, `returns` and `bases`. A new convention
extends this contract with a test; it does not rename the readers.

## A package repository

```
gramide-go/
  almide.toml           name = "gramide_go"; gramide is the one dependency
  src/mod.almd          definition(), and VERSION
  src/lexer.almd        how it is lexed: the Spec (or, for Python, the scanner)
  src/grammar.almd      the grammar value, `fn rules() -> parser.Grammar`, and its tests
  src/symbols.almd      symbol_rules(), and what the readers say about a small file
  src/table.almd        generated: the grammar compiled, read by every binary
  cli/main.almd         the package's own binary: gramide over this language, plus gen-table
  ci/check.sh           almide test, the table check, the binary's smoke test, the language's oracles
  docs/evidence/        the measurements the README cites, as JSON
```

`src/mod.almd` imports `lexer`, `symbols` and `table`, never `grammar`: the
shipped `gramide` reaches `definition()` and nothing that constructs a rule.
`cli/main.almd` imports `grammar` too, because it is the one thing that
compiles it:

```
almide build cli/main.almd -o gramide_go     # the package's binary
./gramide_go gen-table > src/table.almd      # after any change to the grammar
./gramide_go gen-table | diff -u src/table.almd -   # what CI runs
```

`gramide.tables.render(id, rules())` writes the compiled arena down as
Almide source; the file it produces is deterministic, so the diff is the
check. The binary is built from `cli/`, not `src/`, because a package with a
`src/mod.almd` is a library and `almide build` of its `src/main.almd` does not
produce a program.

## Composing a binary

A binary lists its packages by name and hands the engine a `cli.Program`:

```
fn packages() -> List[package_api.Definition] = [gramide_go.definition(), …]

effect fn main() -> Unit = {
  let argv = env.args()
  match cli.batch_of(argv) {
    some((cmd, paths)) => cli.report(parallel(cmd, paths)!),
    none => cli.run(cli.Program { name: "gramide", version: VERSION, packages: packages() }, argv),
  }
}
```

`check` and `balance` over many files are a batch, and the batch is the one
thing the binary runs itself. `parallel` cuts the file list into eight slices
of roughly equal bytes and checks them in a `fan` block (25.5 MB of Go: 2.74 s
to 0.70 s). That block cannot live in the engine: a `fan` arm may carry only
values without closures, a package's lexer is a closure, and so each arm has to
build the packages by name — which only the binary that composes them can do.
`cli.sequential` is the one-slice batch for a binary that does not bother, and
`cli.run` alone still answers every command, `check` included, one slice at a
time. Every language package's `cli/main.almd` carries the same block, so its
own binary measures the way the shipped one does.

`cli.run` refuses a composition that registers an id or an extension twice,
by name, before it reads a file.

## Structured symbols

`gramide symbols` and `symbols-recovered` are the versioned JSON that source
readers such as hew consume; [symbols.md](symbols.md) is that schema. The
recovered form is described with the Python package that offers it.
