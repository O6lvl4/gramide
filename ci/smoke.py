"""Drive the command line through the demo language; no network, no model."""
from pathlib import Path
import json, os, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[1]
ALMIDE = os.environ.get('ALMIDE_BIN', 'almide')

def run(binary, *args, code=0):
    p = subprocess.run([str(binary), *map(str, args)], capture_output=True, text=True, timeout=30)
    assert p.returncode == code, (args, p.returncode, p.stdout, p.stderr)
    return p.stdout, p.stderr

with tempfile.TemporaryDirectory() as tmp:
    binary = Path(tmp) / 'gramide_demo'
    subprocess.run([ALMIDE, 'build', 'ci/demo_cli.almd', '-o', str(binary)], cwd=ROOT, check=True)
    good = Path(tmp) / 'good.example'; good.write_text('@Box { action read; }')
    bad = Path(tmp) / 'bad.example'; bad.write_text('@Box { action ; }')
    manifest = json.loads(run(binary, 'languages')[0])
    assert manifest['schema_version'] == 1 and [p['id'] for p in manifest['packages']] == ['example'], manifest
    version = run(binary, 'version')[0].splitlines()
    assert version[0] == 'gramide_demo 0.0.0' and version[1].startswith('gramide ') and version[1].endswith('(engine)') and version[2].startswith('gramide-example 0.1.0'), version
    assert run(binary, 'check', good)[0] == f'{good}: ok\n'
    out, err = run(binary, 'check', good, bad, code=1)
    assert out == f'{good}: ok\n' and 'unexpected' in err, (out, err)
    doc = json.loads(run(binary, 'symbols', good)[0])
    assert doc['complete'] and [s['name'] for s in doc['symbols']] == ['Box', 'Box.read'], doc
    assert run(binary, 'outline', good)[0] == 'L1-1 class Box\n  L1-1 method Box.read\n'
    _, err = run(binary, 'symbols', bad, code=1)
    assert 'unexpected' in err, err
    _, err = run(binary, 'tokens', good, code=1)
    assert 'no language package provides tokens' in err, err
    unknown = Path(tmp) / 'x.unknown'; unknown.write_text('?')
    _, err = run(binary, 'check', unknown, code=1)
    assert 'no registered grammar' in err, err
    _, err = run(binary, 'check', Path(tmp) / 'missing.example', code=1)
    assert 'No such file' in err, err
    assert run(binary, 'balance', good)[0] == f'{good}: balanced\n'
    assert 'usage:' in run(binary, code=1)[1]
print('Core CLI smoke passed: languages, version, check, symbols, outline, balance and refusals through the demo language')
