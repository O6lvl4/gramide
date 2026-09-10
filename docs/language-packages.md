# Language package contract

The production composition root is `src/registry.almd`. It registers static
`Definition` values from `src/packages/gramide_{almide,go,rust,python}.almd`.
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
scopes, namespace scopes, callables and declaration envelopes. Grammars use the shared tree field
conventions (`name`, `trait`, `receiver`, `type_name`) consumed by tags and symbols. A new
syntax needing a new field convention must extend this ABI with tests.
`src/package_contract_test.almd` exercises a custom lexer, grammar, declaration
and owner rules without editing the built-in registry.

`SymbolRules.namespaces` identifies declarations whose paths qualify flat tags
and structured symbols, independently of method-owner `scopes`. Existing static
package definitions must provide this field (an empty list if unused). Rust uses
`mod`; outline keeps module nesting through indentation. This source-level
contract addition does not change the JSON schema version or capability names.

`gramide languages` emits `{ "schema_version": 1, "packages": [...] }`. Each
entry has `id`, `name`, `version`, `extensions` and `capabilities`. Consumers must
check the relevant capability: hew needs `symbols`, while cairn requires `check`
for a grammar-backed write gate. A reader-only grammar must not advertise check.
All built-in packages expose check, tokens, parse, outline and symbols. Almide,
Go and Rust additionally advertise tags and map; Python reference extraction is
not yet covered by that contract. Balance is a separate generic fallback.

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

## Python implementation progress: lambda, yield and await

`lambdas.almd` follows the lambda parameter rules in the matching CPython v3.14.4
reference. It preserves positional-only parameters, ordinary parameters,
keyword-only parameters, defaults, `*args` and `**kwargs`. Defaults before `/`
continue to constrain ordinary parameters after `/`; keyword-only parameters
may independently have or omit defaults. Parameters use repeated groups rather
than recursion per parameter.

Expression rules also handle `await` at its primary-expression precedence,
parenthesized `yield`, `yield from`, and yielded tuples/unpacking. Lambda bodies
retain their low precedence, including nested lambdas and conditional bodies.

The oracle enumerates all six lambda parameter categories through four positions
(1,554 combinations) and includes longer mixed signatures, nested defaults,
trailing commas and invalid annotations/ordering. All binary/comparison operator
fixtures are combined with `await` on either side. The cumulative corpus matches
**1,729** AST structures and rejects **2,454** malformed expressions.
[Evidence](evidence/python-lambda-yield-await.json) records the corpus hash.
Lambda comparison includes parameter categories and default associations, not
just acceptance.

These are grammar/AST checks. Restrictions on `await` or `yield` outside an
appropriate function, duplicate parameter names and other compiler-context
checks remain pending. Interpolated/concatenated string syntax, escape validation,
statements, declarations, recovery and hew integration are still unfinished;
Python remains unregistered.

## Python implementation progress: string composition and interpolation syntax

`string_expressions.almd` follows the CPython v3.14.4 string, f-string and t-string
rules. It permits ordinary/f-string concatenation, bytes-only concatenation and
t-string-only concatenation, rejecting mixtures across those families. Replacement
fields use the existing expression/yield rules and preserve debug markers,
conversions (`s`, `r`, `a`) and recursively nested format specifications.

The package expression entry point is now `expressions.parse_with`. It applies
`string_expressions.prepare` before the PEG parser: lexical STRING tokens remain
CPython-compatible, but bytes literals become a distinct grammar token kind.
It also verifies source adjacency after `!`, which token-text matching alone
cannot express. Future package integration must retain this preparation step.

The expanded oracle covers all four string-family categories through four
concatenated pieces, plus 1,024 prefix/quote/body combinations, nested f/t strings,
comments, yield/await, debug formatting, conversion errors and malformed fields.
The cumulative corpus matches **2,607** structures and rejects **2,954** malformed
expressions. [Evidence](evidence/python-string-expressions.json) records the hash.
Comparison includes string families, replacement expressions, conversion defaults
and nested format-field structure. Literal chunks remain in source tokens but
are excluded from AST normalization; decoded literal text, t-string expression
text and debug-generated text are not compared by this oracle. The separate
lexer oracle continues to check exact source-token text and byte ranges.

Escape decoding/validation and contextual compiler checks remain unfinished,
as do statements, declarations, recovery and hew integration. Python remains
unregistered; these expression milestones do not establish complete Python
support or a performance win over tree-sitter.

## Python implementation progress: numeric escape validation

The expression entry point now rejects truncated/non-hex `\x`, `\u` and `\U`
escapes, and `\U` values above U+10FFFF. `escapes.almd` follows CPython v3.14.4
`Objects/unicodeobject.c` and `Objects/bytesobject.c`, fetched into the reference
clone. Bytes literals only interpret `\x` among these forms. Raw literals skip
numeric escape interpretation; nested f/t-string frames preserve their own raw
modes, including format-specification chunks and ordinary strings inside fields.
The lexical scanner continues to report source boundaries independently.

The oracle adds 469 cases across raw/ordinary/bytes/interpolated modes, quote
widths, truncated escapes, invalid digits, range boundaries, escaped backslashes
and nested raw-mode transitions. The cumulative suite matches **2,993** structures
and rejects **3,037** inputs. [Evidence](evidence/python-numeric-escapes.json)
records this corpus. CPython sometimes raises `UnicodeDecodeError` rather than
`SyntaxError` for malformed interpolation escapes; both count as rejection.
Diagnostics currently point to the containing literal token, not the exact
escape byte. Warning-only unknown/octal escapes remain accepted without warning
emission, matching default CPython acceptance.

Unicode-name escapes (`\N{...}`), decoded values and contextual compiler checks
remain unfinished. This does not complete string validation or Python support;
statements, declarations, recovery and hew integration are still required.

## Python implementation progress: simple statements

`statements.almd` follows CPython v3.14.4's `simple_stmts`, assignment, import,
delete and other simple-statement rules. It connects the existing expression
and assignment-target grammars to semicolon/newline-delimited statements:
chained/destructuring assignment, annotated and augmented assignment, return,
raise/from, assert, delete, global/nonlocal, import/from/as, pass, break,
continue, expression statements and yield statements. Annotation nodes retain
the distinction between a bare name and a parenthesized/attribute target.
Relative imports preserve module names, aliases and leading-dot levels.

`statements.file_grammar()` currently accepts files made entirely of these
simple statements. It uses `expressions.parse_with` for literal preparation and
validation. Compound statements and type aliases are not implemented by this
checkpoint, so this is not yet a complete Python file parser or package.

The new statement oracle shares expression normalization with the expression
suite (`ci/python_ast.py`). It matches **400** statement trees, including **227**
exact top-level simple-statement segments from CPython's tokenize, dataclasses,
inspect, ast and typing modules, and rejects **124** malformed inputs. It compares
assignment targets/order, annotation flags, augmentation operators, import paths
and aliases, relative levels and control-statement expressions. It does not
claim these standard-library modules parse as complete files.
[Evidence](evidence/python-simple-statements.json) records the corpus hash.

Compiler-context validation, type comments, Unicode-name escape validation,
compound suites/declarations, recovery and hew integration remain unfinished.
Python stays unregistered.

## Python implementation progress: compound control flow

`compounds.almd` connects logical NEWLINE/INDENT/DEDENT tokens to nonempty suites
and composes them with the simple-statement grammar. It follows CPython v3.14.4
for if/elif/else, while/for with else, async for, with/async with and try/except/
except*/else/finally. Ordinary and exception-group handlers cannot be mixed.
Python 3.14's unparenthesized exception lists are supported, with alias placement
following the reference grammar.

The with-item grammar distinguishes parenthesized item lists from a tuple
expression followed by `as`. The former needs the next token after the
closing parenthesis to be a colon; otherwise it falls back to the expression form. `with ():`
is syntactically valid (an empty tuple context expression), regardless of whether
that value can act as a context manager at runtime.

The cumulative statement oracle now matches **491** trees and rejects **146**
malformed inputs. It includes 227 standard-library simple statements and six
exact top-level compound-statement segments, nested branch/loop combinations,
async flags, handler order and aliases, and multiple dedentation levels.
[Evidence](evidence/python-compound-statements.json) records the corpus hash.
Tests compare which suite belongs to each else/finally/handler, not just whether
a file was accepted.

Function/class declarations, match patterns, type aliases, contextual compiler
checks, type comments, Unicode-name escape validation, recovery and hew
integration remain unfinished. Python is still unregistered.

## Python implementation progress: functions, classes and generic declarations

`parameters.almd` follows CPython v3.14.4's function parameter grammar, including
positional-only and keyword-only parameters, annotations, defaults and variadic
parameters. Starred annotations are admitted for `*args`, not ordinary parameters
or `**kwargs`. The separate lambda grammar keeps its unannotated signature rules.

`declarations.almd` adds sync/async functions, classes, decorators, return
annotations, type aliases and type parameters (bounds, defaults, TypeVarTuple and
ParamSpec). Declarations reuse the existing suite and expression grammars. Their
names use the shared tree `name` field, and decorator spans belong to the owning
declaration for future symbol-range integration.

The statement oracle matches **683** structures and rejects **1,543** malformed
inputs. It includes 1,554 annotated-parameter category combinations, longer mixed
signatures, nested declarations, class arguments, decorator order and generic
parameter structure. It now also compares **ten complete standard-library files**:
keyword.py, token.py, stat.py, copyreg.py, genericpath.py, reprlib.py, textwrap.py,
inspect.py, tokenize.py and ast.py. Bodies are compared recursively, not only
function/class names. [Evidence](evidence/python-declarations.json) records the
corpus and the full-file list. Literal decoding and compiler-context checks are
still outside this oracle.

Match patterns, contextual checks, type-comment handling, Unicode-name escape
validation, recovery, package registration and hew integration remain unfinished.
Dataclasses/typing full-file fixtures are still pending their match syntax;
previous simple-statement segments from those modules remain covered. The ten
full files do not establish support for the entire standard library or a
performance/memory win over tree-sitter.

The declaration corpus exposed quadratic copying in the **test probe's output
walk**, causing the initial CI run to exceed its 60-second process deadline.
The probe now emits node token indices and one separate token-text array;
`ci/python_ast.py` rejoins them for exactly the same structural assertions. No
fixtures were removed and the deadline is unchanged. A local diagnostic on the
same inspect.py observed approximately 42.84 seconds for the old output path,
0.07 seconds with tree output omitted, and 0.35 seconds for the indexed output.
These are single-run harness diagnostics, not a production/tree-sitter benchmark.

## Python implementation progress: match patterns

`patterns.almd` follows CPython v3.14.4's pattern grammar rather than accepting
arbitrary expressions after `case`. It preserves wildcard/capture/value/as/or,
sequence/star, mapping/rest and class positional/keyword patterns, plus case
guards and subject tuples. `match` and `case` retain their soft-keyword behavior.

Literal preparation now distinguishes imaginary numeric tokens for grammar use,
while the lexical token contract remains unchanged. Ordinary expressions accept
both numeric kinds; complex-number patterns require a real left operand and an
imaginary right operand. Attribute/class paths and capture targets have their
own lookahead restrictions. Empty class-pattern arguments cannot contain a
comma, and mapping rest captures must occur last.

The statement oracle now matches **857** structures and rejects **1,600** malformed
inputs. It compares pattern kinds, capture names, mapping keys/rests, class
positions/keywords, guards and case bodies. Dataclasses.py and typing.py are now
included as **complete files**, bringing the full standard-library corpus to
12 files. [Evidence](evidence/python-match-patterns.json) records the list and
corpus hash. This remains structural AST comparison, not literal decoding or
execution.

Compiler-context checks (for example duplicate captures, inconsistent OR-pattern
bindings or unreachable cases), type comments, Unicode-name escape validation,
recovery, package registration and hew integration remain unfinished. Python is
still unregistered at this checkpoint; the next integration stage must preserve
the literal-preparation path and document remaining validation limits.

## Python package registration and reader integration

`gramide-python` now registers `.py` and `.pyi` for Python 3.14 through the same
static package API as the other languages. Its lexer callback always performs
literal validation and grammar token preparation, including bytes/imaginary
refinement. Strict checks and symbol extraction therefore use the same path as
the CPython grammar oracles. The public `tokens` command exposes these prepared
tokens; the independent lexical oracle still checks the underlying lexer stream.

`SymbolRules.lexical_owners` is a required boolean: false for existing packages,
true for Python. In Python, class/function namespaces already contain the method
owner, so flat names append the declaration once (`Outer.Inner.method`). Nested
functions retain lexical paths but are functions, not methods of the outer class.
Structured method owners use the complete enclosing class path. Outline expresses
nesting through indentation as before. This is lexical qualification, not runtime
name resolution or Python's `__qualname__` format with `<locals>` markers.

Declaration ranges trim trailing newline/indent/dedent markers, which otherwise
can point at the next declaration. Decorators are included; unrelated following
comments and blank lines are excluded. The CPython symbol oracle checks 645
names/kinds/owners/ranges across nested, decorated and async declarations, stubs,
and 12 complete stdlib files. An optional suite-ending semicolon is retained.

The Python scanner stays strict for checks and complete-symbol reads. Optional
reader recovery is described below; broken input must never produce a symbols
document marked complete. Compiler-context checks,
Unicode-name escapes, NFKC identity, literal decoding, encoding cookies/BOM and
Python reference extraction remain future work. `check` is a grammar check, not
a promise that CPython compilation or execution succeeds. Historical checkpoints
above describe their then-unregistered state. No tree-sitter victory is claimed.

## Python logical-line recovery

`RecoverLines(rule)` / `parser.recover_lines(rule)` is an opt-in shared engine
rule for grammars with `newline`, `indent` and `dedent` tokens. In strict mode it
has exactly the wrapped rule's acceptance. In recovery mode a failed statement
skips to another logical line at the same indentation, or stops before the
current scope's closing dedent/EOF. It never resumes midway through an expression
or hoists declarations from a skipped nested suite. The skipped range becomes
an `ERROR` node; consecutive invalid lines can share one such range.

Python statement lists now use this rule. `parse` and `outline` preserve readable
statements around errors, including valid outer functions/classes whose suites
contain a bad statement. A malformed header and its nested suite are skipped as
a unit. Diagnostics explicitly mark the result as recovered. `check` remains
strict, and `symbols` still refuses incomplete trees; consequently hew does not
yet consume these partial trees as authoritative ranges.

The design was checked against the cloned tree-sitter-python grammar and external
scanner at `26855eabccb19c6abf499fbc5b8dc7cc9ab8bc64`, especially comment/dedent
handling and bracket-aware newline suppression. Gramide uses the strict lexer's
logical layout stream here. This is a different, explicitly tested recovery
policy, not a claim of matching tree-sitter's incomplete-tree shape.

`ci/python_recovery.py` covers 55 cases: incomplete assignments, imports, raises,
asserts, decorators and headers; nested scopes; skipped suites; EOF; blank lines;
UTF-8 comments; physical newlines inside brackets; 2,000 consecutive malformed lines; and strict rejection. It also
asserts that unmatched delimiters and bad escapes remain failures. Ordinary
string recovery is described below. Further scanner recovery, preservation of incomplete declaration heads,
partial-symbol integration with hew, edit-sequence comparisons and incremental
reuse remain unfinished.

## Ordinary-string recovery

The package now honors the lexer callback's recovery flag. Strict entry points
continue to use `physical` / `scan_source`; readers can request
`physical_with` / `scan_source_with`. When an ordinary-string scan fails outside
an interpolation frame, recovery emits an `error` token over its lexical extent.
The existing logical-line parser then records an `ERROR` range.

Single-quoted literals stop at an unescaped physical line ending or EOF. Escaped
newlines stay inside the token, including CRLF. Triple-quoted literals continue
to their closing delimiter or EOF, so declaration-looking text inside an
unterminated triple string is never exported as code. Invalid closed bytes
literals retain their actual closing boundary. The original strict diagnostic
is retained by the reader; recovery does not certify the literal as valid.

Recovered scopes can end with a token consuming EOF immediately after a line
ending. Inclusive outline end lines now count LF/CRLF/CR consistently and exclude
the nonexistent line after that final terminator. This fixes a reproduced
one-line overrun for an enclosing function with an unterminated triple string.

`ci/python_string_recovery.py` checks 163 cases across ordinary prefixes, quote
widths, newline forms, escaped newlines, bytes literals, nested scopes and
unsupported errors. Check, symbols and tokens must still reject these inputs.
The existing ordinary-string lexical oracle and full grammar oracles remain in
CI. The boundary policy was reviewed against the cloned tree-sitter-python
external scanner's single/triple delimiter and backslash handling; equivalent
recovered-tree shape or performance is not claimed.

Interpolation recovery is described below. Unmatched outer brackets, invalid
escapes, invalid indentation and NUL remain unsupported. Incremental edit reuse
also remains unfinished; hew now consumes the recovered declaration contract.

## Recovered declaration contract for readers

Python advertises `symbols-recovered`, a separate command from strict `symbols`.
It returns schema version 1 plus `recovery_policy: "error-free-declarations-v1"`,
`complete`, a `diagnostic`, ordered `errors` (inclusive line ranges and exclusive
end byte offsets), and `symbols`. Valid input has `complete: true` and no errors;
recovered input has `complete: false` and nonempty bounded errors. Unsupported
lexical failures still return failure without JSON. Other language packages do
not advertise this policy yet because their recovery may retain partial heads.

Only declarations whose byte ranges do not intersect any ERROR range are
returned. An enclosing class/function covering an error is omitted; an intact
nested method/function can remain with its original lexical name and owner.
This does not certify compiler semantics or recover a malformed header. The
normal symbols command and its complete-only contract remain unchanged.

Error ranges are collected in source order; a binary search tests overlap, so
filtering D declarations against E disjoint errors costs O(D log E), rather than
scanning every error for every declaration. The regression includes 500
alternating errors/functions, malformed headers with hidden nested declarations,
ordinary-string failures, strict rejection and valid-input output parity.

Hew can explicitly request this command after strict parsing fails, validate the
policy and ranges, and label the selected engine `gramide-recovered`. It must
never silently accept an arbitrary partial response from the strict command.


## Interpolated-string recovery

The comparison in `bench/python_recovery.py` exposed two concrete losses to
our tree-sitter adapter: unterminated f/t strings prevented gramide from returning
any declarations. The lexer now checkpoints the outermost interpolation and,
after a lexical failure, replaces all of its emitted tokens with one error token.
This removes replacement-field braces before layout runs, preserves earlier
valid declarations, and prevents nested declaration-looking text from escaping
its failed interpolation. Strict check, symbols and tokens retain rejection and
the original error diagnostic.

A failure in the outer literal mode of a single-quoted string can resume at the
first unescaped LF, CRLF or CR. Completed replacement fields before that failure
are rolled back too. Triple-quoted strings, failed replacement expressions,
format states and nested strings conservatively consume the remaining source:
these states do not establish a safe closing boundary. This may omit real later
declarations; it deliberately does not claim full editor recovery. Unmatched
brackets outside the interpolation and later escape-validation failures remain
unsupported.

This boundary decision follows the single/triple delimiter, escaped-newline and
literal-versus-expression distinctions in the cloned tree-sitter-python external
scanner (`26855eabccb19c6abf499fbc5b8dc7cc9ab8bc64`); gramide's conservative tail
policy is its own consumer contract, not equivalent tree-sitter recovery.
`ci/python_interpolation_recovery.py` checks 239 invalid cases with CPython
rejection, exact retained names and ranges, error exclusion, strict rejection,
all prefix/quote/newline forms, completed fields, nested failures and scope
containment. The existing normal-input token and grammar oracles still run.
