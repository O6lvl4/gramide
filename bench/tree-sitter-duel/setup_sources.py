#!/usr/bin/env python3
"""Fetch only the explicit public source pins; never reset an existing checkout."""
from pathlib import Path
import hashlib,json,subprocess
ROOT=Path(__file__).resolve().parent
def run(*args):return subprocess.check_output(args,text=True).strip()
for lock,directory in [('source-pins.json','sources'),('references.lock.json','references')]:
 for name,info in json.loads((ROOT/lock).read_text()).items():
  dest=ROOT/directory/name;dest.parent.mkdir(parents=True,exist_ok=True)
  if not dest.exists():
   subprocess.run(['git','clone','--no-checkout','--filter=blob:none',info['url'],str(dest)],check=True)
   subprocess.run(['git','-C',str(dest),'checkout','--detach',info['commit']],check=True)
  actual=run('git','-C',str(dest),'rev-parse','HEAD')
  if actual!=info['commit'] or run('git','-C',str(dest),'status','--porcelain'):
   raise SystemExit(f'Refusing mismatched/dirty existing checkout: {dest}')
  if 'license_sha256' in info:
   path=next(p for p in [dest/'LICENSE',dest/'LICENSE.md'] if p.exists())
   assert hashlib.sha256(path.read_bytes()).hexdigest()==info['license_sha256'],path
  print(name,actual)
