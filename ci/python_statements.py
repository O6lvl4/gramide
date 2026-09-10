"""Compare simple-statement structure and syntax rejection with CPython."""
from pathlib import Path
import ast,hashlib,itertools,json,os,platform,shutil,subprocess,sys,sysconfig,tempfile,warnings
from python_ast import reference,actual,OP
warnings.simplefilter('ignore',SyntaxWarning)
ROOT=Path(__file__).resolve().parents[1]
VALID=['', '# comment\n', 'pass\nbreak\ncontinue\n', 'a=1; b=2; a+b;\n', 'return\n', 'return a,b\n', 'yield\n', 'yield from xs\n', 'raise\n', 'raise E(x) from cause\n', 'assert a, message\n', 'global a,b\n', 'nonlocal a,b\n', 'del a,b[0],c.x\n', 'import a.b as c,d\n', 'from ..a.b import (x as y,z,)\n', 'from ... import *\n', 'a=b=c=1\n', 'a,b = c,*xs\n', 'x: list[int]\n', '(x): int = 1\n', 'x.y: int = yield 1\n', 'type = 1\n', 'f"{value}"\n']
INVALID=[';\n','a;;b\n','a=\n','a=b=\n','return yield x\n','raise from x\n','assert\n','global a,\n','nonlocal\n','del *x\n','del f()\n','import a,\n','import a as\n','from import a\n','from . import (a,,b)\n','from x import a,\n','from x import (*)\n','from x import a.b\n','a,b: int\n','f(): int\n','1=2\n']
for target,op,rhs in itertools.product(['a','(a)','a.b','a[0]','f().x','a,b','[a,*b]','*a','1','a+b','f()'],['=','+=',': int ='],['x','x,y','yield x','lambda: x']):
    source=f'{target} {op} {rhs}\n'
    try:ast.parse(source)
    except (SyntaxError,UnicodeError):INVALID.append(source)
    else:VALID.append(source)
for dots,module,names in itertools.product(['','.','..','...','....','.....'],['','a','a.b'],['x','x as y,z','(x,)','*','()','x,']):
    source=f'from {dots}{module} import {names}\n'
    try:ast.parse(source)
    except SyntaxError:INVALID.append(source)
    else:VALID.append(source)
for target in ['a','a,b','(a,b)','[a,b]','()','[]','(a)','f().x','f()[0]','[a,*b]','a+b','None']:
    source=f'del {target}\n'
    try:ast.parse(source)
    except SyntaxError:INVALID.append(source)
    else:VALID.append(source)

# Exercise real top-level simple statements without inventing replacements for
# compound suites. Each exact AST source segment becomes a standalone fixture.
stdlib=Path(sysconfig.get_path('stdlib'));stdlib_count=0
simple=(ast.Expr,ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Import,ast.ImportFrom,ast.Assert,ast.Delete)
for name in ['tokenize.py','dataclasses.py','inspect.py','ast.py','typing.py']:
    source=(stdlib/name).read_text()
    for node in ast.parse(source).body:
        if isinstance(node,simple):
            VALID.append(ast.get_source_segment(source,node)+'\n');stdlib_count+=1

def ref_stmt(n,source):
    ref=lambda v:reference(v,source) if v is not None else None
    if isinstance(n,ast.Expr):return ['expr_stmt',ref(n.value)]
    if isinstance(n,ast.Assign):return ['assign',[ref(t) for t in n.targets],ref(n.value)]
    if isinstance(n,ast.AnnAssign):return ['annassign',ref(n.target),ref(n.annotation),ref(n.value),n.simple]
    if isinstance(n,ast.AugAssign):return ['augassign',ref(n.target),OP[type(n.op)],ref(n.value)]
    if isinstance(n,ast.Return):return ['return',ref(n.value)]
    if isinstance(n,ast.Raise):return ['raise',ref(n.exc),ref(n.cause)]
    if isinstance(n,ast.Assert):return ['assert',ref(n.test),ref(n.msg)]
    if isinstance(n,(ast.Pass,ast.Break,ast.Continue)):return [type(n).__name__.lower()]
    if isinstance(n,(ast.Global,ast.Nonlocal)):return [type(n).__name__.lower(),n.names]
    if isinstance(n,ast.Delete):return ['delete',[ref(t) for t in n.targets]]
    if isinstance(n,ast.Import):return ['import',[[a.name,a.asname] for a in n.names]]
    if isinstance(n,ast.ImportFrom):return ['import_from',n.module,n.level,[[a.name,a.asname] for a in n.names]]
    raise AssertionError(ast.dump(n))

def alias(n):
    kids=n['kids'];name=kids[0]
    return ['.'.join(k['text'] for k in name['kids']) if name['kind']=='dotted_name' else name['text'],kids[1]['text'] if len(kids)>1 else None]

def act_stmt(n):
    k=n['kind'];kids=n['kids'];at=lambda i:actual(kids[i]) if i<len(kids) else None
    if k=='expr_stmt':return [k,at(0)]
    if k=='assign':return [k,[actual(v) for v in kids[:-1]],actual(kids[-1])]
    if k in ('annassign','annassign_simple'):return ['annassign',at(0),at(1),at(2),int(k=='annassign_simple')]
    if k=='augassign':return [k,at(0),kids[1]['text'][:-1],at(2)]
    if k=='return':return [k,at(0)]
    if k in ('raise','assert'):return [k,at(0),at(1)]
    if k in ('pass','break','continue'):return [k]
    if k in ('global','nonlocal'):return [k,[v['text'] for v in kids]]
    if k=='delete':return [k,[actual(v) for v in kids]]
    if k=='import':return [k,[alias(v) for v in kids]]
    if k=='import_from':
        module=None;level=0
        for p in kids[0]['kids']:
            if p['kind']=='dotted_name':module='.'.join(v['text'] for v in p['kids'])
            else:level+=len(p['text'])
        return [k,module,level,[alias(v) for v in kids[1:]]]
    raise AssertionError(n)

with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);(project/'src/packages').mkdir(parents=True)
    shutil.copytree(ROOT/'src/packages/python',project/'src/packages/python')
    for name in ['tree.almd','lex.almd','parser.almd']:shutil.copyfile(ROOT/'src'/name,project/'src'/name)
    shutil.copyfile(ROOT/'ci/python_statements_probe.almd',project/'src/main.almd')
    (project/'almide.toml').write_text('[package]\nname = "statements_probe"\nversion = "0.1.0"\nedition = "2026"\n')
    binary=project/'probe';data=project/'cases.json'
    subprocess.run([os.environ.get('ALMIDE_BIN','almide'),'build','-o',str(binary)],cwd=project,check=True)
    expected=[[ref_stmt(n,s) for n in ast.parse(s).body] for s in VALID]
    for s in INVALID:
        try:ast.parse(s)
        except (SyntaxError,UnicodeError):pass
        else:raise AssertionError(('reference accepts invalid fixture',s))
    data.write_text(json.dumps(dict(cases=VALID+INVALID),ensure_ascii=False))
    results=json.loads(subprocess.check_output([str(binary),str(data)],text=True,timeout=60))
    assert len(results)==len(VALID)+len(INVALID)
    for source,want,got in zip(VALID,expected,results):
        assert got['ok'],(source,got)
        result=[act_stmt(n) for n in got['tree']['kids'] if n['kind']!='newline']
        assert result==want,(source,want,result)
    for source,got in zip(INVALID,results[len(VALID):]):assert not got['ok'],(source,got)
report=dict(python=platform.python_version(),matching_statement_trees=len(VALID),stdlib_simple_statements=stdlib_count,rejected_statements=len(INVALID),source_sha256=hashlib.sha256(json.dumps(VALID+INVALID,ensure_ascii=False).encode()).hexdigest(),scope='simple statement structure; no compound statements, type aliases, contextual compiler checks or literal decoding')
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
