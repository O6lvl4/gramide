"""Compare Python declaration names and source ranges against CPython AST."""
from pathlib import Path
import ast,json,subprocess,sysconfig,tempfile
BIN=Path(__file__).resolve().parents[1]/'gramide'

def expected(source):
    lines=source.splitlines(keepends=True)
    offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line.encode()))
    rows=[]
    def visit(node,parents=(),owner=''):
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.TypeAlias)):
            function=isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
            cls=isinstance(node,ast.ClassDef)
            name=node.name if function or cls else node.name.id
            decorators=node.decorator_list if function or cls else []
            start=min([node.lineno]+[d.lineno for d in decorators])
            # Declaration indentation is retained by hew's line reader; byte
            # ranges begin at the decorator @ or the declaration keyword.
            col=node.col_offset
            rows.append(dict(name='.'.join((*parents,name)),kind='method' if function and owner else 'function' if function else 'class' if cls else 'type',
                             owner='.'.join(parents) if function and owner else '',start=start,end=node.end_lineno,
                             start_byte=offsets[start-1]+col,end_byte=offsets[node.end_lineno-1]+node.end_col_offset))
            if function or cls:
                for child in node.body:visit(child,(*parents,name),name if cls else '')
            return
        for child in ast.iter_child_nodes(node):visit(child,parents,owner)
    visit(ast.parse(source))
    return rows

def check(path):
    source=path.read_text();raw=source.encode()
    result=subprocess.run([str(BIN),'symbols',str(path)],check=True,capture_output=True,text=True,timeout=30)
    doc=json.loads(result.stdout)
    assert doc['complete'] and doc['lang']=='python',doc
    want=expected(source)
    actual=[{k:s[k] for k in want[0]} for s in doc['symbols']] if want else doc['symbols']
    assert len(actual)==len(want),(path,len(actual),len(want))
    for a,b in zip(actual,want):
        # A suite's optional final semicolon belongs to the parser span.
        end=a['end_byte'];ref=b['end_byte']
        assert end==ref or raw[ref:end].strip()==b';',(path,a,b)
        assert {k:v for k,v in a.items() if k!='end_byte'}=={k:v for k,v in b.items() if k!='end_byte'},(path,a,b)
    return len(want)

with tempfile.TemporaryDirectory() as tmp:
    p=Path(tmp)/'sample.py'
    p.write_text('''# 日本語 tests byte offsets.
@decorate(
    "class")
class Outer:
    @staticmethod
    def method(x):
        def helper(): return "λ"
        class Local:
            async def method(self): return 2
        return helper()

    # Between declarations should not extend method ranges.
    class Inner:
        def method(self):
            text = """\ndef phantom(): pass\n"""
            return text

async def method(): return 0

type Alias[T] = list[T]
''')
    total=check(p)
    stub=Path(tmp)/'sample.pyi';stub.write_text('class C:\n def m(self) -> int: ...\n');total+=check(stub)
    for source in ['def broken(:\n pass\n','x = "\\xZ1"\n','x = b"a" "b"\n','match x:\n case 1+2: pass\n']:
        p.write_text(source)
        for command in ['check','symbols']:
            result=subprocess.run([str(BIN),command,str(p)],capture_output=True,text=True)
            assert result.returncode!=0,(command,source,result.stdout)
            if command=='symbols':assert not result.stdout,(source,result.stdout)
stdlib=Path(sysconfig.get_path('stdlib'))
files=['keyword.py','token.py','stat.py','copyreg.py','genericpath.py','reprlib.py','textwrap.py','inspect.py','tokenize.py','ast.py','dataclasses.py','typing.py']
for name in files:total+=check(stdlib/name)
print(f'Python symbols: {total} declarations match CPython names/owners/ranges; 12 complete stdlib files, nested/decorated/async declarations, stubs, invalid input')
