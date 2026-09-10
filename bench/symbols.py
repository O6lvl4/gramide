"""Compare full-file structured reads; no incremental parsing or startup subtraction."""
from pathlib import Path
import argparse, hashlib, json, platform, random, statistics, subprocess, tempfile, time
ap = argparse.ArgumentParser()
ap.add_argument('--gramide', type=Path, required=True)
ap.add_argument('--before', type=Path, required=True)
ap.add_argument('--tree-sitter', type=Path, required=True)
ap.add_argument('--tree-sitter-source', type=Path, required=True)
ap.add_argument('--go-grammar-source', type=Path, required=True)
ap.add_argument('--output', type=Path, required=True)
args = ap.parse_args()
binaries = {k: p.resolve() for k,p in [('before',args.before),('after',args.gramide),('tree_sitter',args.tree_sitter)]}
report = {'platform':platform.platform(),'python':platform.python_version(),
          'mode':'fresh process, read + full parse + JSON ranges; no old tree; wall time includes startup',
          'scope':'generated Go top-level functions only; not general language coverage or incremental performance',
          'binary_sha256':{k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in binaries.items()},
          'reference_commits':{k:subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip() for k,p in [('tree_sitter',args.tree_sitter_source),('tree_sitter_go',args.go_grammar_source)]},'cases':[]}
def invoke(label,path):
    command=[str(binaries[label])]+([] if label=='tree_sitter' else ['symbols'])+[str(path)]
    start=time.perf_counter()
    result=subprocess.run(command,capture_output=True,check=True,timeout=30)
    return time.perf_counter()-start,json.loads(result.stdout)
def normalize(label,payload):
    rows=payload if label=='tree_sitter' else payload['symbols']
    return [{k:r[k] for k in ['name','start','end','start_byte','end_byte']} for r in rows]
with tempfile.TemporaryDirectory() as tmp:
    for count in [100,400,800]:
        source='package sample\n'+''.join('func F%d(x int) int { return x + %d }\n'%(i,i) for i in range(count))
        path=Path(tmp)/'sample.go';path.write_text(source)
        expected=None
        for label in binaries:
            _,payload=invoke(label,path)
            rows=normalize(label,payload)
            if expected is None:expected=rows
            assert rows==expected,(count,label)
        samples={label:[] for label in binaries}
        order=list(binaries)*3;random.Random(42).shuffle(order)
        for label in order:
            elapsed,payload=invoke(label,path)
            assert normalize(label,payload)==expected
            samples[label].append(elapsed)
        row={'functions':count,'bytes':len(source.encode()),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
             'seconds':samples,'median_seconds':{k:statistics.median(v) for k,v in samples.items()},'ranges_identical':True}
        report['cases'].append(row)
        print({k:v for k,v in row.items() if k!='seconds'},flush=True)
args.output.write_text(json.dumps(report,indent=2)+'\n')
