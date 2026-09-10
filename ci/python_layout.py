"""CPython oracle for the Python layout stage, not a full Python lexer claim."""
from pathlib import Path
import io,json,os,platform,re,shutil,subprocess,tempfile,tokenize
ROOT=Path(__file__).resolve().parents[1]
# Strings are already indivisible physical tokens at the layout interface.
VALID=[
 ('nested','if True:\n    if True:\n        x = 1\n    y = 2\nz = 3\n'),
 ('tabs','if True:\n\tx = 1\n\ty = 2\n'),
 ('comments','if True:\n    # misleading indentation\n    x = 1\n  # harmless\n\n    y = 2\n'),
 ('brackets','x = (\n  1 +\n      2\n)\ny = [\n  3,\n4\n]\n'),
 ('continued','x = 1 + \\\n    2\n'),
 ('leading_continued','if True:\n    \\\n      x = 1\n    y = 2\n'),
 ('continued_blank','x = 1 \\\n\ny = 2\n'),
 ('continued_comment','x = 1 \\\n# comment\ny = 2\n'),
 ('zero_leading_continued','if True:\n\\\n    x = 1\n'),
 ('continued_comment_eof','x = 1 \\\n# comment'),
 ('multiline_string','if True:\n    x = """one\nzero indent\n    end"""\n    y = 2\n'),
 ('no_final_newline','if True:\n    x = 1'),
 ('formfeed','if True:\n \f    x = 1\n'),
 ('unicode','if True:\n    日本語 = "🪨"\n    x = 日本語\n'),
 ('crlf','if True:\r\n    x = (1 +\r\n      2)\r\n'),
 ('empty',''),('comments_only','# comment\n\n  # more\n'),
]
def positions(source):
    lines=source.split('\n')
    offsets=[0]
    for line in lines[:-1]:offsets.append(offsets[-1]+len((line+'\n').encode()))
    def at(pos):
        row,col=pos
        if row>len(lines):return len(source.encode())
        return offsets[row-1]+len(lines[row-1][:col].encode())
    def token(kind,text,start,end):
        return dict(kind=kind,text=text,start=at(start),end=at(end),line=start[0],col=len(lines[start[0]-1][:start[1]].encode())+1 if start[0]<=len(lines) else 1)
    return token

def reference_case(name,source):
    compile(source,name,'exec')
    make=positions(source);physical=[];expected=[];previous=0
    raw=source.encode()
    for t in tokenize.generate_tokens(io.StringIO(source).readline):
        if t.type in (tokenize.INDENT,tokenize.DEDENT):
            expected.append('indent' if t.type==tokenize.INDENT else 'dedent');continue
        kind={tokenize.NAME:'identifier',tokenize.NUMBER:'number',tokenize.STRING:'string',tokenize.OP:'punct',tokenize.NEWLINE:'newline',tokenize.NL:'newline',tokenize.COMMENT:'comment',tokenize.ENDMARKER:'eof'}.get(t.type)
        assert kind is not None,(name,t)
        token=make(kind,t.string,t.start,t.end)
        # tokenize omits explicit continuations; restore them from source gaps.
        for match in re.finditer(rb'\\\r?\n',raw[previous:token['start']]):
            start=previous+match.start();end=previous+match.end()
            line=raw[:start].count(b'\n')+1;line_start=raw.rfind(b'\n',0,start)+1
            physical.append(dict(kind='continuation',text=raw[start:end].decode(),start=start,end=end,line=line,col=start-line_start+1))
        previous=token['end']
        if kind=='newline' and not t.string:continue # layout synthesizes EOF newline
        physical.append(token)
        if t.type not in (tokenize.NL,tokenize.COMMENT):expected.append(kind)
    # The oracle may synthesize NEWLINE before ENDMARKER with no source byte.
    if source and not source.endswith(('\n','\r')):
        oracle=list(tokenize.generate_tokens(io.StringIO(source).readline))
        expected=[('indent' if t.type==tokenize.INDENT else 'dedent' if t.type==tokenize.DEDENT else {tokenize.NAME:'identifier',tokenize.NUMBER:'number',tokenize.STRING:'string',tokenize.OP:'punct',tokenize.NEWLINE:'newline',tokenize.ENDMARKER:'eof'}[t.type]) for t in oracle if t.type not in (tokenize.NL,tokenize.COMMENT)]
    return dict(name=name,source=source,tokens=physical),expected

# Invalid layout fixtures use a deliberately small physical-token adapter so
# CPython can reject layout without preventing construction of the input stream.
def plain_case(name,source):
    make=positions(source);tokens=[]
    for line,text in enumerate(source.splitlines(keepends=True),1):
        for m in re.finditer(r'\r?\n|\\\n|[A-Za-z_]+|[0-9]+|[^ \t\r\n\f]',text):
            s=m.group();kind='newline' if s in ('\n','\r\n') else 'continuation' if s=='\\\n' else 'identifier' if s[0].isalpha() else 'number' if s.isdigit() else 'punct'
            tokens.append(make(kind,s,(line,m.start()),(line,m.end())))
    raw=source.encode();tokens.append(dict(kind='eof',text='',start=len(raw),end=len(raw),line=raw.count(b'\n')+1,col=1))
    try:compile(source,name,'exec')
    except SyntaxError as error:line=error.lineno
    else:raise AssertionError(('reference unexpectedly accepts',name))
    return dict(name=name,source=source,tokens=tokens),line
INVALID=[('mixed','if True:\n\tx = 1\n        y = 2\n'),
 ('bad_dedent','if True:\n    x = 1\n  y = 2\n'),
 ('deeper_mixed','if True:\n    if True:\n\tx = 1\n'),
 ('unclosed','x = (1\n'),('mismatched','x = (1]\n'),('dangling_continuation','x = 1 \\\n')]
# Compare indentation spellings at equal and differing visual columns. Only
# lexer-level indentation errors are asserted here; suite syntax belongs to the
# future grammar and is deliberately not attributed to this stage.
spellings=['    ','        ','\t',' \t','\t ','         ','\t\t','                ']
for i,left in enumerate(spellings):
    for j,right in enumerate(spellings):
        name=f'indent_pair_{i}_{j}';source=f'if True:\n{left}x = 1\n{right}y = 2\n'
        try:compile(source,name,'exec')
        except SyntaxError as error:
            if isinstance(error,TabError) or 'unindent does not match' in str(error):INVALID.append((name,source))
        else:VALID.append((name,source))
INVALID.append(('too_many_brackets','x = '+('('*201)+'1'+(')'*201)+'\n'))
INVALID.append(('too_many_indents',''.join(' '*i+'if True:\n' for i in range(101))+' '*101+'x = 1\n'))
with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);(project/'src/packages/python').mkdir(parents=True)
    for file in ['tree.almd','lex.almd','packages/python/layout.almd']:
        shutil.copyfile(ROOT/'src'/file,project/'src'/file)
    shutil.copyfile(ROOT/'ci/python_layout_probe.almd',project/'src/main.almd')
    (project/'almide.toml').write_text('[package]\nname = "layout_probe"\nversion = "0.1.0"\nedition = "2026"\n')
    binary=project/'probe'
    subprocess.run([os.environ.get('ALMIDE_BIN','almide'),'build','-o',str(binary)],cwd=project,check=True)
    valid=[reference_case(*row) for row in VALID];invalid=[plain_case(*row) for row in INVALID]
    cases=[row[0] for row in valid+invalid];data=project/'cases.json';data.write_text(json.dumps({'cases':cases},ensure_ascii=False))
    result=json.loads(subprocess.check_output([str(binary),str(data)],text=True))
    for (case,expected),actual in zip(valid,result):
        assert actual['ok'],(case['name'],actual)
        assert [t['kind'] for t in actual['tokens']]==expected,(case['name'],expected,actual)
        code=lambda ts:[t for t in ts if t['kind'] not in ('newline','indent','dedent','comment','continuation','eof')]
        assert code(actual['tokens'])==code(case['tokens']),case['name']
    for (case,line),actual in zip(invalid,result[len(valid):]):
        assert not actual['ok'],(case['name'],actual)
        assert actual['line']==line,(case['name'],line,actual)
    print(f'CPython {platform.python_version()}: {len(valid)} valid layout cases and {len(invalid)} rejected cases match; source-token byte ranges preserved')
