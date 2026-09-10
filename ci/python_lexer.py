"""Compare connected Python lexing with CPython, recording interpolation gaps."""
from pathlib import Path
import io,json,os,platform,shutil,subprocess,sys,sysconfig,tempfile,tokenize,hashlib
ROOT=Path(__file__).resolve().parents[1]
SOURCES=[
 ('nested','if True:\n    if False:\n        pass\n    x = 1\ny = 2\n'),
 ('unicode','class 日本語:\n    e\u0301 = "🪨"\n    def 関数(self):\n        return self.e\u0301\n'),
 ('crlf','if True:\r\n    x = (1 +\r\n     2)\r\n    s = """a\r\nb"""\r\n'),
 ('cr','if True:\r    x = 2\r'),
 ('continuation','if True:\n    \\\n      x = 1 + \\\n          2\n    y = 3\n'),
 ('comments','# comment\nif True:\n # comment\n    x = 1\n\n  # end\n'),
 ('strings',"a = r'\\\"'\nb = b'abc'\nc = '''a\nb'''\nd = u'日本語'\n"),
 ('operators','x: int = 0x_FF\nx **= 2\nx >>= 1\ny = .5e+2j\nz = [x for x in range(3) if x != 2]\na = ...\n'),
 ('no_final_newline','if True:\n    x = 1'),('empty',''),('comment_eof','x = 1 # tail'),
]
SOURCES.append(('many_declarations',''.join(f'value_{i} = {i}\n' for i in range(2000))))
stdlib=Path(sysconfig.get_path('stdlib'))
for name in ['keyword.py','token.py','stat.py','copyreg.py','genericpath.py','reprlib.py','textwrap.py']:
    SOURCES.append((name,(stdlib/name).read_text()))
INVALID=['if True:\n\tx = 1\n        y = 2\n','x = (1]\n','x = 1e+\n','x = "unterminated\n','name🪨 = 1\n','x = 1 \\oops\n','x = 1\x00\n']

def oracle(source):
    # Map normalized character offsets back to original UTF-8 bytes.
    normalized='';offsets=[0];i=0;byte=0
    while i<len(source):
        width=2 if source[i:i+2]=='\r\n' else 1
        normalized+='\n' if source[i]=='\r' else source[i]
        byte+=len(source[i:i+width].encode());offsets.append(byte);i+=width
    starts=[0]
    for i,c in enumerate(normalized):
        if c=='\n':starts.append(i+1)
    raw=source.encode()
    def at(pos):
        row,col=pos
        return offsets[min(starts[row-1]+col,len(offsets)-1)] if row<=len(starts) else len(raw)
    kinds=[];code=[];interpolated=False
    for t in tokenize.generate_tokens(io.StringIO(normalized).readline):
        if tokenize.tok_name[t.type].startswith(('FSTRING','TSTRING')):interpolated=True
        if t.type in (tokenize.NL,tokenize.COMMENT):continue
        kind={tokenize.NAME:'identifier',tokenize.NUMBER:'number',tokenize.STRING:'string',tokenize.OP:'punct',tokenize.NEWLINE:'newline',tokenize.INDENT:'indent',tokenize.DEDENT:'dedent',tokenize.ENDMARKER:'eof'}.get(t.type,'interpolation')
        kinds.append(kind)
        if kind in ('identifier','number','string','punct'):
            start,end=at(t.start),at(t.end)
            line_start=max(raw.rfind(b'\n',0,start),raw.rfind(b'\r',0,start))+1
            code.append(dict(kind=kind,text=raw[start:end].decode(),start=start,end=end,line=t.start[0],col=start-line_start+1))
    return kinds,code,interpolated

with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);(project/'src/packages').mkdir(parents=True)
    shutil.copytree(ROOT/'src/packages/python',project/'src/packages/python')
    for file in ['tree.almd','lex.almd']:shutil.copyfile(ROOT/'src'/file,project/'src'/file)
    shutil.copyfile(ROOT/'ci/python_lexer_probe.almd',project/'src/main.almd')
    (project/'almide.toml').write_text('[package]\nname = "lexer_probe"\nversion = "0.1.0"\nedition = "2026"\n')
    binary=project/'probe';data=project/'cases.json'
    subprocess.run([os.environ.get('ALMIDE_BIN','almide'),'build','-o',str(binary)],cwd=project,check=True)
    for source in INVALID:
        try:compile(source,'invalid','exec')
        except SyntaxError:pass
        else:raise AssertionError('reference accepted malformed fixture')
    data.write_text(json.dumps({'cases':[dict(source=s) for _,s in SOURCES]+[dict(source=s) for s in INVALID]},ensure_ascii=False))
    results=json.loads(subprocess.check_output([str(binary),str(data)],text=True,timeout=60))
    accepted=[];unsupported=[]
    for (name,source),result in zip(SOURCES,results):
        compile(source,name,'exec')
        kinds,code,interpolated=oracle(source)
        if interpolated:
            assert not result['ok'] and 'interpolated' in result['message'],(name,result)
            unsupported.append(name);continue
        assert result['ok'],(name,result)
        assert [t['kind'] for t in result['tokens']]==kinds,(name,'token kinds differ')
        actual=[t for t in result['tokens'] if t['kind'] in ('identifier','number','string','punct')]
        assert actual==code,(name,'source token ranges differ',next(((a,b) for a,b in zip(actual,code) if a!=b),None))
        accepted.append(name)
    assert all(not r['ok'] for r in results[len(SOURCES):])
    report=dict(python=platform.python_version(),matched=accepted,unsupported_interpolation=unsupported,rejected=len(INVALID),
                source_sha256={name:hashlib.sha256(source.encode()).hexdigest() for name,source in SOURCES},
                compared='logical token kinds; exact text, bytes, lines and byte columns of code tokens; no grammar claim')
    if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
