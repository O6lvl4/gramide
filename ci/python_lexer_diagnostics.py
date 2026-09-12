"""Deferred fallback diagnostics retain the original physical byte position."""
from pathlib import Path
import subprocess,tempfile
BIN=Path(__file__).resolve().parents[1]/'gramide'
cases=[
 ('$',1,1,'unexpected Python character'),
 ('  $',1,3,'unexpected Python character'),
 ('# 日本語\r\nx = \\q\r\n',2,5,'unexpected character after line continuation'),
 ('é = $\n',1,6,'unexpected Python character'),
 ('x = f"{$}"',1,8,'unexpected Python character'),
 ('x = t"{\\q}"',1,8,'unexpected character after line continuation'),
 ('x = '+'f"{'*101+'x'+'}"'*101,1,305,'too many nested interpolated strings'),
]
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)/'bad.py'
 for source,line,col,message in cases:
  p.write_bytes(source.encode())
  for command in ['tokens','check','symbols']:
   r=subprocess.run([str(BIN),command,str(p)],capture_output=True,text=True,timeout=10)
   assert r.returncode!=0 and not r.stdout,(source,command,r)
   assert r.stderr==f'{p}:{line}:{col}: {message}\n',(source,command,r.stderr)
print('Python lexer diagnostics: 21 strict command checks preserve messages and byte positions')
