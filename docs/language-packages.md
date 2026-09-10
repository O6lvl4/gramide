# Language package contract

The production composition root is `src/registry.almd`. It registers static
`Definition` values from `src/packages/gramide_{almide,go,rust}.almd`.
`src/package_api.almd` defines the interface; `src/lang.almd` is the generic host.
This establishes package boundaries without requiring separate repositories,
dynamic loading or independently installable Almide packages. Those are future
distribution decisions, not capabilities of this release.

Each definition supplies a stable language ID, package name/version, extensions,
capabilities, lexer factory, grammar factory, display separator and symbol rules.
The lexer factory prepares configuration once per loaded language and returns a
`(String, Bool) -> Result[List[Token], LexError]` callback. The boolean requests
recovery. The shared lexer remains useful but is optional. The host compiles only
languages present in a batch and rejects ambiguous extension registrations.

Symbol rules map syntax node kinds to semantic declaration kinds and identify
scopes, callables and declaration envelopes. Grammars use the shared tree field
conventions (`name`, `receiver`, `type_name`) consumed by tags and symbols. A new
syntax needing a new field convention must extend this ABI with tests.
`src/package_contract_test.almd` exercises a custom lexer, grammar, declaration
and owner rules without editing the built-in registry.

`gramide languages` emits `{ "schema_version": 1, "packages": [...] }`. Each
entry has `id`, `name`, `version`, `extensions` and `capabilities`. Consumers must
check the relevant capability: hew needs `symbols`, while cairn requires `check`
for a grammar-backed write gate. A reader-only grammar must not advertise check.
The built-in packages currently expose check, tokens, parse, outline, symbols,
tags and map. Balance is a separate generic fallback.

## Python design checkpoint

Python is not registered or advertised as supported. Before implementing
`gramide-python`, the reference checkout was pinned to CPython
`f715d25a8f0f0d57ecd2ae0dfe56c2ee01752733` in
`../almide-references/cpython` (Parser/lexer, Parser/tokenizer and Grammar).
Its lexer maintains indentation and alternate indentation stacks, ignores blank
and comment-only lines for layout, and emits pending INDENT/DEDENT tokens.
This motivates the custom lexer callback rather than another newline flag.

A Python package needs oracle comparisons for tabs/spaces and inconsistent
dedents, blank/comment lines, implicit and explicit continuation, strings and
f-strings, decorators, async declarations and match/case. Syntax rejection and
symbol ranges must be tested separately against CPython. A partial grammar may
be useful for reading, but must not acquire the check capability until its
acceptance/rejection contract is demonstrated.

## Compatibility validation

During extraction, 40 Go/Rust reference files matched the previous binary across
check, outline, symbols, tags and tokens (200 exact stdout/stderr/exit comparisons).
The existing independent Go AST range oracle remains in CI. Large-file timing
was measured for check only; no large-generated-file symbols speedup is claimed.

The implementation checkpoints below preserve historical results; the latest
checkpoint states the current remaining work.

## Python implementation progress: layout

`src/packages/python/layout.almd` implements the strict layout stage. Its input
is UTF-8 source and physical tokens ending in EOF. Token columns are one-based
byte columns, matching gramide's existing token contract. The scanner must emit
physical `newline`, `comment`, and `continuation` tokens (the latter includes a
backslash plus the line ending), and must keep multiline strings indivisible.
The stage preserves code tokens and adds logical newline/indent/dedent markers.
Indent/dedent markers have empty text and zero-width byte spans at the next code
token or EOF; they are not source whitespace tokens.

The implementation follows CPython's lexer indentation and alternate-indentation
stacks, tab stops, formfeed reset, leading line continuations, and the 100-entry
indent / 200-entry delimiter bounds. Blank/comment lines and bracketed physical
newlines do not produce statement separators. EOF completes a pending logical
line and drains indentation. Mixed tab/space indentation, inconsistent dedents,
unclosed/mismatched brackets and dangling continuations are rejected.

`ci/python_layout.py` compares against the host CPython tokenizer and compiler,
prints the oracle version, and runs the compiled Almide layout module through a
test-only JSON adapter. The reference tokenizer supplies physical tokens for valid
cases; a small independent adapter supplies malformed-layout fixtures so reference
rejection does not prevent testing gramide. The comparison covers logical token
kinds, preservation of original code-token text/positions, rejection and error
lines. It does not claim equivalent diagnostic text or synthetic marker spans.
Local CPython 3.14.4 validates 25 valid and 51 invalid cases.

This module is not a registered Python package. Python string/f-string, number
and identifier scanning, grammar rules, semantic ranges, recovery, real-source
corpora and hew integration remain unfinished. Python's `check` capability stays
unavailable until that end-to-end implementation is independently verified.

## Python implementation progress: ordinary string boundaries

`src/packages/python/strings.almd` recognizes ordinary, raw, Unicode and bytes
prefixes (including mixed-case `br` / `rb`) and scans single/triple-quoted strings.
It follows `_PyLexer_scan_string` in the pinned CPython `Parser/lexer/string.c`:
raw strings still escape quote characters lexically, escaped physical newlines
continue a string, and unescaped physical newlines cannot end a short string.
The scanner returns an exclusive byte offset in the original UTF-8 source.
It rejects unclosed strings, literal NUL bytes and non-ASCII bytes-literal content.

`ci/python_strings.py` validates 2,020 token boundaries and 12 rejected strings
against local CPython 3.14.4. The matrix varies prefix case/order, quote width,
escapes, quote runs, multiline content, Unicode, and nonzero UTF-8 start offsets.
The reference applies Python file-reading universal-newline conversion, then maps
its token boundary back to original bytes; passing raw CR directly to `tokenize`
would differ from the compiler's actual source-reading behavior. CI prints its
host oracle version rather than assuming a fixed installed Python release.

This stage locates ordinary string tokens. Escape decoding/validation (for example,
malformed `\\x` escapes), f-string and t-string expression parsing, identifier and
number scanning, recovery, and integration with layout/grammar are still pending.
Interpolated prefixes are not accepted by this component and must be dispatched
to an expression-aware scanner. Python remains unregistered.

## Python implementation progress: numbers

`src/packages/python/numbers.almd` scans decimal, binary, octal and hexadecimal
integers, decimal fractions/exponents and imaginary suffixes. It enforces digit
sets, underscore placement, leading-zero integer restrictions and ASCII suffix
boundaries. It returns original-source byte endpoints without evaluating or
converting numeric values, so large integers and overflowing float spellings do
not acquire host numeric limits.

The implementation follows the pinned CPython `Parser/lexer/number.c`, including
its compatibility boundary before adjoining `and`, `else`, `for`, `if`, `in`,
`is`, `or` and `not` keywords. CPython currently warns for these spellings rather
than rejecting all of them; the eventual lexer diagnostic channel must report
that warning. Non-ASCII identifier adjacency is left to identifier scanning and
grammar integration, as CPython's numeric suffix check also distinguishes ASCII.

`ci/python_numbers.py` compares compiler acceptance and tokenizer boundaries for
650 cases, including every base, prefix case, digit separators, fractions,
exponents, imaginary numbers, huge exponents, adjoining keywords and nonzero
UTF-8 byte offsets. Another 32 malformed numeric spellings must be rejected by
both implementations. Local oracle: CPython 3.14.4; CI reports its actual version.
The complete lexer, identifier validation, interpolated strings and grammar
remain unfinished; these component checks do not register Python support.

## Python implementation progress: Unicode identifiers

`src/packages/python/identifiers.almd` scans Python identifiers using explicit
Unicode 16 tables generated from CPython 3.14. ASCII uses direct comparisons;
non-ASCII classes use binary searches over compact inclusive ranges prepared
once per lexer. This avoids depending on the Unicode version bundled with a host
Rust regex library. The generator is `scripts/gen_python_identifiers.py`; CI
regenerates in check mode, and pins the Python oracle to 3.14.

`ci/python_identifiers.py` compares both classes for every one of the 1,114,112
code points, including surrogate values, against `str.isidentifier` and the
continuation check on `"a" + character`. It also compares 38 UTF-8 identifier scans
with CPython, including combining marks, compatibility letters, non-Latin names,
Unicode 15/16 additions, emoji, invalid starts and nonzero byte offsets. Original
source spelling and byte endpoints are preserved. The scanner consumes the same
potential identifier run described by CPython's `verify_identifier` and rejects
invalid non-ASCII characters inside that run.

This targets Python 3.14 / Unicode 16. Other Python Unicode versions require an
explicit version policy rather than silently adopting host character classes.
Keyword classification, NFKC name identity, interpolated strings, lexer integration,
grammar, recovery and hew's end-to-end Python reading remain pending. Python is
still not registered as a supported grammar.

## Python implementation progress: connected UTF-8 lexer

`src/packages/python/lexer.almd` connects ordinary strings, numbers, Unicode
identifiers and layout into `scan_source`. It handles longest-match Python
operators, comments, physical CR/LF/CRLF newlines, explicit continuations and
line tracking through multiline strings. The input contract is already-decoded
UTF-8 text; source-file encoding-cookie/BOM handling is not implemented here.
Hard/soft keyword interpretation remains a grammar concern: names currently use
the common `identifier` token kind. Lexing does not claim syntax validity.

`ci/python_lexer.py` compares complete logical token sequences and original code
token text, byte endpoints, lines and byte columns with CPython. It excludes
synthetic layout-marker positions from the position comparison, while retaining
those markers in the token-kind comparison. The local CPython 3.14.4 result is
15 matched inputs (including 2,000 declarations and `keyword.py`, `token.py`,
`stat.py`), seven rejected malformed inputs, and four standard-library files
explicitly unavailable because they contain interpolation (`copyreg.py`,
`genericpath.py`, `reprlib.py`, `textwrap.py`). The latter are measured gaps,
not skipped successes. [Evidence with source hashes](evidence/python-lexer.json)
records this bounded result.

F-string and t-string prefixes are detected and return an explicit unsupported
error rather than being misread as adjacent identifiers and ordinary strings.
Interpolation, escape validation, recovery, NFKC name identity, grammar and hew
integration remain necessary before Python can be registered. Full CPython
standard-library acceptance and tree-sitter parity have not been established.

## Python implementation progress: f-string and t-string modes

The connected lexer now scans both interpolation families. A stack tracks literal,
replacement-expression and format-specifier modes; nested interpolation uses the
same ordinary expression scanner as source outside strings. The dedicated
`interpolation.almd` handles escaped braces, named Unicode escapes, quote widths,
raw prefixes and transitions back to expression mode. Token spans follow CPython,
including its split spans for doubled braces and zero-width format-middle tokens.
This follows the pinned CPython `Parser/lexer/string.c` implementation.

The expanded whole-source oracle compares 409 accepted inputs and 11 rejected
malformed inputs with CPython 3.14.4. The accepted set contains 384 combinations of
interpolation family/prefix, quote width, fields, nested expressions, raw strings,
debug fields and dynamic format specifications, plus multiline-expression comments
and 12 standard-library files. All four files blocked by interpolation in the prior
checkpoint now match. Exact significant-token kinds, source spans, text, lines and
byte columns are compared, including interpolation start/middle/end tokens.
[Evidence and source hashes](evidence/python-interpolation.json) record the scope.

These are lexical comparisons, not proof of valid replacement-expression grammar
or format/conversion semantics. Escape validation, grammar and invalid-syntax
corpora, recovery, NFKC name identity, source encoding handling, hew integration
and comparative performance/memory measurements remain unfinished. Python remains
unregistered until its capability contracts are demonstrated.

## Python implementation progress: expression precedence

`src/packages/python/expressions.almd` supplies reusable expression rules plus a
standalone evaluation entry for testing. It implements arithmetic/matrix/bitwise
operators, Python's asymmetric unary/power precedence, boolean operations,
comparison chains, right-associative conditional expressions, grouping, and
simple call/attribute/subscript postfixes. Hard keywords are excluded from names;
soft keywords remain usable as identifiers. The rules follow the expression
sections of the pinned CPython `Grammar/python.gram`, targeting Python 3.14.

`ci/python_expressions.py` compares 648 normalized expression trees with CPython
ASTs. It covers all ordered pairs of the selected binary/boolean/comparison
operators, explicit associativity/grouping cases, conditionals and basic postfix
chains. Boolean AST lists are normalized to their equivalent left-fold structure;
comparison chains retain their dedicated chain representation. No expression is
evaluated. Another 47 malformed/keyword expressions must be rejected by both
parsers. [Evidence](evidence/python-expressions.json) records the corpus hash and
scope. This establishes more than acceptance: the tested operators bind to the
same operands as the reference parser.

This is not the complete expression grammar. Containers, comprehensions, slices,
lambdas, assignment/yield/await forms, full call arguments and interpolation grammar
still require implementation and oracle coverage. Statements, declarations, escape
validation, recovery and hew integration remain unfinished; Python stays unregistered.

## Python implementation progress: displays and slices

`containers.almd` extends the reusable expression rules with list, tuple, set and
dictionary displays, starred display items, dictionary unpacking, slices and
multi-item/starred subscripts. Empty braces produce a dictionary; a tuple display
requires a comma unless empty. The evaluation entry uses ordinary expressions for
unparenthesized tuples, preserving CPython's distinction between valid `(*a,)`
and invalid `*a,` in eval mode. These rules follow the display/slice sections of
the pinned CPython grammar.

The expanded AST oracle now matches 718 accepted expressions and rejects 62
malformed expressions. It compares container kinds, nesting, unpacking structure,
dictionary key/value pairing and omitted slice bounds/steps in addition to the
previous precedence checks. [Evidence](evidence/python-containers.json) records
this cumulative corpus and its hash. No values are evaluated.

Comprehensions, lambdas, assignment/yield/await expressions, complete call
arguments and interpolation grammar still remain, along with statements,
declarations, contextual syntax checks, recovery and hew integration. Python
is not registered by this checkpoint.

## Python implementation progress: call argument ordering

`arguments.almd` follows `arguments`, `args`, `kwargs` and the unpacking rules in
CPython `Grammar/python.gram` at the pinned reference commit. Calls now preserve
positional and starred arguments, named keywords and double-starred mappings.
The grammar enforces the transition from positional arguments to keywords and
then mapping unpacking: a positional argument can follow `*args`, but cannot
follow a keyword, and `*args` cannot follow `**kwargs`. Call unpacking accepts a
full expression, unlike starred container displays. Repeated argument groups
use repetition rather than recursion per argument.

The oracle enumerates all four argument categories through five positions
(1,364 combinations), with CPython determining validity. It compares positional
and keyword sequences separately, matching the CPython AST representation while
the gramide tree retains source order. Nested calls, conditional unpacking,
malformed keyword targets and 2,000 positional/keyword argument calls are covered.
The cumulative suite matches 1,156 expression trees and rejects 1,004 malformed
expressions. [Evidence](evidence/python-call-arguments.json) records the corpus.

This is AST parsing, not Python compilation or evaluation. Duplicate keyword
checks, NFKC name identity and other contextual validation remain pending.
Generator arguments and assignment expressions still require their expression
rules, as do comprehensions, lambdas, yield/await and interpolation. Statements,
declarations, recovery and hew integration are unfinished; Python stays
unregistered.

## Python implementation progress: named expressions and comprehensions

This checkpoint uses the matching CPython **v3.14.4** grammar at commit
`23116f998f6789d8c2fbe5ed5b8146854c8c2a4f`, fetched into the reference clone.
The original development-branch reference now includes newer comprehension
forms; those are not part of the Python 3.14 target.

`comprehensions.almd` adds list/set/dict comprehensions, generator expressions,
generator call arguments, repeated `for`/`if` clauses and `async for` markers.
Its reusable assignment-target rules support attribute/subscript receivers and
nested tuple/list destructuring. Calls may occur inside a receiver chain but
cannot be the final assignment target. Shared primary suffix rules keep these
receiver chains consistent with ordinary expressions.

Named expressions (`:=`) are admitted only in the positions allowed by the
Python grammar, including parenthesized groups, display items, call arguments,
subscripts and comprehension elements. Unparenthesized slice bounds and keyword
values still require ordinary expressions. Starred subscript items were also
corrected to accept full expressions, including conditional expressions.

The cumulative AST oracle matches **1,465** expression structures and rejects
**1,043** malformed expressions. Coverage includes products of display types,
assignment targets and iterable expressions; async/sync clauses and filters;
invalid targets; and generator argument delimiters. Target boundary cases are
classified independently by CPython. [Evidence](evidence/python-comprehensions.json)
records the corpus hash. This comparison checks structure, clause order and
async markers, not execution or AST Load/Store context annotations.

Compiler/symbol-table restrictions (such as a walrus rebinding a comprehension
iteration variable or appearing in an iterable) are not checked by `ast.parse`
and remain pending contextual validation. Lambdas, yield/await, interpolation
syntax, statements, declarations, escape validation, recovery and hew integration
remain unfinished. Python stays unregistered.
