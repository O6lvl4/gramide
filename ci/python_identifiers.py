"""Exhaustive CPython Unicode-class oracle plus UTF-8 identifier scanning."""
from pathlib import Path
import json,os,platform,shutil,subprocess,tempfile,unicodedata
ROOT=Path(__file__).resolve().parents[1]
assert unicodedata.unidata_version=='16.0.0','Use CPython 3.14 / Unicode 16 for this pinned oracle'
names=['name','_','x1','日本語','é','e\u0301','\u0301e','K','Ａ','变量1','x·y','·x','🪨','name🪨','1name','name\u200d','a\u00b2','\U00011f02','\U00001c89']
with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);(project/'src/packages/python').mkdir(parents=True)
    for file in ['tree.almd','names.almd','lex.almd','packages/python/identifiers.almd','packages/python/identifier_data.almd']:
        shutil.copyfile(ROOT/'src'/file,project/'src'/file)
    shutil.copyfile(ROOT/'ci/python_identifiers_probe.almd',project/'src/main.almd')
    (project/'almide.toml').write_text('[package]\nname = "identifiers_probe"\nversion = "0.1.0"\nedition = "2026"\n')
    binary=project/'probe';data=project/'cases.json'
    subprocess.run([os.environ.get('ALMIDE_BIN','almide'),'build','-o',str(binary)],cwd=project,check=True)
    def run(points,scans):
        data.write_text(json.dumps(dict(points=points,scans=scans),ensure_ascii=False))
        return json.loads(subprocess.check_output([str(binary),str(data)],text=True,timeout=60))
    for start in range(0,0x110000,65536):
        points=list(range(start,min(start+65536,0x110000)))
        actual=run(points,[])['classes']
        expected=[[chr(cp).isidentifier(),('a'+chr(cp)).isidentifier()] for cp in points]
        assert actual==expected,('class mismatch in block',hex(start))
    cases=[];expected=[]
    for name in names:
        for prefix in ['', '🪨 ']:
            cases.append(dict(source=prefix+name+' + 1',start=len(prefix.encode())))
            expected.append(dict(ok=True,end=len((prefix+name).encode())) if name.isidentifier() else dict(ok=False))
    assert run([-1,0x110000],cases)==dict(classes=[[False,False],[False,False]],scans=expected)
print(f'CPython {platform.python_version()} / Unicode 16: all 1,114,112 code points match both classes; {len(cases)} identifier scans match')
