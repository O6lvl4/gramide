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

## Two rules that cost a day each

**No re-parsing in the grammar.** Ordered choice is only linear if alternatives fail
early. Two places in the first draft of the Almide grammar did not: `stmt = assign |
expr` re-parsed the whole expression after failing on `=`, and `[a, …]` tried the
map form (`[k: v]`) first, parsing the first element fully before failing on `:`.
Each doubled the work per nesting level, which is exponential in nesting depth. Both
were rewritten so the shared prefix is parsed once and the token after it decides
(`expr ("=" expr)?`, `"[" expr (":" … | "," …)`).

**One self-recursive engine function.** The Almide native backend passes a list or
record parameter by reference (`&[T]`, `&G`) only when the function is not part of a
mutually recursive group. With `parse_rule` calling `parse_seq`, `parse_alt`,
`parse_many` and `fold_left`, every call cloned the whole grammar and the whole token
list: a 280-line file took 21 s. Sequence, choice, repetition and the left fold are
now loops inside `parse_rule`; the same file takes 0.15 s and the 3,382-file Almide
corpus 7 s on 8 cores.

## What is measured

Every `.almd` file in the Almide repository, excluding `research/grammar-lab` (syntax
experiments in deliberately non-Almide forms) and `docs/roadmap` (pseudo-code with
`...` placeholders):

- 3,317 well-formed files: all parse.
- 65 `broken.almd` fixtures are rejected. Each is also rejected by `almide check`, 57
  as parse errors and 8 with a targeted syntax diagnostic (retired `..` ranges,
  `let … in`, `let rec`, `??` without a fallback).
- 720 other `broken.almd` fixtures parse and fail later in the compiler, as intended.

The guarantee this establishes runs one way: a file gramide rejects is broken for the
compiler too. That is the direction a syntax gate needs.

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

## Next

1. `outline` fields for references (calls, type mentions) so an agent can rank files
   by what they mention.
2. A second language, to prove the lexer/parser split holds.
3. Memoisation of `Ref` results per (rule, position) if a grammar ever needs it; none
   does so far.
