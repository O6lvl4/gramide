"""Compare precedence/associativity with CPython AST, never by evaluating code."""
from pathlib import Path
import ast,itertools,json,os,platform,shutil,subprocess,tempfile,keyword,hashlib,sys
ROOT=Path(__file__).resolve().parents[1]
OPS=['+','-','*','/','//','%','@','**','<<','>>','&','^','|','and','or','==','!=','<','<=','>','>=','in','not in','is','is not']
VALID=[f'a {left} b {right} c' for left,right in itertools.product(OPS,repeat=2)]
VALID += ['-a ** b','a ** -b','a ** b ** c','not a == b','not not a','~a ** +b','a if b else c if d else e','a or b if c and d else e','a and (b and c)','(a + b) * c','f(a,b,).value[x + y]','f() ** g(x)','True if flag else None','match + case + type','日本語 + 2']
INVALID=['a +','a **','a ** * b','a if b','a else b','a not b','a is not','if + x','for','f(a,,b)','a[]','a.','a + * b','not','a < < b']
VALID += ['-a ** -b ** c','a - (b - c)','a ** (b ** c)','(a ** b) ** c'] + [name+' + a' for name in keyword.softkwlist]
INVALID += [name for name in keyword.kwlist if name not in ('True','False','None')]
OP={ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Div:'/',ast.FloorDiv:'//',ast.Mod:'%',ast.MatMult:'@',ast.Pow:'**',ast.LShift:'<<',ast.RShift:'>>',ast.BitAnd:'&',ast.BitXor:'^',ast.BitOr:'|',ast.And:'and',ast.Or:'or',ast.Eq:'==',ast.NotEq:'!=',ast.Lt:'<',ast.LtE:'<=',ast.Gt:'>',ast.GtE:'>=',ast.In:'in',ast.NotIn:'not in',ast.Is:'is',ast.IsNot:'is not',ast.USub:'-',ast.UAdd:'+',ast.Invert:'~',ast.Not:'not'}
def reference(n,source):
    if isinstance(n,(ast.Name,ast.Constant)):return ['atom',ast.get_source_segment(source,n)]
    if isinstance(n,ast.BinOp):return ['bin',OP[type(n.op)],reference(n.left,source),reference(n.right,source)]
    if isinstance(n,ast.UnaryOp):return ['unary',OP[type(n.op)],reference(n.operand,source)]
    if isinstance(n,ast.BoolOp):
        out=reference(n.values[0],source)
        for v in n.values[1:]:out=['bool',OP[type(n.op)],out,reference(v,source)]
        return out
    if isinstance(n,ast.Compare):return ['compare',reference(n.left,source),[[OP[type(op)],reference(v,source)] for op,v in zip(n.ops,n.comparators)]]
    if isinstance(n,ast.IfExp):return ['if',reference(n.test,source),reference(n.body,source),reference(n.orelse,source)]
    if isinstance(n,ast.Attribute):return ['attr',reference(n.value,source),n.attr]
    if isinstance(n,ast.Call):return ['call',reference(n.func,source),[reference(v,source) for v in n.args]]
    if isinstance(n,ast.Subscript):return ['sub',reference(n.value,source),reference(n.slice,source)]
    raise AssertionError(ast.dump(n))
def actual(n):
    kids=n['kids'];kind=n['kind']
    if not kids:return ['atom',n['text']]
    if kind in ('binary','boolean'):return ['bin' if kind=='binary' else 'bool',kids[1]['text'],actual(kids[0]),actual(kids[2])]
    if kind=='unary':return ['unary',kids[0]['text'],actual(kids[1])]
    if kind=='power' and len(kids)>1:return ['bin','**',actual(kids[0]),actual(kids[2])]
    if kind=='conditional' and len(kids)>1:return ['if',actual(kids[2]),actual(kids[0]),actual(kids[4])]
    if kind=='comparison' and len(kids)>1:return ['compare',actual(kids[0]),[[' '.join(k['text'] for k in kids[i]['kids']),actual(kids[i+1])] for i in range(1,len(kids),2)]]
    if kind=='primary':
        out=actual(kids[0])
        for suffix in kids[1:]:
            if suffix['kind']=='attribute':out=['attr',out,suffix['kids'][0]['text']]
            elif suffix['kind']=='call':out=['call',out,[actual(k) for k in suffix['kids']]]
            elif suffix['kind']=='subscript':out=['sub',out,actual(suffix['kids'][0])]
            else:raise AssertionError(suffix)
        return out
    assert len(kids)==1,n
    return actual(kids[0])
with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);(project/'src/packages').mkdir(parents=True)
    shutil.copytree(ROOT/'src/packages/python',project/'src/packages/python')
    for file in ['tree.almd','lex.almd','parser.almd']:shutil.copyfile(ROOT/'src'/file,project/'src'/file)
    shutil.copyfile(ROOT/'ci/python_expressions_probe.almd',project/'src/main.almd')
    (project/'almide.toml').write_text('[package]\nname = "expressions_probe"\nversion = "0.1.0"\nedition = "2026"\n')
    binary=project/'probe';data=project/'cases.json'
    subprocess.run([os.environ.get('ALMIDE_BIN','almide'),'build','-o',str(binary)],cwd=project,check=True)
    expected=[reference(ast.parse(s,mode='eval').body,s) for s in VALID]
    for s in INVALID:
        try:ast.parse(s,mode='eval')
        except SyntaxError:pass
        else:raise AssertionError(('reference accepts malformed fixture',s))
    data.write_text(json.dumps(dict(cases=VALID+INVALID),ensure_ascii=False))
    results=json.loads(subprocess.check_output([str(binary),str(data)],text=True,timeout=60))
    assert len(results)==len(VALID)+len(INVALID)
    for source,want,got in zip(VALID,expected,results):
        assert got['ok'],(source,got)
        assert actual(got['tree'])==want,(source,want,actual(got['tree']))
    for source,got in zip(INVALID,results[len(VALID):]):assert not got['ok'],(source,got)
report=dict(python=platform.python_version(),matching_expression_trees=len(VALID),rejected_expressions=len(INVALID),
            expressions_sha256=hashlib.sha256(json.dumps(VALID+INVALID,ensure_ascii=False).encode()).hexdigest(),
            scope='normalized operator trees, conditional order, comparisons, simple call/attribute/subscript structure; not a complete Python grammar')
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
