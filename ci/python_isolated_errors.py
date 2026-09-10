"""Isolated ASCII errors/stray closers preserve logical lines and ownership."""
from pathlib import Path
import ast,json,re,subprocess,tempfile
BIN=Path(__file__).resolve().parents[1]/'gramide'
count=0

def run(command,path):
 return subprocess.run([str(BIN),command,str(path)],capture_output=True,text=True,timeout=10)

with tempfile.TemporaryDirectory() as tmp:
 path=Path(tmp)/'editing.py'
 def case(source,names):
  global count
  try:ast.parse(source)
  except SyntaxError:pass
  else:raise AssertionError(source)
  path.write_bytes(source.encode())
  result=run('symbols-recovered',path)
  assert result.returncode==0,(source,result)
  doc=json.loads(result.stdout)
  assert not doc['complete'] and doc['errors'] and doc['diagnostic'],doc
  assert [s['name'] for s in doc['symbols']]==names,(source,doc)
  raw=source.encode()
  for s in doc['symbols']:
   assert all(s['end_byte']<=e['start_byte'] or s['start_byte']>=e['end_byte'] for e in doc['errors']),doc
   fragment=raw[s['start_byte']:s['end_byte']]
   assert fragment.startswith(('def '+s['name'].split('.')[-1]+'(').encode()),s
   assert b'\n' not in fragment and b'\r' not in fragment,s
   line=len(re.findall(rb'\r\n|\r|\n',raw[:s['start_byte']]))+1
   assert s['start']==s['end']==line,s
  for command in ['check','symbols','tokens']:
   result=run(command,path)
   assert result.returncode!=0 and not result.stdout,(source,command,result)
  count+=1
 for bad in [')',']','}','$','`','?','\x01']:
  for newline in ['\n','\r\n','\r']:
   for template,names in [
    ('def before(): pass\n{bad}\ndef after(): pass\n',['before','after']),
    ('class Box:\n def good(self): pass\n {bad}\n def next(self): pass\n',['Box.good','Box.next']),
    ('def outer():\n def good(): pass\n {bad}\n def next(): pass\n',['outer.good','outer.next']),
    ('{bad}\n',[]),
   ]:case(template.format(bad=bad).replace('\n',newline),names)
  case('# 日本語\ndef before(): pass\n'+bad,['before'])
  case('def before(): pass\nx = '+bad+'; def phantom(): pass\ndef after(): pass\n',['before','after'])
 # A broken header cannot promote its nested declarations.
 for header in ['def broken$():','class Broken?:','if enabled]:']:
  case(header+'\n def phantom(): pass\ndef after(): pass\n',['after'])
 # Delimiters/invalid ASCII inside literals or comments are ordinary content.
 source='def kept():\n text = ") ] } $ ` ?"\n raw = r"$)"\n # ) ] } $ ` ?\n return text\n'
 ast.parse(source);path.write_text(source)
 strict=json.loads(subprocess.check_output([str(BIN),'symbols',str(path)]))
 recovered=json.loads(subprocess.check_output([str(BIN),'symbols-recovered',str(path)]))
 assert recovered['complete'] and not recovered['errors'] and recovered['symbols']==strict['symbols'],recovered
 # An unknown character inside an unclosed bracket cannot create a restart line.
 case('def before(): pass\nx = ($\n def phantom(): pass\n',['before'])
 # Mismatched existing brackets, NUL and bad escape validation remain failures.
 for source in ['x = (]\n','x = "\x00"\n','x = "\\xZZ"\n']:
  path.write_bytes(source.encode());result=run('symbols-recovered',path)
  assert result.returncode!=0 and not result.stdout,(source,result)
print(f'Python isolated errors: {count} recovery cases, strict rejection, exact retained ranges and literal containment passed')
