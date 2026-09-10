"""Range contracts and independent Go parser comparison; no model calls."""
from pathlib import Path
import json,subprocess,tempfile
BIN=Path(__file__).resolve().parents[1]/'gramide'
def symbols(path):
 p=subprocess.run([str(BIN),'symbols',str(path)],capture_output=True,text=True,check=True)
 d=json.loads(p.stdout);assert d['schema_version']==1 and d['complete'] is True
 return d['symbols']
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp)
 fixture=root/'ranges.go'
 fixture.write_text('''package sample
// 日本語 before declarations tests UTF-8 byte offsets.
type Box struct { value int }
func (b *Box) Read(
) int {
    text := `}
func phantom() {}`
    _ = text
    return b.value
}
func Other() {
    /* } */
}
''')
 oracle=root/'oracle'
 subprocess.run(['go','build','-o',str(oracle),str(BIN.parent/'ci/reference_ranges.go')],check=True)
 expected=json.loads(subprocess.check_output([str(oracle),str(fixture)],text=True))
 actual=[{k:s[k] for k in expected[0]} for s in symbols(fixture) if s['kind'] in ('method','function')]
 assert actual==expected,(actual,expected)
 raw=fixture.read_bytes()
 for s in symbols(fixture):assert raw[s['start_byte']:s['end_byte']].strip()
 rust=root/'ranges.rs';rust.write_text("// 日本語\nimpl Box {\n #[inline]\n pub fn\n read<'a>(&'a self) -> &'a str {\n r##\"}\nfn phantom() {}\n\"##\n }\n}\n")
 syms=symbols(rust);method=next(s for s in syms if s['name']=='Box::read')
 assert (method['owner'],method['start'],method['end'])==('Box',3,9),method
 assert rust.read_bytes()[method['start_byte']:method['end_byte']].startswith(b'#[inline]')
 assert not any('phantom' in s['name'] for s in syms)
 rust.write_text('#[repr(C)]\npub struct\nBox { x: i32 }\n')
 box=next(s for s in symbols(rust) if s['name']=='Box')
 assert (box['start'],box['end'],box['start_byte'])==(1,3,0),box
 rust.write_text('mod outer {\n mod inner {\n  impl fmt::Display for S {\n   fn fmt(&self) {}\n  }\n  fn free() {}\n }\n}\nmod other { fn free() {} }\n')
 syms=symbols(rust)
 assert [s['name'] for s in syms]==['outer','outer::inner','fmt::Display for outer::inner::S','outer::inner::S::fmt','outer::inner::free','other','other::free'],syms
 method=next(s for s in syms if s['kind']=='method')
 assert method['owner']=='S' and method['start']==4 and method['end']==4,method
 tags=subprocess.check_output([str(BIN),'tags',str(rust)],text=True)
 assert 'def impl fmt::Display for outer::inner::S L3-5' in tags,tags
 assert 'def function outer::inner::free L6-6' in tags and 'def function other::free L9-9' in tags,tags
 outline=subprocess.check_output([str(BIN),'outline',str(rust)],text=True)
 assert 'L3-5 impl fmt::Display for S' in outline and 'L4-4 method S::fmt' in outline,outline
 assert 'L6-6 function free' in outline and 'outer::inner::free' not in outline,outline
 almd=root/'ranges.almd';almd.write_text('fn real() -> Int = {\n  1\n}\n')
 assert [(s['name'],s['start'],s['end']) for s in symbols(almd)]==[('real',1,3)]
 almd.write_text('fn real() -> String = """\nhello\n"""\n')
 assert [(s['name'],s['start'],s['end']) for s in symbols(almd)]==[('real',1,3)]
 broken=root/'broken.rs';broken.write_text('fn real() {}\nfn broken(\n')
 p=subprocess.run([str(BIN),'symbols',str(broken)],capture_output=True,text=True)
 assert p.returncode!=0 and not p.stdout,(p.returncode,p.stdout,p.stderr)
 # A per-node copy of the complete token stream made this path quadratic.
 # Keep a generous process deadline: the fixed walk completes in well under a
 # second locally, while the old walk takes tens of seconds on this input.
 large=root/'many.go'
 large.write_text('package sample\n'+''.join('func F%d(x int) int { return x + %d }\n'%(i,i) for i in range(2000)))
 result=subprocess.run([str(BIN),'symbols',str(large)],capture_output=True,text=True,check=True,timeout=15)
 actual=json.loads(result.stdout)['symbols']
 expected=json.loads(subprocess.check_output([str(oracle),str(large)],text=True))
 assert len(actual)==2000
 assert [{k:s[k] for k in expected[0]} for s in actual]==expected
print('Structured ranges passed: Go parser oracle, Rust ownership/raw strings, Almide, invalid input')
