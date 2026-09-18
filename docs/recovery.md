# Reading a file that does not parse

A strict parse answers whether the file is the language. An editor, an
outline, a repository map ask a different question of a file that is not:
what is still there. This note is how gramide answers it, and how that answer
was measured against tree-sitter's.

## Recover sites

A grammar marks the lists whose members can be given up one at a time —
`recover(item)` inside `rep`, `recover_all` for a whole list — and the parser
in recovering mode reads, at each such site, the item as written.

Before it reads, the recovering parse pairs the file's brackets by kind: a
closer pairs with the nearest open bracket of its kind, and the brackets
open above that one never close. When the brackets do not balance, the
file's indentation has a say. A closer that begins its line, where the
nearest open bracket of its kind stands on a line indented deeper, pairs with
the next one of its kind on a line indented as its own: the nearer ones are
the brackets that lost their closers. The `}` gone from an `if` leaves the
`if`'s `{` unpaired, not the function's. A bracket left unpaired ends, for
the parse, before the first token after it that begins a line indented no
deeper than the bracket's own line, outside every pair opened after it — the
`if`'s next statement; the next `func` after a function whose own `}` went
missing — or before the closer that ends what holds it. A tab and a space
count one each: a file indents one way.

Most of what recovery decides, it reads off that pairing:

- **A bracket that lost its closer.** A sequence that reads an opener the
  pairing left unpaired bounds what it reads after it where that opener
  ends: its lists stop there, and no skip goes past. The closer it then wants
  is taken as there, zero tokens wide. The body of an `if` whose `}` went
  missing holds the lines indented under the `if` and ends; the function
  around it reads on as written, and nothing goes under `ERROR`.
- **A closer the file lacks.** Where the parse wants a `)`, `]` or `}` and
  the token is not it, the closer is taken as there, zero tokens wide, in two
  cases: the token is a closer of another kind that pairs — the next closer
  belongs to something outside, as the `}` after a call that lost its `)`
  inside braces — or the innermost bracket open at that point is one no
  closer answers, so a `)` gone from a call is read as ending where the call
  ends, at the `;`. At the end of the file every bracket still open is such a
  one, so a body an edit left open closes there and keeps what it read.
  Neither applies inside a lookahead or a negation, which ask what the next
  token is; there an opener no closer answers begins nothing.
- **Where a list ends.** A list stops at a closer that pairs with an opener
  before the list began: it ends something the list is inside. A closer that
  pairs inside the list — its opener went under an `ERROR` node — or with
  nothing is one error token, and the list reads on. An item that begins with
  a negation refusing the token, as a case body refuses the next `case`, ends
  its list as a strict read would.

When the item still fails there are two ways on, and a third when the first
read closed brackets at the end of the file:

- **skip.** Find the next place the item rule reads again, no further than
  the closer of the innermost pair around the item (the end of the file for
  `recover_all`), keep whatever head of the failed item is readable on its own
  (the second rule of `recover_keeping`), and put one `ERROR` node over the
  tokens between. A try that fails at an opener the pairing left unpaired
  goes on from where that opener ends: a try from every token inside it would
  read to that same end. A run of tries that each read far before failing is
  one construct read again from every token in it; after 32 tries that read
  more than 64 tokens each, the search goes on from the farthest any failed
  at.
- **repair.** Read the item again with a `)`, `]` or `}` taken as there where
  its first read failed farthest — each of the three is tried, the read with
  the fewest tokens under `ERROR` stands. This is the way for a method whose
  parameter list lost its `)` before its body: the parser wanted `)` where it
  found `{`. It is the analogue of the `MISSING` node an LR recovery inserts,
  one token at a time and only at the item level. Inside a repair under way
  nothing else is repaired, except by items after the repaired place, which
  it cannot reach.
- **close.** A first read that took closers at the end of the file keeps a
  body an edit left open, and it is weighed against skipping. It loses when
  its first `ERROR` begins where the item rule reads: a Go method after a
  function that lost its `}`, read inside the function as a few statements
  and an `ERROR` over `func`, loses few tokens but ends the function too
  late. Otherwise it wins when the skip would read on to the same end — the
  same tokens with fewer of them — or when it puts fewer tokens under
  `ERROR`, counting for the skip what the items it reads on through put
  there.

A site remembers what it worked out, by position: the ways read the item
again, and an enclosing item's ways read everything in it again, so without
the memo a break nested k lists deep would cost the ways to the k-th power.
An answer holds under the bound it was worked out under, and an item read as
written, leaning on nothing, is remembered only by the trials that read it.
The ways are tried without a tree, and the one chosen is read again with the
tree, its items replaying what they worked out. Lists nested more than 256
deep are not read — every `{` an edit typed that no `}` answers opens one
more, and the stack is finite.

The strict parse never takes a closer as there; a file is the language or it
is not. A reader does not run it on a file whose brackets do not balance:
every grammar reads a bracket only as one of a pair, so such a file is not
the language, and what the reader says is wrong with it is the first bracket
the pairing leaves unpaired — ``21493:26: `{` is never closed`` for a `}`
deleted ten lines below it, where a strict read would have read the 3 MB
file to its end to say that it ended. `check` still reads strictly, and
names what it expected where it failed. The incremental reader compares its
result with the recovering whole parse on every breaking edit of the corpora
(`ci/incremental_check.py --breaking`), so the two ways are the same tree by
construction. A body closed zero tokens wide ends at its last item; the line
break after it is the enclosing item's, not that item's.

Python has no closers to take: its blocks are indentation, which the layout
pass turns into `indent` and `dedent` tokens, and a bracket left open joins
every following line into one. Recovering, the layout pass closes such a
bracket where a line begins with a statement word (`def`, `class`, `if`,
`return`, …) at the indentation of the opener's line or less — the tokens
from the opener to that line end become one error token — and a closer of a
kind that is open deeper closes down to it, while one that matches nothing
open is an error token by itself. An f-string that fails inside — a `}`
gone from a replacement field — ends at its line when it opened with one
quote; only one opened with three owns the rest of the file.


## What a broken file costs

Recovery must not turn a large file into a long wait. `bench/recovery_cost.py`
in the TypeScript package breaks `compiler/checker.ts` (3.1 MB, one function
of 2.9 MB) N times at random — a `)` or `}` deleted, a `(` or `{` typed at the
start of a word, up to every place there is one — and times the recovered
outline against the tree-sitter harness, best of three, in seconds, gramide
first ([evidence](https://github.com/O6lvl4/gramide-typescript/blob/main/docs/evidence/recovery-cost-checker-ts.json)):

| breaks | `)` deleted | `}` deleted | `(` typed | `{` typed |
|---|---:|---:|---:|---:|
| 0 | 0.07 / 0.14 | 0.07 / 0.14 | 0.08 / 0.14 | 0.07 / 0.14 |
| 1 | 0.09 / 0.14 | 0.09 / 0.14 | 0.07 / 0.14 | 0.07 / 0.14 |
| 10 | 0.09 / 0.14 | 0.07 / 0.14 | 0.09 / 0.14 | 0.09 / 0.14 |
| 100 | 0.09 / 0.14 | 0.07 / 0.14 | 0.09 / 0.15 | 0.10 / 0.21 |
| 1,000 | 0.09 / 0.34 | 0.04 / 0.14 | 0.10 / 0.38 | 0.12 / 0.19 |
| 10,000 | 0.11 / 0.45 | 0.03 / 0.07 | 0.12 / 0.46 | 0.09 / 0.32 |
| every one there is | 0.11 / 0.43 (31,938) | 0.03 / 0.10 (10,455) | 0.05 / 0.33 (224,949) | 0.12 / 0.89 (224,949) |

A broken file costs gramide at most 0.12 s where the whole one costs 0.08,
and at no count of any kind more than 67% of what it costs tree-sitter.
Three things hold it there. A file whose
brackets do not balance is read once, recovering, with no strict read before
it; the one break that makes the strict read fail at the end of the file
would otherwise read the file twice. A bracket that lost its closer closes
where its indentation ends, so nothing after it is read as its body and no
item fails. And a skip steps over an opener the pairing left unpaired: with
a `(` typed before every word, a try from each token of a line read to the
line's end, and the search cost the square of the line.

It was not always so. At first the read grew faster than the breaks did:
200 `)` deleted cost 2.08 s and 500 cost 7.64 s, against tree-sitter's 0.15
and 0.24 s, since every failed item's resume search and lookahead scanned
the tokens after it, and an unclosed bracket made those scans run to the
end. Before the JavaScript, TypeScript and Rust packages were fixed on
2026-09-18, the lookahead that reads a bracket tree read an opener both as
the group it opens and as a lone token, so an unclosed bracket forked the
read at every opener after it: 2^30 for thirty breaks. A grammar that reads
brackets as a tree must give an opener one reading only.

## What was measured

`bench/recovery.py` in each package breaks every file of its corpus in four
ways, one at a time — a `{` typed at the start of a word, a `}` deleted, a
`)` deleted, a `(` typed at the start of a word — and lists the declarations
each tool still reports: gramide's `outline` (which reads the recovered
parse) and tree-sitter's tree through the same C harness as the timing
comparisons (`--recover`). Each tool is compared with its own listing of the
whole file, by kind, name and start line. A declaration whose lines hold the
break is expected to go; one whose lines do not is *collateral*, and a break
is *clean* when nothing collateral is lost and nothing new appears. Only
files both tools parse whole without error take part; the break kinds keep
the line count so lines stay comparable.

The table below is filled from each package's `docs/evidence/recovery-*.json`
(gramide first, tree-sitter second, on the same breaks):

| corpus | files, breaks | kept: gramide / tree-sitter | clean breaks: gramide / tree-sitter |
|---|---:|---:|---:|
| JavaScript, Node `lib/` | 427, 1,694 | 99.4% / 95.9% | 98.3% / 90.6% |
| TypeScript, TypeScript `src/` | 697, 2,588 | 99.2% / 99.0% | 98.1% / 94.6% |
| Go, Go `src/` | 8,010, 30,927 | 99.8% / 91.1% | 99.3% / 82.9% |
| Rust, Almide compiler `crates/` | 663, 2,632 | 100.0% / 97.5% | 100.0% / 94.9% |
| Python, CPython `Lib/` | 1,450, 5,193 | 99.0% / 96.3% | 98.2% / 82.3% |

gramide is ahead on every kind of break in every language. The indentation
pairing is most of it: a `}` deleted from a JavaScript method once lost the
class or nested what followed into the method, since anything after reads
as a statement; now the method's body ends before the next member, indented
as the method is, and the class reads on — 96.6% of those breaks are clean,
against 82.2% before and tree-sitter's 83.7%, whose LR recovery puts the
brace back by other means. A Go or Rust function whose `}` went missing ends
before the next `func` or `fn` and keeps what it held, where tree-sitter's
cost model nests the rest of the file into the open body. A `)` gone from a
parameter list closes at the `{` after it; a Python bracket or f-string left
open costs one statement where tree-sitter loses the block.
