"""Run an instrumented outline binary, requiring normal output equivalence."""
from pathlib import Path
import argparse,hashlib,json,platform,subprocess,sysconfig
ap=argparse.ArgumentParser(description=__doc__)
for name in ['gramide','profiled','generated-rust','runtime-rlib','output']:ap.add_argument('--'+name,type=Path,required=True)
args=ap.parse_args()
report=dict(python=platform.python_version(),rustc=subprocess.check_output(['rustc','--version'],text=True).strip(),
 method='Rust alloc/alloc_zeroed and realloc requests attributed exclusively to innermost instrumented generated function, including uninstrumented runtime callees; not exact call sites, timing, live heap, RSS or all libc allocations. Instrumentation may affect optimization. Valid normal-return paths only.',
 artifacts={n:dict(sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for n,p in [('normal_binary',args.gramide),('profiled_binary',args.profiled),('generated_rust',args.generated_rust),('runtime_rlib',args.runtime_rlib),('instrumenter',Path(__file__).parent/'instrument_allocations.py')]},cases=[])
for name in ['inspect.py','typing.py','argparse.py','_pydecimal.py','pydoc_data/topics.py']:
 p=Path(sysconfig.get_path('stdlib'))/name
 normal=subprocess.run([str(args.gramide.resolve()),'outline',str(p)],capture_output=True,check=True,timeout=30)
 prof=subprocess.run([str(args.profiled.resolve()),'outline',str(p)],capture_output=True,check=True,timeout=30)
 assert normal.stdout==prof.stdout and not normal.stderr,(name,'output changed')
 rows=[]
 for line in prof.stderr.decode().splitlines():
  assert line.startswith('ALLOC\t'),(name,line)
  _,fn,a,r,b=line.split('\t');rows.append(dict(function=fn,allocations=int(a),reallocations=int(r),requested_bytes=int(b)))
 assert rows,(name,'missing profile')
 rows.sort(key=lambda r:r['allocations']+r['reallocations'],reverse=True)
 case=dict(file=name,source_sha256=hashlib.sha256(p.read_bytes()).hexdigest(),output_sha256=hashlib.sha256(normal.stdout).hexdigest(),allocations=sum(r['allocations'] for r in rows),reallocations=sum(r['reallocations'] for r in rows),functions=rows)
 report['cases'].append(case)
 print(name,case['allocations'],case['reallocations'],flush=True)
args.output.write_text(json.dumps(report,indent=2)+'\n')
