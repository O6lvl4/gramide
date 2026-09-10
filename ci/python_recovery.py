"""Python logical-line recovery preserves scope and never certifies partial trees."""
from pathlib import Path
import ast,subprocess,tempfile
BIN=Path(__file__).resolve().parents[1]/'gramide'
def run(cmd,path):return subprocess.run([str(BIN),cmd,str(path)],capture_output=True,text=True,timeout=10)
count=0
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'editing.py'
 # Bad expressions must consume the entire logical line; no resuming midway
 # through a call, string, semicolon suite or a skipped indentation block.
 broken=['x =','return +','assert','import','raise from error','x = 1 2','x = ; y = 1','@','if condition','def damaged():','class Damaged:']
 for statement in broken:
  for template in [
   'def before(): pass\n{bad}\ndef after(): pass\n',
   'class Box:\n def before(self): pass\n {bad}\n def after(self): pass\ndef outside(): pass\n',
   'def outer():\n def before(): pass\n {bad}\n def after(): pass\ndef outside(): pass\n',
   'if enabled:\n {bad}\n def inside(): pass\ndef outside(): pass\n',
  ]:
   source=template.format(bad=statement)
   try:ast.parse(source)
   except SyntaxError:pass
   else:raise AssertionError(source)
   p.write_text(template.format(bad='pass'));expected=run('outline',p)
   assert expected.returncode==0 and not expected.stderr,expected
   p.write_text(source)
   outline=run('outline',p)
   assert outline.returncode==0 and outline.stdout==expected.stdout,(source,outline,expected.stdout)
   tree=run('parse',p)
   assert tree.returncode==0 and '(ERROR)' in tree.stdout and '[recovered,' in tree.stderr,(source,tree)
   for cmd in ['check','symbols']:
    result=run(cmd,p);assert result.returncode!=0,(source,cmd,result)
    if cmd=='symbols':assert not result.stdout,(source,result)
   count+=1
 # Bad headers followed by a nested suite must not export that suite's names.
 for header in ['if condition','class Broken','def broken()']:
  p.write_text(f'def before(): pass\n{header}\n def phantom(): pass\n class Hidden:\n  def nested(self): pass\n\n# between scopes\ndef after(): pass\n')
  result=run('outline',p)
  assert result.returncode==0 and result.stdout=='L1-1 function before\nL8-8 function after\n',result
  assert 'phantom' not in result.stdout and 'Hidden' not in result.stdout and 'nested' not in result.stdout,result
  count+=1
 # Nested failure must stop before the enclosing dedent, preserving ownership.
 p.write_text('class Outer:\n class Inner:\n  x =\n def method(self): pass\ndef outside(): pass\n')
 result=run('outline',p)
 assert result.returncode==0 and result.stdout=='L1-4 class Outer\n  L2-3 class Inner\n  L4-4 method Outer.method\nL5-5 function outside\n',result
 count+=1
 # A final malformed line, an all-error file, blank lines and UTF-8 comments.
 for source,expected in [('x =\n',''),('def before(): pass\nx =','L1-1 function before\n'),
                          ('def before(): pass\nx =\n\n# 日本語\n\ndef after(): pass\n','L1-1 function before\nL6-6 function after\n')]:
  p.write_text(source);result=run('outline',p)
  assert result.returncode==0 and result.stdout==expected and '[recovered,' in result.stderr,(source,result)
  count+=1
 # Physical newlines inside brackets/strings do not become resume boundaries.
 p.write_text('x = (1\n +)\ndef after(): pass\n')
 result=run('outline',p);assert result.returncode==0 and result.stdout=='L3-3 function after\n',result
 count+=1
 # A long run of invalid lines must make progress and reach the next declaration.
 p.write_text('x =\n'*2000+'def after(): pass\n')
 result=run('outline',p)
 assert result.returncode==0 and result.stdout=='L2001-2001 function after\n',result
 count+=1
 # Lexical failures are not supported by this recovery layer.
 for source in ['x = (]\ndef after(): pass\n','x = "\\xZZ"\n']:
  p.write_text(source)
  for cmd in ['check','symbols','outline']:
   result=run(cmd,p);assert result.returncode!=0 and not result.stdout,(source,cmd,result)
  count+=1
print(f'Python recovery: {count} cases preserve logical-line boundaries, scopes and strict rejection')
