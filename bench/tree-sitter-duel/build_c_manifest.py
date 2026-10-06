#!/usr/bin/env python3
from pathlib import Path
import hashlib,json,subprocess,sys,time
ROOT=Path(__file__).resolve().parent
language,binary,cc,*flags=sys.argv[1:];binary=Path(binary)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
refs=json.loads((ROOT/'references.lock.json').read_text())
for name,ref in refs.items():
 p=ROOT/'references'/name
 assert subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()==ref['commit']
 assert not subprocess.check_output(['git','-C',str(p),'status','--porcelain'],text=True).strip(),name+' reference modified'
meta={'language':language,'binary_sha256':sha(binary),'adapter_sha256':sha(ROOT/'tree_sitter_adapter.c'),'build_script_sha256':sha(ROOT/'build_tree_sitter.sh'),'references':refs,'compiler':subprocess.check_output([cc,'--version'],text=True).splitlines()[0],'flags':flags,'built_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())}
Path(str(binary)+'.build.json').write_text(json.dumps(meta,indent=2)+'\n')
