"""Time one command against another binary, on the same files, with identical output required.

Usage: python3 bench/verb_timing.py --before ./a --after ./b --verb tokens \
           --output docs/evidence/x.json [--samples 21] [--files stat.py ast.py ...]

Files are named relative to the running interpreter's stdlib, or given as a path
of their own. Every sample is a
fresh process and startup is included, as in bench/python_outline.py; the two
binaries are interleaved and shuffled so the machine's load falls on both. The
run aborts unless both binaries write byte-identical stdout, because a faster
answer that is a different answer is not the same command.
"""
from pathlib import Path
import argparse,hashlib,json,platform,random,statistics,subprocess,sysconfig,time

ap=argparse.ArgumentParser(description=__doc__)
for name in ['before','after','output']:ap.add_argument('--'+name,type=Path,required=True)
ap.add_argument('--verb',required=True)
ap.add_argument('--samples',type=int,default=21)
ap.add_argument('--files',nargs='+',default=['stat.py','ast.py','inspect.py','typing.py','_pydecimal.py'])
args=ap.parse_args()
if args.samples<1:ap.error('--samples must be positive')

bins={'before':args.before.resolve(),'after':args.after.resolve()}
report=dict(platform=platform.platform(),verb=args.verb,samples_per_binary=args.samples,
 mode='fresh process per sample, startup included, shuffled and interleaved; stdout required byte-identical between the two binaries',
 binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in bins.items()},cases=[])
for name in args.files:
 path=name if Path(name).is_absolute() else str(Path(sysconfig.get_path('stdlib'))/name)
 outputs={k:subprocess.run([str(p),args.verb,path],capture_output=True) for k,p in bins.items()}
 for k,r in outputs.items():assert r.returncode==0,(name,k,r.stderr.decode())
 assert outputs['before'].stdout==outputs['after'].stdout,name
 samples={k:[] for k in bins}
 order=list(bins)*args.samples;random.Random(67).shuffle(order)
 for k in order:
  start=time.perf_counter();result=subprocess.run([str(bins[k]),args.verb,path],capture_output=True)
  samples[k].append(time.perf_counter()-start)
  assert result.returncode==0 and result.stdout==outputs['before'].stdout,(name,k)
 median={k:statistics.median(v) for k,v in samples.items()}
 case=dict(file=Path(name).name,path=path,bytes=len(outputs['before'].stdout),lines=outputs['before'].stdout.count(b'\n'),
  output_sha256=hashlib.sha256(outputs['before'].stdout).hexdigest(),seconds=samples,median_seconds=median,
  ratio=median['after']/median['before'])
 report['cases'].append(case)
 print(f"{args.verb:8s} {name:22s} before {median['before']*1000:8.3f} ms  after {median['after']*1000:8.3f} ms  {case['ratio']:.2f}x",flush=True)
args.output.write_text(json.dumps(report,indent=2)+'\n')
