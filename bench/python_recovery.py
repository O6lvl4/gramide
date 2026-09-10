"""Known-edit declaration recovery comparison; no speed or general ranking claim."""
from pathlib import Path
import argparse
import hashlib
import json
import platform
import subprocess
import sys
import sysconfig
import tempfile

FIELDS = ('name', 'kind', 'owner', 'start', 'end', 'start_byte', 'end_byte')


def declaration(name, fragment, kind='function', owner=''):
    return dict(name=name, fragment=fragment, kind=kind, owner=owner)


BEFORE = 'def before(): pass'
AFTER = 'def after(): pass'
# Expected spans are specified from known intact source fragments, independently
# of either parser. Broken lexical scopes are never intentionally hoisted.
CASES = [
    ('valid', BEFORE+'\n'+AFTER+'\n', [declaration('before', BEFORE), declaration('after', AFTER)]),
    ('assignment', BEFORE+'\nx =\n'+AFTER+'\n', [declaration('before', BEFORE), declaration('after', AFTER)]),
    ('missing-if-colon', 'if broken\n def phantom(): pass\n'+AFTER+'\n', [declaration('after', AFTER)]),
    ('missing-function-colon', 'def broken()\n def phantom(): pass\n'+AFTER+'\n', [declaration('after', AFTER)]),
    ('missing-class-colon', 'class Broken\n def phantom(): pass\n'+AFTER+'\n', [declaration('after', AFTER)]),
    ('bad-method', 'class Box:\n def good(self): pass\n def bad(self):\n  x =\n def next(self): pass\n', [declaration('Box.good', 'def good(self): pass', 'method', 'Box'), declaration('Box.next', 'def next(self): pass', 'method', 'Box')]),
    ('nested-function', 'def outer():\n x =\n def helper(): pass\n'+AFTER+'\n', [declaration('outer.helper', 'def helper(): pass'), declaration('after', AFTER)]),
    ('single-string', BEFORE+'\nx = "bad\n'+AFTER+'\n', [declaration('before', BEFORE), declaration('after', AFTER)]),
    ('triple-string', BEFORE+'\nx = """bad\ndef phantom(): pass\n', [declaration('before', BEFORE)]),
    ('bracket-eof', BEFORE+'\nx = (\n def phantom(): pass\n', [declaration('before', BEFORE)]),
    ('f-string', BEFORE+'\nx = f"bad\n'+AFTER+'\n', [declaration('before', BEFORE), declaration('after', AFTER)]),
    ('t-string', BEFORE+'\nx = t"bad\n'+AFTER+'\n', [declaration('before', BEFORE), declaration('after', AFTER)]),
    ('missing-rhs-eof', BEFORE+'\nx =', [declaration('before', BEFORE)]),
    ('all-error', 'x =\n', []),
    ('two-errors', 'x =\n'+BEFORE+'\ny =\n'+AFTER+'\n', [declaration('before', BEFORE), declaration('after', AFTER)]),
    ('decorator', 'x =\n@decorate\ndef after(): pass\n', [declaration('after', '@decorate\ndef after(): pass')]),
    ('utf8-comment', '# 日本語\nx =\ndef café(): pass\n', [declaration('café', 'def café(): pass')]),
    ('missing-parameter', 'def broken(,):\n def phantom(): pass\n'+AFTER+'\n', [declaration('after', AFTER)]),
    ('bad-bytes', 'x = b"é"\n'+AFTER+'\n', [declaration('after', AFTER)]),
    ('trailing-comment', 'x =\n'+AFTER+' # note\n', [declaration('after', AFTER)]),
]


def expected(source, specs):
    raw = source.encode()
    rows = []
    for spec in specs:
        fragment = spec['fragment'].encode()
        assert raw.count(fragment) == 1, spec
        start = raw.index(fragment)
        end = start + len(fragment)
        rows.append(dict(name=spec['name'], kind=spec['kind'], owner=spec['owner'],
                         start=raw[:start].count(b'\n')+1, end=raw[:end].count(b'\n')+1,
                         start_byte=start, end_byte=end))
    return rows


def compare(actual, want):
    # Multisets retain duplicate exports as spurious declarations.
    unmatched = list(actual)
    missing, incorrect = [], []
    for row in want:
        if row in unmatched:
            unmatched.remove(row)
            continue
        candidate = next((r for r in unmatched if r['name'] == row['name']), None)
        if candidate is None:
            missing.append(row)
        else:
            unmatched.remove(candidate)
            incorrect.append(dict(expected=row, actual=candidate))
    return dict(missing=missing, spurious=unmatched, incorrect=incorrect,
                exact=not (missing or unmatched or incorrect))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--gramide', type=Path, required=True)
    ap.add_argument('--tree-sitter', type=Path, required=True)
    ap.add_argument('--references', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    bins = {'gramide': args.gramide.resolve(), 'tree_sitter': args.tree_sitter.resolve()}
    report = dict(platform=platform.platform(),
        scope='20 hand-specified known-edit cases, biased toward existing gramide recovery tests; not representative or a general ranking',
        policy='Export intact declarations with original lexical names and byte/line ranges; omit declarations containing damage and declarations inside broken headers or unterminated triple strings/brackets.',
        adapter='tree-sitter --recover skips ERROR subtrees and missing nodes, excludes error-bearing declarations but visits bodies under intact headers; gramide uses symbols-recovered. Their error boundaries differ. No incremental edits, time or RSS measurement.',
        binary_sha256={k: hashlib.sha256(v.read_bytes()).hexdigest() for k,v in bins.items()},
        source_sha256={p: hashlib.sha256((Path(__file__).parent/p).read_bytes()).hexdigest() for p in ['python_recovery.py', 'tree_sitter_python.c']},
        reference_commits={n: subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.references/n, text=True).strip() for n in ['tree-sitter', 'tree-sitter-python']}, cases=[])
    with tempfile.TemporaryDirectory() as tmp:
        for name, source, specs in CASES:
            path = Path(tmp)/f'{name}.py'
            path.write_bytes(source.encode())
            want = expected(source, specs)
            case = dict(name=name, source=source, expected=want, results={})
            for label, binary in bins.items():
                command = [str(binary), 'symbols-recovered' if label == 'gramide' else '--recover', str(path)]
                try:
                    result = subprocess.run(command, capture_output=True, text=True, timeout=10)
                except subprocess.TimeoutExpired:
                    case['results'][label] = dict(unavailable='timeout after 10s')
                    continue
                if result.returncode:
                    case['results'][label] = dict(unavailable=f'exit {result.returncode}', stderr=result.stderr)
                    continue
                payload = json.loads(result.stdout)
                rows = payload['symbols'] if label == 'gramide' else payload
                actual = [{k:r[k] for k in FIELDS} for r in rows]
                case['results'][label] = dict(actual=actual, **compare(actual, want))
                if label == 'gramide':
                    case['results'][label]['complete'] = payload['complete']
                if name == 'valid':
                    strict_command = [str(binary)]+(['symbols'] if label == 'gramide' else [])+[str(path)]
                    strict = json.loads(subprocess.check_output(strict_command))
                    assert (strict['symbols'] if label == 'gramide' else strict) == rows
                    assert actual == want, (label, actual, want)
            report['cases'].append(case)
    # Regression guard for the C adapter: recovery must not degrade valid input.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ci'))
    from python_symbols import expected as ast_expected
    report['valid_input_checks'] = []
    for name in ['keyword', 'token', 'stat', 'copyreg', 'genericpath', 'reprlib',
                 'textwrap', 'inspect', 'tokenize', 'ast', 'dataclasses', 'typing']:
        path = Path(sysconfig.get_path('stdlib'))/(name+'.py')
        source = path.read_text()
        want = ast_expected(source)
        for flags in [[], ['--recover']]:
            actual = json.loads(subprocess.check_output([str(bins['tree_sitter']), *flags, str(path)], timeout=10))
            assert actual == want, (name, flags, compare(actual, want))
        report['valid_input_checks'].append(dict(file=path.name, declarations=len(want),
            source_sha256=hashlib.sha256(source.encode()).hexdigest(), result='both tree-sitter modes match CPython'))
    report['python'] = platform.python_version()
    report['totals'] = {}
    for label in bins:
        results = [c['results'][label] for c in report['cases']]
        report['totals'][label] = dict(cases=len(results), exact=sum(r.get('exact', False) for r in results),
            unavailable=sum('unavailable' in r for r in results),
            missing=sum(len(r.get('missing', [])) for r in results),
            spurious=sum(len(r.get('spurious', [])) for r in results),
            incorrect=sum(len(r.get('incorrect', [])) for r in results))
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
    print(json.dumps(report['totals'], indent=2))
    for case in report['cases']:
        print(case['name'], {k: 'exact' if v.get('exact') else v.get('unavailable', 'mismatch') for k,v in case['results'].items()})


if __name__ == '__main__':
    main()
