"""Full-file outline timing with a CPython AST display oracle; startup included."""
from pathlib import Path
import argparse,hashlib,json,platform,random,statistics,subprocess,sysconfig,time

from python_outline_oracle import expected

ap=argparse.ArgumentParser(description=__doc__)
for name in ['gramide','before','tree-sitter','references','output']:ap.add_argument('--'+name,type=Path,required=True)
ap.add_argument("--samples", type=int, default=5)
args=ap.parse_args()
if args.samples < 1:ap.error("--samples must be positive")
bins={'gramide':args.gramide.resolve(),'before':args.before.resolve(),'tree_sitter':args.tree_sitter.resolve()}
report=dict(python=platform.python_version(),platform=platform.platform(),
 mode=f'fresh process, read + full parse + identical outline text; startup included, {args.samples} shuffled samples per binary, no incremental reuse or startup subtraction; uninstrumented binaries',
 samples_per_binary=args.samples,
 scope='15 Python 3.14 stdlib files, including three code-heavy issue #37 examples and a string-heavy control. This is not the reported 700-file Python 3.13 corpus or ctxgate-outline binary.',
 binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in bins.items()},
 source_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ['python_outline.py','python_outline_oracle.py','tree_sitter_python.c']},
 reference_commits={n:subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.references/n,text=True).strip() for n in ['tree-sitter','tree-sitter-python']},cases=[])
files=['keyword.py','token.py','stat.py','copyreg.py','genericpath.py','reprlib.py','textwrap.py','inspect.py','tokenize.py','ast.py','dataclasses.py','typing.py','argparse.py','_pydecimal.py','pydoc_data/topics.py']
for name in files:
 path=Path(sysconfig.get_path('stdlib'))/name
 source=path.read_text();want=expected(source).encode()
 def invoke(label):
  start=time.perf_counter()
  result=subprocess.run([str(bins[label]),'--outline' if label=='tree_sitter' else 'outline',str(path)],capture_output=True,timeout=20)
  elapsed=time.perf_counter()-start
  return result,elapsed
 case=dict(file=name,source_sha256=hashlib.sha256(source.encode()).hexdigest(),bytes=len(source.encode()),expected_sha256=hashlib.sha256(want).hexdigest(),correctness={})
 for label in bins:
  result,_=invoke(label)
  case['correctness'][label]='matches CPython' if result.returncode==0 and not result.stderr and result.stdout==want else dict(exit=result.returncode,stderr=result.stderr.decode(),actual=result.stdout.decode(),expected=want.decode())
 if all(v=='matches CPython' for v in case['correctness'].values()):
  samples={k:[] for k in bins};order=list(bins)*args.samples;random.Random(42).shuffle(order)
  for label in order:
   result,elapsed=invoke(label)
   assert result.returncode==0 and not result.stderr and result.stdout==want,(name,label)
   samples[label].append(elapsed)
  case.update(seconds=samples,median_seconds={k:statistics.median(v) for k,v in samples.items()})
 report['cases'].append(case)
 print(name,case.get('median_seconds',{k:'mismatch' if isinstance(v,dict) else v for k,v in case['correctness'].items()}),flush=True)
args.output.write_text(json.dumps(report,indent=2)+'\n')
