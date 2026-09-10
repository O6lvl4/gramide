# gramide design

## What it is for

An agent editing code asks a parser two questions, thousands of times a session:

1. Does this file still parse? If not, where does it break?
2. What declarations are in it, and where does each one start and end?

gramide answers those and nothing else. It is not a compiler front end: no name
resolution, no types, no evaluation of string interpolations. Its output is a tree
of `Node { kind, field, start, end, kids }` over token indices, and three commands on
top of it (`check`, `outline`, `tags`), plus `map`, which turns every file's tags into a
ranked, budgeted map of a repository (src/map.almd, a port of the ranking famulus5 used:
reference edges between files, PageRank personalised toward the task's mentions).

## Shape

```
source ──lexer──▶ tokens ──parser(grammar)──▶ tree
```

**A language is data.** One file per language holds two values: a lexer `Spec` and a
`Grammar`. Neither is code that only that language can use, and nothing outside that
file knows the language exists except one branch on the file extension.

**One lexer, with named families.** The driver, the byte helpers and the operator
scanner are shared. What differs between languages is keywords, operators, comment
markers, what a newline means, and the two things a table genuinely cannot describe:
how numbers are written and how string literals end. Those two are *families*, named
constants selecting hand-written scanners that live beside each other in `lex.almd`.
A table that claimed to describe every string syntax would be wrong the first time it
met a Rust `r#"…"#` or a Python f-string, and being wrong about a string is being
wrong about where the code ends. So a new language names a family that fits, or adds
one; everything else about it is data. Go's lexing is 32 lines of spec where it used
to be 229 lines of module.

Rust was the first language added after the split, and it needed two families and one
newline policy: numbers with a type suffix, strings where `r##"…"##` closes only on
the hashes it opened with and `'a` is a lifetime rather than an unterminated
character, and `NL_NONE` for a language that separates with `;` and braces. That is
the shape the design expects. Everything else about Rust is 34 lines of spec.

**Newlines are tokens.** Almide separates statements with newlines, so the grammar has
to see them. The lexer emits one `newline` token per run of blank lines and drops
whitespace and comments. The grammar says where a line may continue: after an
opening bracket, a comma, `=`, `=>`, `then`, `else`, and on either side of a binary
operator. A line-initial `-` glued to its operand (`-1`) is lexed as a distinct `neg`
token, because the compiler treats it as a new statement rather than a subtraction.

**A grammar is a value.** `Grammar { start, rules: Map[String, Rule] }` with

```
Rule = Tok(kind) | Lit(text) | Keep(text) | Ref(name)
     | Seq(rules) | Alt(rules) | Rep(rule) | Rep1(rule) | Opt(rule)
     | Wrap(kind, rule) | Field(name, rule)
     | Not(rule) | Ahead(rule)
     | Left(kind, operand, op)
     | Recover(rule, head) | RecoverAll(rule, head) | Eps
```

`Tok` keeps the token as a leaf, `Lit` matches and drops it, `Keep` keeps punctuation
on purpose (operators inside `binary` nodes). `Wrap` makes a node, `Field` names the
node(s) a rule produced so a caller can ask `child(n, "name")`.

**Ordered choice, no left recursion.** `Alt` commits to the first alternative that
matches, `Rep` is greedy. Expressions are written as a precedence ladder, one rule per
level, each a `Left(kind, operand, op)` that matches `operand (op operand)*` and folds
to the left afterwards. This is what every hand-written parser does; it just happens
to be a value here.

**Errors are the farthest failure.** The parser threads a `State { far, collect }`
through every rule. Whenever a terminal fails at a token index beyond `far`, that
becomes the new `far`. When the start rule fails, the error is "unexpected X at `far`
(expected …)"; that position is where a human would say the syntax breaks. What was
expected there is gathered by a second parse, since a file that parses never needs it.

**A grammar says where to carry on.** `Recover` and `RecoverAll` mark an item of a
list that a reader would rather skip than lose the list over, and name a prefix of it
worth keeping on its own. They do nothing on a strict parse. See "Error recovery".

**A name says what owns it.** `outline` and `tags` print one line per declaration, and
that line is read on its own — in a repo map, in a grep, in a flat list of a file's
symbols. `fn as_str` is worth nothing there; `Applicability::as_str` is the answer.
So a function is named with the type that owns it, found one of two ways: the nearest
enclosing `impl`, `type_spec` or `protocol_declaration` (Rust, and a trait's methods),
or the `receiver` field (Go, which writes the owner in the signature instead of by
nesting). A `mod` is deliberately not an owner: a module is a path, not a type, and
prefixing every function in a file with it would say nothing. Neither is a function
body, so a helper written inside a method is not a method.

The separator — `::` or `.` — is the third field of a `Language`, beside the lexer
spec and the grammar, because neither of those carries it. `src/tags.almd` knows no
language: it knows the node kinds in `decl_kind`, the fields `name`, `field` and
`receiver`, and nothing else.

**Offsets are bytes.** A token's `start` and `end` count bytes, because the lexer
reads bytes. `string.slice` counts characters. Cutting a name out of the source with
token offsets therefore works until a file has a `—` in a comment above it, and then
it is wrong by one byte per non-ASCII character — silently, and only on the files
least likely to be in a test. Names are joined from their tokens instead
(`tree.span_text`); `tree.text_of`, which is the only thing that needs the whitespace
between tokens, cuts the source as bytes and says what that costs.

## What the native backend taught the engine

Every one of these showed up as a corpus run that did not finish. Each is a
rule about how Almide's native backend copies values, verified by reading the
generated Rust, and each is now a comment at the place in the code it shaped.

**No re-parsing in the grammar.** Ordered choice is only linear if alternatives fail
early. `stmt = assign | expr` re-parsed the whole expression after failing on `=`, and
`[a, …]` tried the map form first, parsing the first element fully before failing on
`:`. Each doubled the work per nesting level. Both now parse the shared prefix once and
let the next token decide.

**One self-recursive engine function.** A list or record parameter is passed by
reference only when the function is not part of a mutually recursive group
(almide/almide#2040). With `parse_rule` calling four helpers, every call cloned the
grammar and the token list: 21 s for a 280-line file. Sequence, choice, repetition and
the left fold are loops inside `parse_rule`; 0.15 s.

**No closure reads a captured list.** A lambda that reads a captured `var` clones it
per call. Both lexers had a `push` closure reading `bytes` and a `list.find` lambda in
the operator scanner: quadratic lexing, 55 s for 32k lines. Plain loops and top-level
helpers; 0.3 s.

**Helpers that take the big list live in the same module, and never hand it to a
consumer.** A call into another module, or to a consuming stdlib function such as
`list.slice`, marks the parameter owned and the whole list is cloned at every call.
The byte helpers are duplicated per lexer module and build token text with `list.get`.
Likewise `x ?? fallback` on anything holding the parameter marks it escaping; a
`match` does not.

**The grammar runs compiled.** A `Rule` value is what an author writes; the engine
runs on a flat arena of three-integer nodes with texts in a parallel list and every
`Ref` resolved to an index. A node visit copies twelve bytes. Running on the `Rule`
tree cloned a sub-grammar at every reference, and the parser state's `expected` list
held strings that were copied on every call; it now holds node ids and renders them
only for an error. Together: a 116k-line Go file from 188 s to 7.6 s.

**Nothing that repeats compares strings.** `compile` numbers every distinct text a
terminal asks for, and the token stream is numbered against the same table once per
parse. A terminal match is an integer compare, and the engine never reads the token
record, so it never copies a value that owns two strings. This is also the way round
a backend that renders `t.kind == want` as a clone of both operands (almide/almide#2066)
and `list.get` as a copy of the element (almide/almide#2070).

**A result carries no nodes.** A rule pushes what it built onto one list the caller
owns and hands down, and a rule that fails truncates that list back to where it found
it. Returning the nodes meant every sequence copied its children into its parent, once
per level of nesting, and naming a node rebuilt its whole subtree; a single chain of
4,000 operators took 2.17 s and quadrupled with each doubling. It is now linear and
takes 0.01 s. `list.pop` moves the element out, where `list.reverse`, `list.set` and
`list.slice` all copy the list, so a drain of two pops and two pushes per node beats
one copy of a subtree.

**Nothing per call holds a list.** The parser state is two integers. What was expected
at the farthest failure moves to a list the caller owns, which is right on its own
terms because that set only ever moves forward and backtracking never has to undo it.
The set is filled only on a second pass, which a file that parses never runs.

**Compiling is per grammar, not per file.** `emit` appends to the arena it is given
rather than building a private one and copying it up, and `parse_with` takes a grammar
that is already compiled. `check` and `balance` take any number of files. The whole
validation corpus, 11,364 files, went from 159 s at the start of this work to 18 s.

## What is measured

**Almide.** Every `.almd` file in the Almide repository, excluding `research/grammar-lab` (syntax
experiments in deliberately non-Almide forms) and `docs/roadmap` (pseudo-code with
`...` placeholders):

- 3,317 well-formed files: all parse.
- 65 `broken.almd` fixtures are rejected. Each is also rejected by `almide check`, 57
  as parse errors and 8 with a targeted syntax diagnostic (retired `..` ranges,
  `let … in`, `let rec`, `??` without a fallback).
- 720 other `broken.almd` fixtures parse and fail later in the compiler, as intended.

**Rust.** Every `.rs` file under `crates`, `tests`, `runtime`, `src` and `tools` of the
Almide compiler (827 files, 15.7 MB):

- 826 files parse. `rustfmt --edition 2024` accepts exactly those 826.
- The one file `rustfmt` rejects, for using `gen` as a name in an edition that reserves
  it, gramide accepts. That is a name resolution question, not a syntax one.
- 15.7 MB in 2.4 s on one core, 6.6 MB/s, the same as the Go grammar.

**Go.** Every `.go` file under `GOROOT/src` of Go 1.27 (8,077 files):

- 8,042 files parse.
- 35 files, all under `testdata`, are rejected; `gofmt -e` rejects every one of them.
- 11 `testdata` files that `gofmt -e` rejects parse (permissiveness, listed below).

The guarantee this establishes runs one way for both languages: a file gramide rejects
is broken for the reference parser too. That is the direction a syntax gate needs.

## Known permissiveness

Files gramide accepts that the compiler rejects at parse time (11 fixtures):

- chained comparisons `a < b < c` (compiler: non-associative)
- `|>` with an arbitrary right-hand side (compiler: a single postfix chain)
- `f<Int>(x)` angle-bracket generics
- `t.0.1` chained tuple index (lexes `0.1` as a float)
- a positional argument after a named one
- `todo` without a string argument
- `@attr(x = -1)` negative attribute arguments
- some `fan.bounded` argument shapes

And by design: the inside of `${…}` interpolations is not parsed; two statements on
one line without a separator are accepted (the compiler accepts `let m = n * 2 m + 1`
as well).

For Go, the 11 `testdata` files `gofmt` rejects and gramide accepts fail counting or
character rules the grammar does not enforce: more than two expressions in a `range`
clause, an empty type-parameter list `[]`, an empty type-argument list, a parameter
list mixing named and unnamed parameters, `go` with a non-call or parenthesized
expression, and a non-ASCII character (`☹`) that the lexer accepts as an identifier.

## `balance`: a gate for the languages without a grammar

A parser is the right gate, and there is one for Almide and Go. For everything else
the honest options are no gate, or the language's compiler — which needs the whole
project to tell a syntax error from a missing symbol, and one that refuses a correct
edit is worse than none.

`gramide balance` is the third option. It lexes a C-family file (line and block
comments, string, character, backtick and raw-string literals, Java text blocks) and
asks two questions a valid file always answers yes to: do `()`, `[]` and `{}` balance
and nest, and does every literal and comment close. A rejection is therefore never
wrong, and the failures it catches are the ones that actually happen — a generation
that stopped halfway, a markdown fence, a paragraph of prose where a file should be.
It cannot see a missing semicolon and does not claim to.

Measured on all 8,077 `.go` files under `GOROOT/src`: 8,075 balanced, one directory,
and one rejection — a deliberately malformed compiler fixture that `gofmt -e` also
rejects. No false rejection.

## How fast, against something honest

1,500 Go files, 25,549,317 bytes, one core, one process each, alternating runs.
`gofmt -e` is the fair comparison: it is a hand-written recursive descent parser for
the same language, and `-e` makes it report every syntax error rather than the first.
`GOMAXPROCS=1` because gofmt parallelises across its file arguments by default and
gramide cannot yet ask for a second core (almide#2080).

| | 2026-09-10 | rate |
|---|---|---|
| `gofmt -e -l`, `GOMAXPROCS=1` | 1.30 s | 19.6 MB/s |
| `gramide check` | 2.74 s | 9.3 MB/s |

**About twice as slow as the reference parser for the language**, interpreting a grammar
value rather than running code generated from one. It was 27x slower when this work
started and 4.3x slower earlier the same day.

The same day's two changes, separated:

| | Go 25.5 MB |
|---|---|
| before | 5.60 s |
| + caching the lexer's operator patterns and a compact `Bytes` source | 3.03 s |
| + Almide's own byte-slice and ownership work on top | 2.74 s |

Against tree-sitter, which is the other reference worth having — `ctxgate-outline`, a C
tree-sitter binary, against `gramide outline`, 120 Rust files, 2,951,900 bytes, process
startup (0.33 s for 120 processes, the same for both) subtracted:

| | |
|---|---|
| tree-sitter | 0.155 s |
| gramide, before | 0.73 s |
| gramide, now | 0.333 s |

Also about 2x, from 4.7x. Peak RSS on a 3.95 MB file went 180.8 MiB to 160.1 MiB.

What none of this changes: tree-sitter has 371 languages to gramide's three, and
incremental parsing, which gramide does not have at all. Speed was never the gap that
mattered most.

Where a run of `gramide check` spends its time, same corpus, one process per file:

| | |
|---|---|
| process startup | 0.16 s |
| compiling the grammar | 0.05 s |
| lexing | 0.04 s |
| parsing | 0.13 s |

Two things follow. Parsing is no longer the largest item for a per-file run, which is
why `check` takes many files at a time. And the remaining gap to `gofmt` is not one
missing trick: it is that every value the engine touches is copied, which is the cost
of the property that makes the grammar editable at runtime.

## Where the time went, and what the profile got wrong

Measured 2026-09-10 with `sample` on a release build, one 3.95 MB Go file, so that the
per-file costs above do not dominate. The first profile said `check` splits 70% lexing,
8% numbering the token stream, 22% parsing — **the parser was not the bottleneck, the
lexer was** — and that 84% of the lexer's time was `malloc` / `free` / `memmove` rather
than the lexer:

```
_xzm_free                 1008        <- top of stack
_xzm_xzone_malloc          380
_malloc_zone_malloc        276
lex::tokenize_with         228        <- the actual lexer
almide_rt_string_to_bytes  153
String::clone              132
```

The conclusion drawn from that was wrong, and it is worth writing down why. The reading
was "the allocations are the `Token` record and the byte list, so the representation has
to change and this is a language problem". The actual cause was **the lexer rebuilding
its operator byte patterns on every token**: an allocation probe counted 22,961,527
allocation requests for this file, and caching the patterns once per tokenization and
storing the source in a compact `Bytes` took that to 2,612,801 — 88.6% fewer — without
touching `Token` or `String` at all. Lexing this file went from 0.52 s to 0.105 s, five
times faster, and the split is now roughly a third lexing to two thirds numbering and
parsing.

The lesson is not "profile first" — the profile was right about *where*. It is that
"84% of the time is in malloc" says nothing about *which* allocations, and the four
representation changes tried before finding the real one measured 0%, 0%, 0% and 0%
(below). A profile that names the allocator names the symptom; the count of allocations
per input, attributed to a call site, names the cause.

What is left on the same file: the allocator is still the largest single item but no
longer dominant, and `AlmideMap::position` now shows up — that is the two map lookups
per token in `kind_ids` and `text_ids`, which the lexer could hand over for free because
it already knows which keyword or operator it matched.

The two representation costs below are real and still filed; they are simply not what
this input was spending its time on.

`string.to_bytes` returns
`List[Int]`, which is `Vec<i64>`, so reading a 3.95 MB source allocates 31.6 MB — and it
is the only byte-accurate accessor a string has, because `string.slice` counts
characters. And a `Token` owns two `String`s, which gives the whole token list a
per-element destructor. Both are filed: almide#2077, almide#2078.

The negative results are worth as much as the positive one, because each looked
obviously right:

| change | effect on `check` |
|---|---|
| interning the tree's `kind` and `field` strings | **0%** |
| pre-sizing the per-node child vectors | **0%** |
| pre-sizing the token vector | **0%** |
| dropping `Token.text` alone | **0%** |
| making `Token.kind` scalar alone | 4% of lexing |
| **both at once — no heap in the record** | **13% of lexing** |
| rebuilding against the fixed almide#2066–#2070 | **0%** |

The last row is the one to remember. Every clone those issues describe was fixed
upstream, and gramide got nothing, because the engine had already been written around
each of them — see "What the native backend taught the engine". A workaround does not
stop costing once the bug is fixed; it stops being needed.

The row above it is a real shape: removing one of a record's two owned fields is worth
nothing and removing both is worth 13%, because a record with any owned field gives its
whole list a per-element destructor. It is still true. It was simply the wrong 13% to be
chasing while an 88.6% allocation reduction sat in the operator scanner.

One more measurement, because it decides how much a second core would be worth:
`fan { }` is specified as native threads, and it is not — eight CPU-bound arms take the
same wall time as a `for` loop, and `user` never exceeds `real` (almide#2080). `gofmt`
parallelises across its file arguments by default; the comparison above pins it to one
core so that it is fair, but in ordinary use it keeps fourteen and gramide cannot ask
for a second.

## Error recovery

A file an agent is halfway through editing usually does not parse, and it is the file
the agent most needs to read. So a reader that fails asks a second time, recovering.

The grammar says where recovery is worth attempting, with `recover` on an item of a
list inside brackets and `recover_all` on an item of the file itself. Both are
transparent when nothing goes wrong: they produce no node of their own, and the strict
parse behaves exactly as if they were not there. On a recovering parse, an item that
fails is retried at each following position until it reads again; the tokens given up
become one `ERROR` node, and the list carries on. The skip stops at end of file, and
for `recover` also at a closing bracket that belongs to something outside, so a
statement list can never recover by eating the brace that ends it. A run of separators
is not an error, so giving up at the end of a list leaves no node.

The lexer recovers too, because the ordinary state of a file someone is typing into is
an unterminated string. `tokenize_recovering` turns each run it cannot read into an
`error` token, which no grammar rule asks for, so the parser's recovery gives up on the
smallest enclosing list rather than on the file.

A declaration whose signature is half-typed keeps its name. `recover_all_keeping`
names a second rule, a prefix of the item worth having on its own, and recovery reads
it at the failure point before writing the ERROR node over the rest. Each grammar has
a `decl_head` rule for this: `func` and a name, `type` and a name, and so on. So
`func Beta(y int` with the rest still unwritten appears in the outline as
`L5-5 function Beta`, which is the state a file is in for most of the time anyone is
editing it.

What this buys, on the 102 files of the validation corpus that do not parse: 99 give an
outline, 684 declarations in total. The three that give nothing are a directory, an
empty file, and a file of English prose named `.go` — in each case there is no Go
before the first thing that fails. Recovery costs about 14 ms on a 130 KB file that
fails, and nothing at all on a file that parses.

`check` never recovers. It is the gate, its exit code is a verdict, and its output on
all 39,021 corpus files is byte-identical to the engine before recovery existed.
`parse`, `outline`, `tags` and `map` all recover, and say so: the reason goes to stderr
and, for `map`, into the notes under the map.

`check` also builds no tree. Whether a rule matches never depended on the nodes it made
— the tree is output — so `parser.verify` runs the same engine with `build: false` and
every `Wrap`, `Field` and leaf becomes a no-op. That is the whole difference between the
gate and a reader. On the 25.5 MB Go corpus, alternating runs: 5.805 s against 5.563 s,
4.2%, and `check` output stays byte-identical on all 39,021 files. It matters more than
the number: `check` is what an agent runs on every write, and it was building and
throwing away a syntax tree each time.

## Next

1. Recovery inside a block, so a half-typed statement costs its statement rather than
   the run of statements after it.
2. Memoisation of `Ref` results per (rule, position) if a grammar ever needs it; none
   does so far.
