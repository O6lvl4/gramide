"""Recover ordinary-string boundaries without inventing declarations in literals."""
from pathlib import Path
import subprocess,tempfile
BIN=Path(__file__).resolve().parents[1]/'gramide'
def run(cmd,p):return subprocess.run([str(BIN),cmd,str(p)],capture_output=True,text=True,timeout=10)
count=0
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'editing.py'
 def case(source,want):
  global count
  p.write_bytes(source.encode())
  result=run('outline',p)
  assert result.returncode==0 and result.stdout==want and '[recovered,' in result.stderr,(source,result,want)
  tree=run('parse',p)
  assert tree.returncode==0 and '(ERROR)' in tree.stdout,(source,tree)
  for cmd in ['check','symbols','tokens']:
   result=run(cmd,p);assert result.returncode!=0 and not result.stdout,(source,cmd,result)
  count+=1
 for prefix in ['', 'r','R','u','U','b','B','br','bR','Br','BR','rb','rB','Rb','RB']:
  for quote in ['"',"'"]:
   for newline in ['\n','\r\n','\r']:
    case(newline.join(['def before(): pass',f'x = {prefix}{quote}bad','def after(): pass','']),
         'L1-1 function before\nL3-3 function after\n')
   case(f'def before(): pass\nx = {prefix}{quote}bad', 'L1-1 function before\n')
   case(f'def outer():\n x = {prefix}{quote*3}bad\ndef phantom(): pass\n', 'L1-3 function outer\n')
 # Escaped physical newlines belong to the invalid literal, not to code.
 for newline in ['\n','\r\n','\r']:
  case('def before(): pass'+newline+'x = "bad\\'+newline+'def phantom(): pass'+newline+'def after(): pass'+newline,
       'L1-1 function before\nL4-4 function after\n')
  case('def outer():'+newline+' x = """bad'+newline+'def phantom(): pass'+newline, 'L1-3 function outer\n')
 # A closed, invalid bytes literal still has a usable lexical end.
 for literal in ['b"日本語"', "br'λ'", 'b"""日本語\ninside"""']:
  source='def before(): pass\nx = '+literal+'\ndef after(): pass\n'
  line=source.splitlines().index('def after(): pass')+1
  case(source,f'L1-1 function before\nL{line}-{line} function after\n')
 # A failed string in a nested suite must retain its parent and sibling owners.
 case('class Box:\n def method(self):\n  x = "bad\n def next(self): pass\ndef outside(): pass\n',
      'L1-4 class Box\n  L2-3 method Box.method\n  L4-4 method Box.next\nL5-5 function outside\n')
 # Missing brackets, NUL and bad escapes remain unsupported.
 for source in ['x = ("bad\ndef after(): pass\n',
                'x = "\\xZZ"\n','x = "\x00"\n']:
  p.write_bytes(source.encode());result=run('outline',p)
  assert result.returncode!=0 and not result.stdout,(source,result)
  count+=1
print(f'Python ordinary-string recovery: {count} prefix/quote/newline/boundary and rejection cases passed')
