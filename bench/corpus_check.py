"""How long `check` takes over a whole corpus, the way a caller would run it.

Usage: python3 bench/corpus_check.py --binary ./gramide --root <dir> --ext .go \
           [--output docs/evidence/x.json] [--exclude .git .claude target]

One process per two thousand files, which is what the kernel's argument limit
allows and what `gramide check src/*.go` already is: the grammar is read once
and the files stream past it. This is not one process per file — that measures
process startup, which `bench/startup_floor.py` measures on purpose instead.
"""
from pathlib import Path
import argparse,hashlib,json,platform,statistics,subprocess,time

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--binary',type=Path,required=True)
ap.add_argument('--root',type=Path,required=True)
ap.add_argument('--ext',required=True)
ap.add_argument('--exclude',nargs='*',default=['.git','.claude','target','worktrees'])
ap.add_argument('--passes',type=int,default=5)
ap.add_argument('--output',type=Path)
args=ap.parse_args()

excluded=set(args.exclude)
files=[p for p in sorted(args.root.rglob('*'+args.ext)) if not (set(p.relative_to(args.root).parts) & excluded)]
assert files,'no files matched'
paths=[str(p) for p in files]
total=sum(p.stat().st_size for p in files)
CHUNK=2000

def pass_over():
    start=time.perf_counter()
    rejected=0
    for i in range(0,len(paths),CHUNK):
        result=subprocess.run([str(args.binary.resolve()),'check']+paths[i:i+CHUNK],capture_output=True)
        rejected+=len([l for l in result.stderr.decode(errors='replace').splitlines() if l.strip()])
    return time.perf_counter()-start,rejected

pass_over()
runs=[pass_over() for _ in range(args.passes)]
seconds=statistics.median(s for s,_ in runs)
rejected=runs[-1][1]
biggest=max(files,key=lambda p:p.stat().st_size)
one=[]
for _ in range(11):
    start=time.perf_counter();subprocess.run([str(args.binary.resolve()),'check',str(biggest)],capture_output=True)
    one.append(time.perf_counter()-start)
lines=sum(1 for _ in open(biggest,errors='replace'))
report=dict(platform=platform.platform(),
 binary_sha256=hashlib.sha256(args.binary.read_bytes()).hexdigest(),
 mode=f'`check` over a whole corpus, {CHUNK} files to a process, median of {args.passes} passes; startup is paid once a chunk, not once a file',
 root=str(args.root),ext=args.ext,excluded=sorted(excluded),
 files=len(files),bytes=total,processes=(len(files)+CHUNK-1)//CHUNK,
 seconds=seconds,megabytes_per_second=total/seconds/1e6,rejected_lines=rejected,
 largest=dict(path=str(biggest.relative_to(args.root)),lines=lines,bytes=biggest.stat().st_size,
              milliseconds=statistics.median(one)*1000))
if args.output:args.output.write_text(json.dumps(report,indent=2)+'\n')
print(f"{len(files)} files, {total:,} bytes, {report['processes']} process(es): "
      f"{seconds:.3f} s, {report['megabytes_per_second']:.1f} MB/s, {rejected} rejected")
print(f"largest: {report['largest']['path']}, {lines:,} lines: {report['largest']['milliseconds']:.0f} ms")
