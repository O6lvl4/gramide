"""Parse rate over a whole corpus, with process startup measured and subtracted.

Usage: python3 bench/corpus_parse_rate.py --gramide ./gramide --tree-sitter <binary> \
           --output docs/evidence/x.json [--passes 5]

This is issue #37's method, kept so its number can be checked against the one it
reported: one process a file, which is how a caller with a file list runs it;
then the same number of runs on a one-line file, which is startup and nothing
else; the difference is the parsing. Both binaries are measured the same way and
their outputs are required to agree with CPython before any timing is kept.
"""
from pathlib import Path
import argparse,hashlib,json,platform,random,statistics,subprocess,sysconfig,tempfile,time

from python_outline_oracle import expected

ap=argparse.ArgumentParser(description=__doc__)
for name in ['gramide','tree-sitter','output']:ap.add_argument('--'+name,type=Path,required=True)
ap.add_argument('--passes',type=int,default=5)
args=ap.parse_args()

root=Path(sysconfig.get_path('stdlib'))
excluded={'test','tests','lib2to3','site-packages','__pycache__'}
files=[p for p in sorted(root.rglob('*.py')) if not (set(p.relative_to(root).parts)&excluded)]
total=sum(p.stat().st_size for p in files)
bins={'gramide':args.gramide.resolve(),'tree_sitter':args.tree_sitter.resolve()}
def command(label,path):return [str(bins[label]),'--outline' if label=='tree_sitter' else 'outline',str(path)]

with tempfile.TemporaryDirectory() as tmp:
    tiny=Path(tmp)/'tiny.py';tiny.write_text('x = 1\n')
    # a file every binary must already agree with CPython on, before any clock runs
    check=root/'inspect.py';want=expected(check.read_text()).encode()
    for label in bins:
        got=subprocess.run(command(label,check),capture_output=True)
        assert got.returncode==0 and got.stdout==want,(label,'does not match CPython on inspect.py')
    def sweep(label,paths):
        start=time.perf_counter()
        for p in paths:subprocess.run(command(label,p),capture_output=True)
        return time.perf_counter()-start
    for label in bins:sweep(label,files[:40]);sweep(label,[tiny]*40)
    runs={(l,w):[] for l in bins for w in ('corpus','startup')}
    order=[(l,w) for l in bins for w in ('corpus','startup')]*args.passes
    random.Random(211).shuffle(order)
    for label,what in order:
        runs[(label,what)].append(sweep(label,files if what=='corpus' else [tiny]*len(files)))

report=dict(platform=platform.platform(),
 binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in bins.items()},
 mode=f"issue #37's method: one process a file, {args.passes} interleaved passes, medians; the same count of runs on a one-line file is startup and is subtracted",
 files=len(files),bytes=total,cases={})
for label in bins:
    corpus=statistics.median(runs[(label,'corpus')]);startup=statistics.median(runs[(label,'startup')])
    report['cases'][label]=dict(corpus_seconds=corpus,startup_seconds=startup,
                                parse_seconds=corpus-startup,megabytes_per_second=total/(corpus-startup)/1e6)
g,t=report['cases']['gramide'],report['cases']['tree_sitter']
report['parse_ratio']=g['parse_seconds']/t['parse_seconds']
report['corpus_ratio']=g['corpus_seconds']/t['corpus_seconds']
args.output.write_text(json.dumps(report,indent=2)+'\n')
print(f"{len(files)} files, {total:,} bytes")
for label in bins:
    c=report['cases'][label]
    print(f"  {label:12s} corpus {c['corpus_seconds']:6.2f} s  startup {c['startup_seconds']:6.2f} s  "
          f"parse {c['parse_seconds']:6.2f} s  {c['megabytes_per_second']:6.2f} MB/s")
print(f"parse {report['parse_ratio']:.2f}x, whole run {report['corpus_ratio']:.2f}x")
