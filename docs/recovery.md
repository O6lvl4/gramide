# Reading a file that does not parse

A strict parse answers whether the file is the language. An editor, an
outline, a repository map ask a different question of a file that is not:
what is still there. This note is how gramide answers it, and how that answer
was measured against tree-sitter's.

## Recover sites

A grammar marks the lists whose members can be given up one at a time —
`recover(item)` inside `rep`, `recover_all` for a whole list — and the parser
in recovering mode tries, at each such site, the item as written. When the
item fails there are two ways on, and the site takes the one that puts fewer
tokens under an `ERROR` node:

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
| JavaScript, Node `lib/` | 427, 1,694 | 94.3% / 95.9% | 89.7% / 90.6% |
| TypeScript, TypeScript `src/` | 697, 2,588 | 97.3% / 99.0% | 91.5% / 94.6% |
| Go, Go `src/` | 8,010, 30,927 | 99.5% / 91.1% | 99.0% / 82.9% |
| Rust, Almide compiler `crates/` | 663, 2,632 | 99.9% / 97.5% | 99.8% / 94.9% |
| Python, CPython `Lib/` | 1,450, 5,193 | 98.9% / 96.3% | 98.1% / 82.3% |

Where tree-sitter is ahead the shape is the same each time: a break inside
a member of a brace-delimited body. A `)` deleted in a TypeScript method's
parameter list makes the member fail; the skip resumes a few tokens on,
inside the method (`file: string` reads as a field), and the method's `}`
then closes the class, so every member after it is read as top-level
statements. A `}` deleted from a JavaScript method lets the class body run
on, and since anything reads as a statement the skip resumes right after the
`class` keyword and the class is gone; closing at the end keeps it but nests
what follows. tree-sitter's LR recovery can put the missing token where it
belongs. Where gramide is ahead the item is the reason again: a Go or Rust
file whose `}` went missing resumes at the next `func` or `fn` and loses
that one item, where tree-sitter's cost model nests the rest of the file
into the open body; and a Python bracket or f-string left open costs one
statement where tree-sitter loses the block.
