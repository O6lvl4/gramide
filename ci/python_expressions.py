"""Compare precedence/associativity with CPython AST, never by evaluating code."""
from pathlib import Path
import warnings
warnings.simplefilter("ignore", SyntaxWarning)
import ast,itertools,json,os,platform,shutil,subprocess,tempfile,keyword,hashlib,sys
ROOT=Path(__file__).resolve().parents[1]
OPS=['+','-','*','/','//','%','@','**','<<','>>','&','^','|','and','or','==','!=','<','<=','>','>=','in','not in','is','is not']
VALID=[f'a {left} b {right} c' for left,right in itertools.product(OPS,repeat=2)]
VALID += ['-a ** b','a ** -b','a ** b ** c','not a == b','not not a','~a ** +b','a if b else c if d else e','a or b if c and d else e','a and (b and c)','(a + b) * c','f(a,b,).value[x + y]','f() ** g(x)','True if flag else None','match + case + type','日本語 + 2']
INVALID=['a +','a **','a ** * b','a if b','a else b','a not b','a is not','if + x','for','f(a,,b)','a[]','a.','a + * b','not','a < < b']
VALID += ['-a ** -b ** c','a - (b - c)','a ** (b ** c)','(a ** b) ** c'] + [name+' + a' for name in keyword.softkwlist]
INVALID += [name for name in keyword.kwlist if name not in ('True','False','None')]
# Container displays, unpacking and slices preserve structure, not just acceptance.
VALID += ['()', '(*a,)', 'a,', 'a[()]', '(a,)', 'a,b', '(a,b,)', '[a,*b,c]', '{a,*b}', '{}', '{a:b, **c}', 'a[:]', 'a[::]', 'a[1::2]', 'a[:,b,...]', 'a[*b]', 'a[1,]', 'a[(1,)]', '{(a,b): [c, d]}']
for lower,upper,step in itertools.product(['','a','a + b'],repeat=3):
    VALID.append(f'items[{lower}:{upper}:{step}]')
for item in ['a','a + b','a if b else c','f(a)','[a,b]','{a:b}']:
    for template in ['[{}, x]','({}, x)','{{{}, x}}','{{x: {}, **y}}']:
        VALID.append(template.format(item))
INVALID += ['*a,', '[*]', '[**x]', '{*}', '{**}', '{a:}', '{:a}', '{a:b,c}', '{a,b:c}', '(*a)', 'a[:::]', 'a[1,,2]', 'a[**x]', '[a,,b]', '(a,,b)']
# Exhaust all four argument categories through five positions, including
# orderings that CPython rejects. Unique keyword names avoid semantic duplicates.
for length in range(1,6):
    for categories in itertools.product(range(4),repeat=length):
        items=[['x', f'k{i}=x', '*xs', '**kw'][category] for i,category in enumerate(categories)]
        source='f('+','.join(items)+(',' if length%2 else '')+')'
        try:ast.parse(source,mode='eval')
        except (SyntaxError,UnicodeError):INVALID.append(source)
        else:VALID.append(source)
VALID += ['f(*a if b else c)', 'f(**a if b else c)', 'f(x=1,*a,**b,y=2)', 'f(*a,b,*c)', 'f(x=g(y=1), **h(z=2))']
VALID += ['f('+','.join('x' for _ in range(2000))+')', 'f('+','.join(f'k{i}=x' for i in range(2000))+')']
INVALID += ['f(x=)', 'f(=x)', 'f(a.b=x)', 'f((a)=x)', 'f(*a=1)', 'f(**)', 'f(*,)', 'f(x=1,,)', 'f(for=1)']
# Named expressions are only admitted at the grammar's designated positions.
for template in ['({})','[{}]','{{{}}}','({},)','f({})','a[{}]']:
    for rhs in ['a','a + b','a if b else c','(b := c)']:
        VALID.append(template.format('x := '+rhs))
INVALID += ['x := a', 'x := a, b', '(a.b := x)', '(a[0] := x)', '((a) := x)', 'f(x=a := b)', 'a[x := 1:]', '{x := 1: y}', '[*x := y]']
# Product coverage includes nested destructuring and receiver chains with calls.
for target in ['x','x,y','(x,y)','[x,*y]','(x,(y,*z))','obj.x','obj[x]','f().x','f()[x]','obj.x[y].z','()','[]']:
    for iterable in ['xs','a or b','f(x=1)','(a if b else c)']:
        for template in ['[x for {} in {}]','{{x for {} in {}}}','{{x:y for {} in {}}}','(x for {} in {})','f(x for {} in {})']:
            VALID.append(template.format(target,iterable))
VALID += ['(a,b := x)', '[x for x in xs if x if x > 1]', '[x+y for x in xs for y in ys if y]', '[x async for x in xs if x]', '[x async for x in xs for y in ys]', '[(y := x) for x in xs]', '[y := x for x in xs]', '{y := x for x in xs}', '(y := x for x in xs)', 'f((x for x in xs), y=1)', '[x for x in xs if (y := x)]', 'a[*x if y else z]', '[(x,y) for x in [a for a in xs] for y in ys]']
INVALID += ['[x for f() in xs]', '[x for a+b in xs]', '[x for 1 in xs]', '[x for x.y() in xs]', '[x for x in]', '[x for in xs]', '[x for x in xs if]', '[x for x in xs if y else z]', '[x for x in a if b else c]', '[x for x in xs,]', '[*x for x in xs]', '{**x for x in xs}', 'f(x for x in xs,)', 'f(x for x in xs,y)', '[x for x in xs if y := x]', '[x for **y in xs]']
# Assignment target acceptance is independently classified by CPython's parser.
for target in ['*x','(*x)','(*x,)','*x,y','(x)','((x))','[x,y.z]','x,','(x,)','[x,]',
               '[*x,*y]','[1,x]','{x}','{x:y}','x if y else z','x or y','x+y','await x',
               'x:=y','x.y()','x[y]()','x().y','x()[y]','(x+y).z','(x+y)[z]',
               'f(x for x in xs).y','f(x for x in xs)[y]','True','None','...']:
    source=f'[x for {target} in xs]'
    try:ast.parse(source,mode='eval')
    except (SyntaxError,UnicodeError):INVALID.append(source)
    else:VALID.append(source)
for async_a,async_b,filter_a,filter_b in itertools.product(['','async '],['','async '],['',' if x'],['',' if y if z']):
    VALID.append(f'[x+y {async_a}for x in xs{filter_a} {async_b}for y in ys{filter_b}]')
# Parameter category order, defaults across '/', and keyword-only phases.
for length in range(1,5):
    for categories in itertools.product(range(6),repeat=length):
        params=[['p'+str(i), 'p'+str(i)+'=x', '/', '*', '*p'+str(i), '**p'+str(i)][category] for i,category in enumerate(categories)]
        source='lambda '+','.join(params)+': x'
        try:ast.parse(source,mode='eval')
        except (SyntaxError,UnicodeError):INVALID.append(source)
        else:VALID.append(source)
VALID += ['lambda: x', 'lambda x,/: x', 'lambda a,b=1,/,c=2,*args,d,e=3,**kw: a',
          'lambda a,/,b,c=1,*,d,e=2,**kw: c', 'lambda a=1,/: a', 'lambda a=1,/,**kw: a',
          'lambda a=lambda b: b: a', 'lambda a=(x:=1): a', 'lambda x: lambda y: x+y',
          'lambda x: a if b else c', '(lambda x:x)(1)', 'f(lambda: x)', '[lambda x:x for x in xs]',
          'lambda x, y=1,: x', 'lambda *args,: args', 'lambda **kw,: kw',
          'await f().x[y] ** -z', '-await f() ** x', 'await (await f())', 'f(await g())',
          '[await f(x) async for x in xs]', '(yield)', '(yield x)', '(yield x,)', '(yield x,y)',
          '(yield *xs, y)', '(yield from f())', '(yield from a if b else c)',
          'lambda: (yield x)', '(yield (x:=1))', 'f((yield x))']
INVALID += ['lambda /:x', 'lambda *:x', 'lambda *,**kw:x', 'lambda a=1,b:x',
            'lambda a=1,/,b:x', 'lambda *a=1:x', 'lambda **a=1:x', 'lambda (a,b):x',
            'lambda x:int: x', 'lambda a,,b:x', 'lambda a:','lambda a -> b: x',
            'await -x','await await f()', 'yield x', '(yield from)', '(yield from *xs)',
            '(yield x := 1)', 'f(yield x)']
for op in OPS:
    VALID += [f'await f() {op} x', f'x {op} await f()']
VALID += ['a if b else lambda x: x', 'lambda: a if b else lambda: c',
          '(lambda x: x) if flag else other', 'lambda x=lambda: a if b else c: x',
          'lambda x=(lambda y=1,/:y):x', 'lambda a,/,*args,b=1,**kw: (yield from args)',
          '(yield *xs)', '(yield x,*ys,z,)', '(yield (a,b))', '(await f()).x',
          '(await f())()', 'await f(x for x in xs)', '[x for (lambda: x)().y in xs]']
INVALID += ['a if lambda: b else c', 'a or lambda: b', 'lambda x: y := z',
            '(yield from a,b)', '(yield *a if b else c)', 'await lambda: x',
            'lambda **kw,*args:x', 'lambda *,x,/:x']
# String families and source-sensitive replacement-field syntax.
for length in range(1,5):
    for pieces in itertools.product(['"text"', 'b"data"', 'f"{x}"', 't"{x}"'],repeat=length):
        source=' '.join(pieces)
        try:ast.parse(source,mode='eval')
        except (SyntaxError,UnicodeError):INVALID.append(source)
        else:VALID.append(source)
for prefix,quote,body in itertools.product(['f','F','fr','RF','t','T','tr','RT'],[chr(34),chr(39),chr(34)*3,chr(39)*3],
        ['', 'plain', '{{x}}', '{x}', '{x=}', '{ x = }', '{x!r}', '{x!s}', '{x!a}', '{x!q}', '{x! r}', '{x !r }',
         '{x:}', '{x= :}', '{x:>{width}.{precision}}', '{x:{y:{z}}}', '{x,y}', '{*x,}', '{yield x}', '{yield from xs}',
         '{(x:=1)}', '{x:=10}', '{(lambda: x)()}', '{lambda: x}', '{x+}', '{x!}', '{}', '{f"{y}"}', '{t"{y}"}',
         '{[x for x in xs]}', '{ {"key": value} }', '日本語 {name}']):
    source=prefix+quote+body+quote
    try:ast.parse(source,mode='eval')
    except (SyntaxError,UnicodeError):INVALID.append(source)
    else:VALID.append(source)
VALID += ['"a" "b"', 'b"a" BR"b"', 'f"a{x}" "tail" f"{y}"', 't"{x}" t"{y}"',
          'f"{x!r:>{width}}"', 'f"{x=:.2f}"', 'f"{await f()}"', 'f"{x # comment\n}"']
INVALID += ['f"{x!\tr}"', 'f"{x!\nr}"', 'f"{x!rr}"', 'f"{x!R}"', 'f"{x!1}"', 'f"{x!r!s}"']
# Numeric escape rejection must respect raw/bytes modes and interpolation nesting.
for prefix,quote,body in itertools.product(['','u','r','b','br','rb','f','fr','t','tr'],[chr(34),chr(39)*3],
        [r'\x',r'\x0',r'\xGG',r'\x00',r'\xff',r'\x001',r'\u',r'\u123',r'\u1234',r'\uD800',
         r'\U00000000',r'\U0010ffff',r'\U00110000',r'\Uffffffff',r'\U1234567',r'\U0000GGGG',
         r'\\x',r'\\u',r'\123',r'\777',r'\q',r'\X',r'\\\x00']):
    source=prefix+quote+body+quote
    try:ast.parse(source,mode='eval')
    except (SyntaxError,UnicodeError):INVALID.append(source)
    else:VALID.append(source)
for source in [r'f"\x{x}"',r'f"{x:>\x}"',r't"{x:>\U00110000}"',r'fr"{x:>\x}"',
               'f"{r\'\\x\'}"', 'fr"{\'\\x\'}"', 'f"{fr\'\\x{x}\'}"', 'fr"{f\'\\x{x}\'}"', 'f"\\{x}"']:
    try:ast.parse(source,mode='eval')
    except (SyntaxError,UnicodeError):INVALID.append(source)
    else:VALID.append(source)
from python_ast import reference,actual
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
        except (SyntaxError,UnicodeError):pass
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
            scope='normalized operator trees, conditional order, comparisons, call/attribute/subscript structure, displays, unpacking, slices, call argument ordering, named expressions, comprehensions, lambdas, yield/await, string families, interpolation fields and numeric escape validation (literal decoding excluded); not a complete Python grammar')
if len(sys.argv)>1:Path(sys.argv[1]).write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
