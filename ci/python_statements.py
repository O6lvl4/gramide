"""Compare statement structure and syntax rejection with CPython."""
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

# Suites, branch ownership, async forms and exception-handler combinations.
for header in ['if x','if x := f()','while x','for x in xs','for x,y in pairs','async for x in xs','with a as x','async with a as x','with (a,b)','with (a,b) as x']:
    for body in [' pass\n','\n    a=1\n    b=2\n']:
        VALID.append(header+':'+body)
VALID += ['if a:\n if b: x=1\n else: x=2\nelse: x=3\n',
          'if a: pass\nelif b: pass\nelif c: pass\nelse: pass\n',
          'while x: break\nelse: pass\n', 'for x in a,b: continue\nelse: pass\n',
          'with (a as x,b as (y,z),): pass\n', 'with a as [x,*y],b: pass\n',
          'if a:\n    # comment\n    for b in xs:\n        if b: continue\n    else:\n        pass\nx=1\n']
for prefix,exceptions,suffix in itertools.product(['except','except*'],['A','A as e','A,B','(A,B) as e','A,',''],['','else: pass\n','finally: pass\n','else: pass\nfinally: pass\n']):
    source=f'try: pass\n{prefix} {exceptions}: pass\n{suffix}'
    try:ast.parse(source)
    except SyntaxError:INVALID.append(source)
    else:VALID.append(source)
VALID += ['with (): pass\n', 'try: pass\nfinally: pass\n', 'try:\n x=1\nexcept A:\n raise\nexcept B as e:\n pass\nelse:\n x=2\nfinally:\n x=3\n',
          'try: pass\nexcept* A: pass\nexcept* B as e: pass\n', 'try: pass\nexcept: pass\nexcept A: pass\n']
INVALID += ['if x:\npass\n','if x:\n','if x: if y: pass\n','else: pass\n','elif x: pass\n',
            'while : pass\n','for f() in xs: pass\n','for x in: pass\n','for x in xs,,: pass\n',
            'with a as f(): pass\n','with a,b,: pass\n','with a as x+y: pass\n',
            'try: pass\n','try: pass\nelse: pass\n','try: pass\nexcept* : pass\n',
            'try: pass\nexcept A: pass\nexcept* B: pass\n','try: pass\nexcept A,B as e: pass\n',
            'try: pass\nfinally: pass\nexcept A: pass\n']

# Full signatures, decorators, generic declarations and type aliases.
for length in range(1,5):
    for categories in itertools.product(range(6),repeat=length):
        params=[['p'+str(i)+': T', 'p'+str(i)+': T=x', '/', '*', '*p'+str(i)+': T', '**p'+str(i)+': T'][c] for i,c in enumerate(categories)]
        source='def f('+','.join(params)+') -> R: pass\n'
        try:ast.parse(source)
        except SyntaxError:INVALID.append(source)
        else:VALID.append(source)
VALID += ['def f(): pass\n','async def f(x): return await x\n',
          '@first\n@second(x)\ndef f(a: T,/,b: U=1,*args: *Ts,c,**kw: V) -> R:\n return a\n',
          'class C(Base, *bases, metaclass=Meta, **kw):\n @property\n def value(self): return 1\n',
          'def outer():\n class Inner:\n  async def method(self): pass\n return Inner\n',
          'type Alias = int | str\n','type Alias[T, *Ts, **P] = tuple[T, *Ts]\n',
          'class C[T: (int,str)=int, *Ts=*tuple[int], **P=[int]](Base[T]): pass\n',
          'def f[T: Bound=Default](x:T) -> T: return x\n',
          'def f(*args: *tuple[int,...]): pass\n','type = 1\n','type(x)\n']
INVALID += ['def f(a=1,b): pass\n','def f(a: *T): pass\n','def f(**kw: *T): pass\n',
            'def f():\n','def f(x) ->: pass\n','async class C: pass\n','@decorator\nx=1\n',
            'class C[]: pass\n','def f[](): pass\n','type A[] = int\n','type A =\n',
            'type A[*Ts: Bound] = T\n','class C(x=1,Base): pass\n']

# Exercise real top-level simple statements without inventing replacements for
# compound suites. Each exact AST source segment becomes a standalone fixture.
stdlib=Path(sysconfig.get_path('stdlib'));stdlib_count=0;stdlib_compound_count=0
simple=(ast.Expr,ast.Assign,ast.AnnAssign,ast.AugAssign,ast.Import,ast.ImportFrom,ast.Assert,ast.Delete)
for name in ['tokenize.py','dataclasses.py','inspect.py','ast.py','typing.py']:
    source=(stdlib/name).read_text()
    for node in ast.parse(source).body:
        if isinstance(node,simple):
            VALID.append(ast.get_source_segment(source,node)+'\n');stdlib_count+=1

compound=(ast.If,ast.While,ast.For,ast.AsyncFor,ast.With,ast.AsyncWith,ast.Try,ast.TryStar)
allowed=simple+compound+(ast.Pass,ast.Break,ast.Continue,ast.Return,ast.Raise,ast.Global,ast.Nonlocal)
for name in ['tokenize.py','dataclasses.py','inspect.py','ast.py','typing.py']:
    source=(stdlib/name).read_text()
    for node in ast.parse(source).body:
        if isinstance(node,compound) and all(isinstance(v,allowed) for v in ast.walk(node) if isinstance(v,ast.stmt)):
            VALID.append(ast.get_source_segment(source,node)+'\n');stdlib_compound_count+=1
for outer,inner in itertools.product(['if outer','while outer','for outer in xs'],['if inner','while inner','for inner in ys']):
    VALID.append(f'{outer}:\n    {inner}:\n        x=1\n    else:\n        x=2\nelse:\n    x=3\nx=4\n')

# Complete source files, now that declarations compose with control-flow suites.
full_files=['keyword.py','token.py','stat.py','copyreg.py','genericpath.py','reprlib.py','textwrap.py','inspect.py','tokenize.py','ast.py']
for name in full_files:VALID.append((stdlib/name).read_text())

def ref_signature(a,source):
    pos=a.posonlyargs+a.args;defaults=[None]*(len(pos)-len(a.defaults))+list(a.defaults)
    ref=lambda v:reference(v,source) if v is not None else None
    param=lambda v,d:[v.arg,ref(v.annotation),ref(d)]
    pairs=[param(v,d) for v,d in zip(pos,defaults)];split=len(a.posonlyargs)
    return dict(posonly=pairs[:split],positional=pairs[split:],vararg=param(a.vararg,None) if a.vararg else None,
                keywordonly=[param(v,d) for v,d in zip(a.kwonlyargs,a.kw_defaults)],kwarg=param(a.kwarg,None) if a.kwarg else None)
def ref_types(params,source):
    ref=lambda v:reference(v,source) if v is not None else None
    return [[{ast.TypeVar:'type_var',ast.TypeVarTuple:'type_var_tuple',ast.ParamSpec:'param_spec'}[type(p)],p.name,ref(getattr(p,'bound',None)),ref(p.default_value)] for p in params]

def ref_stmt(n,source):
    ref=lambda v:reference(v,source) if v is not None else None
    body=lambda nodes:[ref_stmt(v,source) for v in nodes]
    if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):return ['function',n.name,int(isinstance(n,ast.AsyncFunctionDef)),ref_signature(n.args,source),ref(n.returns),[ref(v) for v in n.decorator_list],ref_types(n.type_params,source),body(n.body)]
    if isinstance(n,ast.ClassDef):return ['class',n.name,[ref(v) for v in n.bases],[[v.arg,ref(v.value)] for v in n.keywords],[ref(v) for v in n.decorator_list],ref_types(n.type_params,source),body(n.body)]
    if isinstance(n,ast.TypeAlias):return ['type_alias',n.name.id,ref_types(n.type_params,source),ref(n.value)]
    if isinstance(n,(ast.If,ast.While)):return [type(n).__name__.lower(),ref(n.test),body(n.body),body(n.orelse)]
    if isinstance(n,(ast.For,ast.AsyncFor)):return ['for',int(isinstance(n,ast.AsyncFor)),ref(n.target),ref(n.iter),body(n.body),body(n.orelse)]
    if isinstance(n,(ast.With,ast.AsyncWith)):return ['with',int(isinstance(n,ast.AsyncWith)),[[ref(v.context_expr),ref(v.optional_vars)] for v in n.items],body(n.body)]
    if isinstance(n,(ast.Try,ast.TryStar)):return ['try_star' if isinstance(n,ast.TryStar) else 'try',body(n.body),[[ref(v.type),v.name,body(v.body)] for v in n.handlers],body(n.orelse),body(n.finalbody)]
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

def act_block(n):return [act_stmt(v) for v in n['kids'] if v['kind'] not in ('newline','indent','dedent')]
def act_else(nodes):
    if not nodes:return []
    n=nodes[0]
    return [act_stmt(n)] if n['kind']=='if_stmt' else act_block(n['kids'][0])

def maybe_node(n):return actual(n['kids'][0]) if n['kids'] else None
def act_types(n):
    out=[]
    for p in n['kids']:
        parts=p['kids'];bound=None;default=None
        for v in parts[1:]:
            if v['kind']=='bound':bound=maybe_node(v)
            elif v['kind']=='default':default=maybe_node(v)
        out.append([p['kind'],parts[0]['text'],bound,default])
    return out
def act_signature(n):
    out=dict(posonly=[],positional=[],vararg=None,keywordonly=[],kwarg=None);keywordonly=False
    def param(p):
        parts=p['kids'];annotation=None;default=None
        for v in parts[1:]:
            if v['kind']=='annotation':annotation=maybe_node(v)
            elif v['kind']=='default':default=maybe_node(v)
        return [parts[0]['text'],annotation,default]
    for p in n['kids']:
        if p['text']=='/' and not p['kids']:out['posonly']=out['positional'];out['positional']=[]
        elif p['text']=='*' and not p['kids']:keywordonly=True
        elif p['kind'] in ('vararg','kwarg'):out[p['kind']]=param(p['kids'][0]);keywordonly=True
        else:out['keywordonly' if keywordonly else 'positional'].append(param(p))
    return out

def act_stmt(n):
    k=n['kind'];kids=n['kids'];at=lambda i:actual(kids[i]) if i<len(kids) else None
    if k=='function_declaration':
        offset=int(kids[1]['text']=='async')
        decorators=[actual(v) for v in kids[0]['kids'] if v['kind']!='newline']
        return ['function',kids[1+offset]['text'],offset,act_signature(kids[3+offset]),maybe_node(kids[4+offset]),decorators,act_types(kids[2+offset]),act_block(kids[5+offset])]
    if k=='class_declaration':
        bases=[];keywords=[]
        for v in kids[3]['kids']:
            if v['kind']=='keyword':keywords.append([v['kids'][0]['text'],actual(v['kids'][1])])
            elif v['kind']=='mapping':keywords.append([None,actual(v['kids'][0])])
            else:bases.append(actual(v))
        return ['class',kids[1]['text'],bases,keywords,[actual(v) for v in kids[0]['kids'] if v['kind']!='newline'],act_types(kids[2]),act_block(kids[4])]
    if k=='type_alias':return [k,kids[0]['text'],act_types(kids[1]),at(2)]
    if k in ('if_stmt','while_stmt'):return [k.removesuffix('_stmt'),at(0),act_block(kids[1]),act_else(kids[2:])]
    if k=='for_stmt':
        offset=int(kids[0]['text']=='async')
        return ['for',offset,at(offset),at(offset+1),act_block(kids[offset+2]),act_else(kids[offset+3:])]
    if k=='with_stmt':
        offset=int(kids[0]['text']=='async')
        items=[[actual(v['kids'][0]),actual(v['kids'][1]) if len(v['kids'])>1 else None] for v in kids[offset]['kids']]
        return ['with',offset,items,act_block(kids[offset+1])]
    if k in ('try_stmt','try_star'):
        handlers=[];orelse=[];final=[]
        for node in kids[1:]:
            if node['kind']=='handlers':
                for h in node['kids']:
                    spec=h['kids'][0]['kids']
                    handlers.append([actual(spec[0]) if spec else None,spec[1]['text'] if len(spec)>1 else None,act_block(h['kids'][1])])
            elif node['kind']=='else':orelse=act_block(node['kids'][0])
            elif node['kind']=='finally':final=act_block(node['kids'][0])
        return ['try' if k=='try_stmt' else k,act_block(kids[0]),handlers,orelse,final]
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
report=dict(python=platform.python_version(),matching_statement_trees=len(VALID),stdlib_simple_statements=stdlib_count,stdlib_compound_statements=stdlib_compound_count,full_stdlib_files=full_files,rejected_statements=len(INVALID),source_sha256=hashlib.sha256(json.dumps(VALID+INVALID,ensure_ascii=False).encode()).hexdigest(),scope='statement/declaration structure; no match, contextual compiler checks or literal decoding')
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
