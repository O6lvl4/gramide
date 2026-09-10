"""Full-file Python ranges: CPython correctness oracle and time/RSS evidence."""
from pathlib import Path
import argparse,hashlib,json,platform,random,re,statistics,subprocess,sys,sysconfig,tempfile,time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ci'))
from python_symbols import expected
ap=argparse.ArgumentParser()
ap.add_argument('--gramide',type=Path,required=True)
ap.add_argument('--tree-sitter',type=Path,required=True)
ap.add_argument('--before',type=Path,help='optional previous gramide binary for paired comparison')
ap.add_argument('--references',type=Path,required=True)
ap.add_argument('--output',type=Path,required=True)
ap.add_argument('--samples',type=int,default=5)
args=ap.parse_args()
assert args.samples>0
bins={'gramide':args.gramide.resolve(),'tree_sitter':args.tree_sitter.resolve()}
if args.before:bins['gramide_before']=args.before.resolve()
report=dict(platform=platform.platform(),python=platform.python_version(),
 mode='fresh process, file read + full parse + JSON declaration ranges; startup included; no incremental reuse',
 scope='generated functions and complete stdlib files; CPython AST ranges independently required before performance comparison; no general ranking',
 asymmetry='gramide also outputs its normal document metadata and syntax_kind; the C baseline outputs only the compared declaration fields',
 binary_sha256={k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in bins.items()},
 reference_commits={name:subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.references/name,text=True).strip() for name in ['tree-sitter','tree-sitter-python']},cases=[])

def invoke(label,path,memory=False):
 command=[str(bins[label])]+(['symbols'] if label!='tree_sitter' else [])+[str(path)]
 if memory:command=['/usr/bin/time','-l' if sys.platform=='darwin' else '-v']+command
 start=time.perf_counter()
 try:result=subprocess.run(command,capture_output=True,text=True,timeout=30)
 except subprocess.TimeoutExpired:return dict(error='timeout after 30s')
 elapsed=time.perf_counter()-start
 if result.returncode:return dict(error=f'exit {result.returncode}',stderr=result.stderr[:1200])
 payload=json.loads(result.stdout)
 rows=payload['symbols'] if label!='tree_sitter' else payload
 rows=[{k:s[k] for k in ['name','kind','owner','start','end','start_byte','end_byte']} for s in rows]
 answer=dict(seconds=elapsed,rows=rows)
 if memory:
  pattern=r'(\d+)\s+maximum resident set size' if sys.platform=='darwin' else r'Maximum resident set size \(kbytes\):\s*(\d+)'
  match=re.search(pattern,result.stderr)
  if match:answer['peak_rss_bytes']=int(match[1])*(1 if sys.platform=='darwin' else 1024)
  else:answer['memory_error']=result.stderr[:1200]
 return answer

def compare(rows,want,source):
 # Ignore only the optional final semicolon included in a grammar suite span.
 raw=source.encode();fixed=[]
 for a,b in zip(rows,want):
  a=dict(a)
  if a['end_byte']!=b['end_byte'] and raw[b['end_byte']:a['end_byte']].strip()==b';':a['end_byte']=b['end_byte']
  fixed.append(a)
 if len(rows)==len(want) and fixed==want:return None
 return dict(actual_count=len(rows),expected_count=len(want),first_differences=[dict(actual=a,expected=b) for a,b in zip(fixed,want) if a!=b][:3])

with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);paths=[]
 for count in [100,400,800]:
  p=root/f'generated_{count}.py';p.write_text(''.join(f'def f{i}(x: int) -> int:\n    return x + {i}\n\n' for i in range(count)));paths.append(p)
 stdlib=Path(sysconfig.get_path('stdlib'))
 paths += [stdlib/name for name in ['keyword.py','token.py','stat.py','copyreg.py','genericpath.py','reprlib.py','textwrap.py','inspect.py','tokenize.py','ast.py','dataclasses.py','typing.py']]
 for path in paths:
  source=path.read_text();want=expected(source)
  case=dict(file=path.name,bytes=len(source.encode()),source_sha256=hashlib.sha256(source.encode()).hexdigest(),declarations=len(want),correctness={})
  for label in bins:
   result=invoke(label,path)
   case['correctness'][label]=result if 'error' in result else compare(result['rows'],want,source) or 'matches CPython'
  if all(v=='matches CPython' for v in case['correctness'].values()):
   samples={k:[] for k in bins};rss={k:[] for k in bins}
   order=list(bins)*args.samples;random.Random(42).shuffle(order)
   for label in order:
    result=invoke(label,path)
    assert 'error' not in result and compare(result['rows'],want,source) is None,(path,label,result)
    samples[label].append(result['seconds'])
   for label in bins:
    for _ in range(2):
     result=invoke(label,path,memory=True)
     assert 'error' not in result and compare(result['rows'],want,source) is None,(path,label,result)
     assert 'peak_rss_bytes' in result,(path,label,result.get('memory_error'))
     rss[label].append(result['peak_rss_bytes'])
   case.update(seconds=samples,median_seconds={k:statistics.median(v) for k,v in samples.items()},peak_rss_bytes=rss)
  report['cases'].append(case)
  args.output.write_text(json.dumps(report,indent=2)+'\n')
  print({k:v for k,v in case.items() if k not in ['seconds','peak_rss_bytes']},flush=True)
