"""Check every installed stdlib Python outline against CPython, retaining failures."""
from pathlib import Path
import argparse, difflib, hashlib, json, platform, subprocess, sysconfig, tokenize
from python_outline_oracle import expected

ap = argparse.ArgumentParser(description=__doc__)
for name in ['gramide', 'tree-sitter', 'references', 'output']:
    ap.add_argument('--' + name, type=Path, required=True)
args = ap.parse_args()
root = Path(sysconfig.get_path('stdlib'))
excluded = {'test', 'tests', 'lib2to3', 'site-packages', '__pycache__'}
bins = {'gramide': args.gramide.resolve(), 'tree_sitter': args.tree_sitter.resolve()}
sha = lambda data: hashlib.sha256(data).hexdigest()
report = dict(
    python=platform.python_version(), platform=platform.platform(),
    mode='Full-file outline correctness against CPython AST; no timing or incremental reuse.',
    scope='Installed Python stdlib .py files, excluding listed directory components. Not the exact issue #37 Python 3.13 corpus.',
    excluded_components=sorted(excluded),
    binary_sha256={k: sha(p.read_bytes()) for k, p in bins.items()},
    harness_sha256={n: sha((Path(__file__).parent / n).read_bytes()) for n in ['python_stdlib.py', 'python_outline_oracle.py', 'tree_sitter_python.c']},
    reference_commits={n: subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=args.references / n, text=True).strip() for n in ['tree-sitter', 'tree-sitter-python']},
    cases=[],
)
for path in sorted(root.rglob('*.py')):
    relative = path.relative_to(root)
    if excluded.intersection(relative.parts):
        continue
    raw = path.read_bytes()
    row = dict(file=str(relative), bytes=len(raw), source_sha256=sha(raw))
    report['cases'].append(row)
    try:
        with tokenize.open(path) as source:
            want = expected(source.read()).encode()
    except (SyntaxError, UnicodeError, RecursionError) as error:
        row['oracle_error'] = str(error)
        continue
    row['expected_sha256'] = sha(want)
    for label, binary in bins.items():
        try:
            result = subprocess.run([str(binary), '--outline' if label == 'tree_sitter' else 'outline', str(path)], capture_output=True, timeout=30)
        except subprocess.TimeoutExpired:
            row[label] = dict(matches=False, timeout=True)
            continue
        actual = result.stdout
        row[label] = dict(matches=result.returncode == 0 and not result.stderr and actual == want, exit=result.returncode, output_sha256=sha(actual))
        if not row[label]['matches']:
            row[label]['stderr'] = result.stderr.decode(errors='replace')
            row[label]['diff'] = ''.join(difflib.unified_diff(want.decode().splitlines(True), actual.decode(errors='replace').splitlines(True), fromfile='CPython AST', tofile=label))
report['summary'] = dict(files=len(report['cases']), bytes=sum(r['bytes'] for r in report['cases']), oracle_failures=sum('oracle_error' in r for r in report['cases']), matches={k: sum(r.get(k, {}).get('matches', False) for r in report['cases']) for k in bins})
args.output.write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report['summary']))
for row in report['cases']:
    if 'oracle_error' in row or any(not row.get(k, {}).get('matches', False) for k in bins):
        print(row['file'], {k: row.get(k, {}).get('matches', False) for k in bins})
# Retain all comparator failures, but require gramide and the oracle to succeed.
raise SystemExit(0 if report['summary']['files'] > 0 and report['summary']['matches']['gramide'] == report['summary']['files'] else 1)
