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
- its children, whose totals — bytes, lines, tail, tokens, first token,
  kind — are read where each child stands: a child is borrowed to read
  them, never copied, so finding the way through a unit costs integers;
- the ids of the nodes of its own subtree, in preorder, placeholders left
  out.

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

Two shapes of grammar need care here, and the Go and Almide packages have
both. A scanner may close its input with an empty separator (Go's automatic
`;`, Almide's line end): it lands after the head token in the re-lexed
slice and is dropped before the head is compared. And a file or block rule
may read its first item at one recover site and `sep item` at another, so
that the two sites are partners and the separators between items belong to
no item rule: the window is read with the bare item's body, skipping the
separators (which `build` gives to the item before), and its first item is
stamped with the site of the child it replaces, the rest with that site's
partner. An item holding several statement lists (an `if` with two blocks)
has children from each, so the first-of-list role is per child; when a
window empties and it had replaced a list's first item, the child now in
its place takes that role.

An edit that touches no token at all — in a comment, in blank space —
reads no item. A comment is no token, so such an edit lies in one of a
unit's own runs, between two of its tokens or after the last (the doc
comment before an item lies in the bytes of the item before it, whose
range runs to the next head). That run alone is lexed again and must give
the same tokens, kind for kind and length for length; then only its sizes
and its tokens' positions change. A comment the edit opens or closes gives
other tokens, or none, or a scanner error (an unterminated block comment
is an error in strict mode in every package's scanner), and the ordinary
path follows. A line comment the edit opens runs to the end of its line,
so the run must hold that line's end (or end the file) for the check to
see what it swallows; otherwise the ordinary path. The comparison is over
the tokens that carry text: a scanner's layout tokens — a line end, which
JavaScript's scanner gives the break's own length and leaves out when
nothing follows it to separate, an indent, a dedent, the EOF — are the
run's own as they were, moved by the edit. What such an edit costs is the
lex of the run that holds it, so it grows with the comment: the block of
`@typedef` comments at the top of Node's `quic.js` is one run of 20 KB,
and an edit inside it is 50 µs where the file's median edit is 6.

The same path takes an edit that touches exactly one token — a letter
typed into a name, or put right after it, or deleted from it — when the run
lexes again to the same tokens with only that one longer or shorter. What
the parser reads of a token is its kind and the grammar literal its text
spells (a contextual keyword such as `type` is a name that spells one), so
each run keeps that atom per token, and a retyped token may neither spell
a literal before nor after; then the tree is the same tree and only
positions move. A token that changes kind, splits, or joins its neighbour
gives other tokens and the ordinary path follows.

A slice is lexed as the line it stands on: the blank space before it on
its line goes in front, so that a scanner reading layout (Python's
indentation) sees it at its depth, and the `indent` it then opens with,
and the `dedent`s it closes with beyond what the window had, are the
file's around it and are dropped. Python's statements are `recover_lines`
items and are stamped like the others.

Every item carries an id. An item that is not read again keeps it — a
retyped name or a comment edit renames nothing — and an item read again
keeps it when it comes out the same (kind, token count, size) in a window
that read several, or whatever came out when the window read it alone in
place of itself. Only what is new is named anew. `items` lists the
document's items with their ids and absolute ranges; `reparse-bench`
counts, per edit, how many items lost their id.

Every node carries an id too, and an id stands for one text: a node keeps
its id exactly when the edit left its text alone — the same kind over the
same bytes, where they were or moved by the edit — and a node whose text
the edit changed is named anew. That is, in a window read again, each
node that did not come out as it was; and on the way down to the edit,
every node that holds it, up to the file's own. So an id seen again is
the node it was, and a reader may keep what it knew about it. A node that
ends where the edit starts, or starts where it ends, holds nothing of it:
a letter typed onto it makes a longer node, which is new. No id is given
twice, not even when an edit cannot be read in and the file is read
whole: `rebuilt` numbers on from the old document and keeps every id the
rule keeps. `node_ids` lists the ids in the preorder of the tree
`materialize` gives, and `reparse --nodes` prints every node with its id
and how many ids the edit left as they were. `reparse-bench --verify K`
holds the rule against the whole trees before and after every K-th edit,
and counts how many nodes each of those edits renamed: on `checker.ts`,
15 of its 338,851 at the median, the nodes that hold the letter typed.

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
| Node `internal/quic/quic.js` (190 KB) | 5.8 µs | 101 µs | 3.3 ms |
| TypeScript `compiler/parser.ts` (540 KB) | 15 µs | 120 µs | 9.1 ms |
| TypeScript `compiler/checker.ts` (3.1 MB) | 54 µs | 561 µs | 58 ms |
| Excalidraw `components/App.tsx` (465 KB) | 13 µs | 221 µs | 9.4 ms |
| Go `net/http/server.go` (140 KB) | 10 µs | 150 µs | 1.5 ms |
| Rust `lower/expressions.rs` (92 KB) | 4.6 µs | 53 µs | 1.6 ms |
| Python `argparse.py` (107 KB) | 5.1 µs | 44 µs | 2.6 ms |

Most of a median edit is now the lexing of one run and the walk down to
it; what it was before — 30 to 50 µs on every file — was the Almide
backend cloning the compiled grammar into each call along the way, which
a `mut` parameter (passed by reference) removed, and the run's tokens
being cloned to read their measures. Integer lists beside the runs and
children stopped that once; reading each measure where it stands, in a
function whose whole body is the read (`match list.get`, which borrows),
stopped it for good, and dropped the lists, which were a third of a
document. Naming the nodes that hold an edit walks each unit on the way
down once more; it is in the numbers above.

The evidence is in each package's `docs/evidence/incremental-*.json`.

## What it holds

A document holds every token once, relative to its run, every node once,
and a few integers per unit; the parse it was cut from goes when it is
cut. Peak resident size of one process, gramide against the tree-sitter
harness, best of three ([evidence](evidence/memory.json), `bench/memory.py`):

| file | `check` | `outline` | read, one edit, read again |
|---|---:|---:|---:|
| TypeScript `compiler/checker.ts` (3.1 MB) | 33.8 / 61.7 | 58.5 / 61.8 | 126.8 / 62.0 |
| TypeScript `compiler/parser.ts` (540 KB) | 8.8 / 13.7 | 13.9 / 13.7 | 27.4 / 13.7 |
| TSX `components/App.tsx` (465 KB) | 8.7 / 12.9 | 13.3 / 12.9 | 25.8 / 13.0 |
| JavaScript `internal/quic/quic.js` (190 KB) | 4.6 / 5.2 | 6.3 / 5.2 | 10.6 / 5.2 |
| Go `ssa/rewriteAMD64.go` (2.6 MB) | 44.5 / 98.7 | 75.3 / 98.7 | 175.0 / 98.9 |
| Go `net/http/server.go` (140 KB) | 4.0 / 4.5 | 5.6 / 4.5 | 9.2 / 4.7 |
| Rust `lower/expressions.rs` (92 KB) | 4.2 / 5.4 | 5.5 / 5.4 | 9.1 / 5.5 |
| Python `typing.py` (136 KB) | 5.3 / 5.0 | 6.8 / 4.9 | 10.3 / 5.1 |
| Python `argparse.py` (107 KB) | 4.7 / 4.5 | 6.1 / 4.6 | 9.3 / 4.7 |

In megabytes, gramide first. `check` builds no tree: from a few hundred
kilobytes up it holds a third to over half less than tree-sitter. A file
read once for its outline holds within 4% of tree-sitter's tree from a few
hundred kilobytes up, and less on the largest. A document read and edited
holds about twice tree-sitter's tree: the parse and the document
cut from it stand side by side while it is cut, and each unit's tokens are
copied out of the parse. An empty file costs a process 2.5 to 3.4 MB
against tree-sitter's 1.6 to 1.7: the compiled grammar and the lexer's tables are
built when the process starts.

The document was once far larger. The Almide backend copies a list
element taken out with a fallback (`list.get(xs, i) ?? default`), copies a
value used twice in a branch inside a loop instead of moving it at its
last use, and copies what a closure captures for every element a
`list.map` visits: each child read that way was a copy of its subtree, and
putting the tree back together cloned the children's nodes once per node.
Every such read is now a borrow or a move.

## What it does not do

Readers that want absolute positions materialize the file, one pass and
no parsing.
