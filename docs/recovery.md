# Reading a file that does not parse

A strict parse answers whether the file is the language. An editor, an
outline, a repository map ask a different question of a file that is not:
what is still there. This note is how gramide answers it, and how that answer
was measured against tree-sitter's.

## Recover sites

A grammar marks the lists whose members can be given up one at a time —
`recover(item)` inside `rep`, `recover_all` for a whole list — and the parser
in recovering mode tries, at each such site, the item as written. When the
item fails there are three ways on, and the site takes the one that puts
fewer tokens under an `ERROR` node:

- **skip.** Find the next place the item rule reads again (bounded by the
  enclosing closer for `recover`, by the end of the list for `recover_all`),
  keep whatever head of the failed item is readable on its own (the second
  rule of `recover_keeping`), and put one `ERROR` node over the tokens
  between. This is the way for a Go file whose function lost its `}`: nothing
  inside a Go body reads as a top-level declaration, so the next `func` is the
  resume point and only the broken function is lost.
- **close.** Read the item again with the closers it wants at the end of the
  file — `)`, `]`, `}` — taken as there, zero tokens wide, so that the body an
  edit left open closes at the end and keeps what it read, with `ERROR` nodes
  inside it for what its own lists could not read. This is the way for a
  JavaScript class whose method lost its `}`: everything after the break reads
  as a statement, so skipping would resume a few tokens on and drop the class
  with every method before the break; closing keeps the class and its methods
  and loses only what follows the break.
- **repair.** Read the item once more in collecting mode to learn where it
  failed farthest, and read it again with a `)`, `]` or `}` taken as there at
  that place, zero tokens wide — each of the three is tried, the read with
  the fewest tokens under `ERROR` stands. This is the way for a method whose
  parameter list lost its `)`: the parser wanted `)` where it found `:`, and
  with one taken as there the member reads whole, where skipping resumed
  inside the member and let its `}` close the class. It is the analogue of
  the `MISSING` node an LR recovery inserts, one token at a time and only at
  the item level. Nothing is tried inside a repair already under way.

The strict parse never takes a closer as there; a file is the language or it
is not. The incremental reader compares its result with the recovering whole
parse on every breaking edit of the corpora (`ci/incremental_check.py
--breaking`), so the two ways are the same tree by construction.

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
in the TypeScript package deletes N `)` at random from `compiler/checker.ts`
(3.1 MB, one function of 2.9 MB) and times the recovered outline against the
tree-sitter harness, best of three ([evidence](https://github.com/O6lvl4/gramide-typescript/blob/main/docs/evidence/recovery-cost-checker-ts.json)):

| `)` deleted | gramide | tree-sitter | outline lines (intact: 2,650) |
|---:|---:|---:|---:|
| 0 | 0.07 s | 0.14 s | 2,650 |
| 50 | 0.12 s | 0.14 s | 2,650 |
| 100 | 0.13 s | 0.14 s | 2,650 |
| 200 | 2.08 s | 0.15 s | 2,925 |
| 500 | 7.64 s | 0.24 s | 2,898 |

Up to a hundred breaks the read costs what an intact read costs; past that
it grows faster than the breaks do, since every failed item's resume search
and lookahead scan the tokens after it, and an unclosed bracket makes those
scans run to the end. tree-sitter's cost stays flat. Before the JavaScript,
TypeScript and Rust packages were fixed on 2026-09-18, the lookahead that
reads a bracket tree read an opener both as the group it opens and as a lone
token, so an unclosed bracket forked the read at every opener after it:
2^30 for thirty breaks, and this file at two hundred did not finish in ten
minutes. A grammar that reads brackets as a tree must give an opener one
reading only.

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
| JavaScript, Node `lib/` | 427, 1,694 | 96.1% / 95.9% | 92.1% / 90.6% |
| TypeScript, TypeScript `src/` | 697, 2,588 | 98.2% / 99.0% | 95.2% / 94.6% |
| Go, Go `src/` | 8,010, 30,927 | 99.7% / 91.1% | 99.2% / 82.9% |
| Rust, Almide compiler `crates/` | 663, 2,632 | 99.9% / 97.5% | 99.8% / 94.9% |
| Python, CPython `Lib/` | 1,450, 5,193 | 98.9% / 96.3% | 98.1% / 82.3% |

Where tree-sitter still keeps more the shape is one: a `}` deleted from a
JavaScript or TypeScript method. The class body runs on, and since anything
after reads as a statement, skipping resumes right after the `class` keyword
and the class is gone, while closing at the end keeps it but nests what
follows; a repair cannot help, since the failure is at the end of the file.
tree-sitter's LR recovery can put the missing brace where it belongs. On
every other kind of break gramide is ahead: a Go or Rust file whose `}` went
missing resumes at the next `func` or `fn` and loses that one item, where
tree-sitter's cost model nests the rest of the file into the open body; a
`)` gone from a parameter list is repaired; a Python bracket or f-string
left open costs one statement where tree-sitter loses the block.
