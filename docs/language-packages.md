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
