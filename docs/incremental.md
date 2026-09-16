# Reading a file after an edit

The whole parse gives a tree whose token indices, byte offsets and lines
are absolute. Kept that way, an edit near the top of a file moves every
number after it, which costs the whole file again. `src/incremental.almd`
keeps the file differently, and this note is the model.

## Units

The parser stamps every node that a `recover` or `recover_all` site read
as one node with that site, in the node's `field` below -1 (where no field
name lives; a reader of fields compares against names, which are never
negative, and the s-expression prints a negative field as none). Those
nodes are the *units*: in JavaScript and TypeScript, every top-level
declaration and every statement or class member inside braces.

`from_parsed` cuts the tree at the units. A unit keeps:

- its own tokens, in *pieces*: the run before its first child, the runs
  between children, the run after the last. Offsets, lines and columns in
  a piece are relative to where the piece starts; the piece also knows its
  size in bytes, its line breaks, and the bytes after the last break, which
  is what the next base needs;
- its subtree, with each child unit replaced by a placeholder node that
  takes one slot of the unit's own token space (piece 0, child 0, piece 1,
  child 1, …);
- its children, and beside them the children's totals — bytes, lines, tail,
  tokens, first token, kind — so that finding the way through a unit reads
  integers and never a child.

A unit's tokens run from its first token to the first token after its
separators (a line break, a `;`), never into the next child: a recovered
parse can resume on a `;` right after an `ERROR` item.

## An edit

`reparse` walks down from the file: at each unit, the child whose bytes
hold the edit is found by summing sizes; if the edit lies inside that
child and not at its first byte, the child tries first. A unit whose own
tokens hold the edit answers "me", and its parent re-reads a window of
siblings: that child, the child before it when the edit is at its first
byte and nothing of the parent's own stands between (an inserted `+` can
join two statements), and the children up to the edit's end.

The window's bytes are re-lexed from the first child's start through the
first token after the window — the parent's own (`}`, `else`, the EOF)
when any follow, else the next child's head — and parsed with the site's
body until the parser reaches that token. The token must come out as it
was; the items must end exactly there; every item must advance. Otherwise
the answer is `false` and the caller parses the whole file. Two more cases
read the whole file: an edit beside an `ERROR` item in the same list,
because recovery is not local, and a file with no items.

When the window parses, its nodes are cut into units the same way, the
parent's placeholders are renumbered and the pieces between them
re-counted, and the totals along the path are summed again.

## The check

`materialize` puts the file back together — every token with its absolute
position, every placeholder replaced — and `same` compares that with a
whole parse of the same text, token for token and node for node. The
engine's tests hold it on a small language; `reparse-bench --verify K`
holds it every K edits on any file; and each language package's
`ci/incremental_check.py` holds it on every edit of a random sequence
over its corpora, in normal mode and in `--breaking` mode, where every
tenth edit inserts an unmatched brace and the check runs against the
recovering whole parse.

## What it costs

The same edit sequence, in-process, for gramide's `reparse` and for
tree-sitter's `ts_tree_edit` + reparse (the C harness in each package's
`bench/tree_sitter_ranges.c`): a letter typed or deleted six letters into
a word of thirteen or more, so the file stays what it was syntactically.
Medians over 1,000 edits, and the whole parse of the same file:

| file | gramide | tree-sitter | whole parse |
|---|---:|---:|---:|
| Node `internal/quic/quic.js` (190 KB) | 41 µs | 105 µs | 3.4 ms |
| TypeScript `compiler/parser.ts` (540 KB) | 75 µs | 128 µs | 9.5 ms |
| TypeScript `compiler/checker.ts` (3.1 MB) | 126 µs | 565 µs | 57 ms |
| Excalidraw `components/App.tsx` (465 KB) | 72 µs | 220 µs | 9.4 ms |

The evidence is in each package's `docs/evidence/incremental-*.json`.

## What it does not do

Node identity across edits: the tree after an edit is a new tree, and a
reader that kept a node from before cannot find it again. Readers that
want absolute positions materialize the file, one pass and no parsing.
Both are the next thing, not this one.
