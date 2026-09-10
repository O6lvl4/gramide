"""Recover outer interpolation atomically; never hoist names from damaged fields."""
from pathlib import Path
import ast
import json
import re
import subprocess
import tempfile

BIN = Path(__file__).resolve().parents[1]/'gramide'
count = 0


def run(command, path):
    return subprocess.run([str(BIN), command, str(path)], capture_output=True, text=True, timeout=10)


with tempfile.TemporaryDirectory() as tmp:
    path = Path(tmp)/'editing.py'

    def case(source, names):
        global count
        try:
            ast.parse(source)
        except SyntaxError:
            pass
        else:
            raise AssertionError(('fixture must be invalid', source))
        path.write_bytes(source.encode())
        result = run('symbols-recovered', path)
        assert result.returncode == 0, (source, result)
        doc = json.loads(result.stdout)
        assert doc['complete'] is False and doc['diagnostic'] and doc['errors'], (source, doc)
        assert [r['name'] for r in doc['symbols']] == names, (source, doc, names)
        raw = source.encode()
        for e in doc['errors']:
            assert 0 <= e['start_byte'] < e['end_byte'] <= len(raw), (source, e)
        for r in doc['symbols']:
            assert all(r['end_byte'] <= e['start_byte'] or r['start_byte'] >= e['end_byte'] for e in doc['errors']), doc
            fragment = raw[r['start_byte']:r['end_byte']]
            assert fragment.startswith(('def '+r['name'].split('.')[-1]+'(').encode()), (source, r)
            assert b'\n' not in fragment and b'\r' not in fragment, (source, r)
            line = len(re.findall(rb'\r\n|\r|\n', raw[:r['start_byte']]))+1
            assert r['start'] == r['end'] == line, (source, r)
            assert r['end_byte'] == len(raw) or raw[r['end_byte']] in [10, 13], (source, r)
        for command in ['check', 'symbols', 'tokens']:
            result = run(command, path)
            assert result.returncode != 0 and not result.stdout, (source, command, result)
        result = run('parse', path)
        assert result.returncode == 0 and '(ERROR)' in result.stdout, (source, result)
        count += 1

    for prefix in ['f', 'F', 'fr', 'fR', 'Fr', 'FR', 'rf', 'rF', 'Rf', 'RF',
                   't', 'T', 'tr', 'tR', 'Tr', 'TR', 'rt', 'rT', 'Rt', 'RT']:
        for quote in ['"', "'"]:
            for newline in ['\n', '\r\n', '\r']:
                case(newline.join(['def before(): pass', 'x = '+prefix+quote+'bad', 'def after(): pass', '']), ['before', 'after'])
            case('def before(): pass\nx = '+prefix+quote+'bad', ['before'])
            case('def before(): pass\nx = '+prefix+quote*3+'bad\ndef phantom(): pass\n', ['before'])
    # Completed replacement fields must roll back with the later failed literal.
    for family in ['f', 't']:
        for body in ['{value}bad', '{{escaped}}bad', '{value:{width}}bad', '{"same quote"}bad', '{f"{value}"}bad']:
            case('def before(): pass\nx = '+family+'"'+body+'\ndef after(): pass\n', ['before', 'after'])
        for newline in ['\n', '\r\n', '\r']:
            case('def before(): pass'+newline+'x = '+family+'"bad\\'+newline+'def phantom(): pass'+newline+'def after(): pass'+newline, ['before', 'after'])
        # Failed expression, format or nested lexical states own the remaining tail.
        for body in ['{value', '{0x', '{§', '{value\\q', '{"bad', '{f"bad', '{value:bad', 'bad}']:
            case('def before(): pass\nx = '+family+'"'+body+'\ndef phantom(): pass\n', ['before'])
        # Completed valid interpolation before a second broken one must survive.
        case('def before(): return '+family+'"{value}"\nx = '+family+'"bad\ndef after(): pass\n', ['before', 'after'])
        case('class Box:\n def good(self): pass\n def bad(self):\n  x = '+family+'"bad\n def next(self): pass\n', ['Box.good', 'Box.next'])
        case('def outer():\n def good(): pass\n x = '+family+'"""bad\ndef phantom(): pass\n', ['outer.good'])
    # Two failures exercise checkpoint reset and UTF-8 source offsets.
    case('# 日本語\nx = f"bad\ndef first(): pass\ny = t"bad\ndef second(): pass\n', ['first', 'second'])
    # An enclosing unmatched bracket remains unsupported; recovery must not
    # turn a physical newline inside it into a safe statement boundary.
    path.write_text('def before(): pass\nx = (f"bad\ndef phantom(): pass\n')
    result = run('symbols-recovered', path)
    assert result.returncode != 0 and not result.stdout, result
print(f'Python interpolation recovery: {count} prefix, quote, newline, frame rollback and containment cases passed')
