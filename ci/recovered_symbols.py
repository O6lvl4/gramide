"""Explicit recovered-symbol contract; never include declarations covering errors."""
from pathlib import Path
import json,subprocess,tempfile
BIN=Path(__file__).resolve().parents[1]/'gramide'
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'editing.py'
 cases=[
 ('def before(): pass\nx =\ndef after(): pass\n',['before','after']),
 ('class Box:\n def good(self): pass\n def bad(self):\n  x =\n def next(self): pass\n',['Box.good','Box.next']),
 ('def outer():\n x =\n def helper(): pass\ndef after(): pass\n',['outer.helper','after']),
 ('if broken\n def phantom(): pass\ndef real(): pass\n',['real']),
 ('def before(): pass\nx = "bad\ndef after(): pass\n',['before','after']),
 ('def before(): pass\nx = """bad\ndef phantom(): pass\n',['before']),
 ('x =\n',[]),
 ('x =\ndef first(): pass\nx =\ndef second(): pass\n',['first','second']),
 ]
 for source,names in cases:
  p.write_text(source)
  r=subprocess.run([str(BIN),'symbols-recovered',str(p)],capture_output=True,text=True,check=True)
  d=json.loads(r.stdout)
  assert d['schema_version']==1 and d['complete'] is False and d['recovery_policy']=='error-free-declarations-v1',d
  assert d['diagnostic'] and d['errors'],d
  assert [s['name'] for s in d['symbols']]==names,d
  previous=0
  for e in d['errors']:
   assert previous<=e['start_byte']<e['end_byte']<=len(source.encode()),e
   assert 1<=e['start']<=e['end']<=d['total_lines'],e
   previous=e['end_byte']
  for s in d['symbols']:
   assert all(s['end_byte']<=e['start_byte'] or s['start_byte']>=e['end_byte'] for e in d['errors']),d
  strict=subprocess.run([str(BIN),'symbols',str(p)],capture_output=True,text=True)
  assert strict.returncode!=0 and not strict.stdout,strict
 p.write_text('class Box:\n def good(self): pass\n')
 strict=json.loads(subprocess.check_output([str(BIN),'symbols',str(p)]))
 recovered=json.loads(subprocess.check_output([str(BIN),'symbols-recovered',str(p)]))
 assert recovered['complete'] is True and not recovered['errors'] and not recovered['diagnostic'],recovered
 assert strict['symbols']==recovered['symbols'],recovered
 p.write_text('x = (\n')
 r=subprocess.run([str(BIN),'symbols-recovered',str(p)],capture_output=True,text=True)
 assert r.returncode!=0 and not r.stdout,r
 other=Path(tmp)/'x.rs';other.write_text('fn valid() {}\n')
 r=subprocess.run([str(BIN),'symbols-recovered',str(other)],capture_output=True,text=True)
 assert r.returncode!=0 and not r.stdout,r
 # Many disjoint errors exercise the sorted interval lookup, not only one range.
 p.write_text(''.join(f'x =\ndef f{i}(): pass\n' for i in range(500)))
 d=json.loads(subprocess.check_output([str(BIN),'symbols-recovered',str(p)],timeout=10))
 assert len(d['errors'])==500 and [s['name'] for s in d['symbols']]==[f'f{i}' for i in range(500)],d
print('Recovered symbols: exact retained declarations, error exclusion, strict/unsupported rejection and 500 disjoint errors passed')
