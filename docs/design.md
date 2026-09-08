# gramide design

## What it is for

An agent editing code asks a parser two questions, thousands of times a session:

1. Does this file still parse? If not, where does it break?
2. What declarations are in it, and where does each one start and end?

gramide answers those and nothing else. It is not a compiler front end: no name
resolution, no types, no evaluation of string interpolations. Its output is a tree
of `Node { kind, field, start, end, kids }` over token indices, and three commands on
top of it (`check`, `outline`, `parse`).

## Shape

```
source ──lexer──▶ tokens ──parser(grammar)──▶ tree
```

**Lexer per language, parser shared.** Every language has two or three places where a
table-driven lexer cannot say what happens (string interpolation, heredocs, nested
comments), and those are exactly the places a syntax check must get right. So the
lexer is hand-written per language, over bytes, and the parser above it is generic.

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
     | Left(kind, operand, op) | Eps
```

`Tok` keeps the token as a leaf, `Lit` matches and drops it, `Keep` keeps punctuation
on purpose (operators inside `binary` nodes). `Wrap` makes a node, `Field` names the
node(s) a rule produced so a caller can ask `child(n, "name")`.

**Ordered choice, no left recursion.** `Alt` commits to the first alternative that
matches, `Rep` is greedy. Expressions are written as a precedence ladder, one rule per
level, each a `Left(kind, operand, op)` that matches `operand (op operand)*` and folds
to the left afterwards. This is what every hand-written parser does; it just happens
to be a value here.

**Errors are the farthest failure.** The parser threads a `State { far, expected }`
through every rule. Whenever a terminal fails at a token index beyond `far`, that
becomes the new `far` and the expectation list restarts; at the same index the
expectation is appended. When the start rule fails, the error is "unexpected X at
`far` (expected …)". That position is where a human would say the syntax breaks.

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

## What is measured

**Almide.** Every `.almd` file in the Almide repository, excluding `research/grammar-lab` (syntax
experiments in deliberately non-Almide forms) and `docs/roadmap` (pseudo-code with
`...` placeholders):

- 3,317 well-formed files: all parse.
- 65 `broken.almd` fixtures are rejected. Each is also rejected by `almide check`, 57
  as parse errors and 8 with a targeted syntax diagnostic (retired `..` ranges,
  `let … in`, `let rec`, `??` without a fallback).
- 720 other `broken.almd` fixtures parse and fail later in the compiler, as intended.

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

## Next

1. Memoisation of `Ref` results per (rule, position) if a grammar ever needs it; none
   does so far.
