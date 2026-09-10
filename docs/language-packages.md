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
