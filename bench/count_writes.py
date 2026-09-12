"""Count the write(2) calls a command makes to stdout, exactly.

Usage: python3 bench/count_writes.py --binary ./gramide --output docs/evidence/x.json \
           [--before ./gramide-before] [--samples-are-not-needed]

A `println` per line is a `write` per line: Rust's stdout is a LineWriter, so it
flushes at every newline whether or not stdout is a terminal. The count is
deterministic — it is a property of the program, not of the machine it ran on —
so it is the honest measure of an output change that timing can only corroborate.

The counter is a dyld interposer on `write`, in the shape of
bench/instrument_allocations.py: diagnostic only, and the measured binaries are
the uninstrumented ones.
"""
from pathlib import Path
import argparse,hashlib,json,os,platform,subprocess,sysconfig,tempfile

INTERPOSER='''#include <unistd.h>
#include <stdio.h>
static long writes = 0, bytes = 0;
ssize_t counted_write(int fd, const void *buf, size_t n) {
  if (fd == 1) { writes++; bytes += (long)n; }
  return write(fd, buf, n);
}
__attribute__((destructor)) static void report(void) {
  fprintf(stderr, "WRITES\\t%ld\\t%ld\\n", writes, bytes);
}
__attribute__((used)) static struct { const void *replacement; const void *replacee; }
interposers[] __attribute__((section("__DATA,__interpose"))) = {
  { (const void *)counted_write, (const void *)write } };
'''

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--binary',type=Path,required=True)
ap.add_argument('--before',type=Path)
ap.add_argument('--output',type=Path,required=True)
args=ap.parse_args()

cases=[('outline',name) for name in ['keyword.py','token.py','stat.py','copyreg.py','genericpath.py','reprlib.py','textwrap.py','inspect.py','tokenize.py','ast.py','dataclasses.py','typing.py','argparse.py','_pydecimal.py','pydoc_data/topics.py']]
cases+=[('tokens',name) for name in ['stat.py','ast.py','inspect.py','typing.py','_pydecimal.py']]

with tempfile.TemporaryDirectory() as tmp:
 source=Path(tmp)/'count_writes.c';source.write_text(INTERPOSER)
 library=Path(tmp)/'count_writes.dylib'
 subprocess.run(['cc','-dynamiclib','-O2','-o',str(library),str(source)],check=True,capture_output=True)
 def count(binary,verb,path):
  env=dict(os.environ,DYLD_INSERT_LIBRARIES=str(library))
  result=subprocess.run([str(binary.resolve()),verb,path],capture_output=True,env=env,text=True)
  assert result.returncode==0,(verb,path,result.stderr)
  row=[l for l in result.stderr.splitlines() if l.startswith('WRITES')]
  assert len(row)==1,result.stderr
  _,writes,written=row[0].split('\t')
  return dict(writes=int(writes),bytes=int(written),lines=result.stdout.count('\n'))
 binaries={'after':args.binary}|({'before':args.before} if args.before else {})
 report=dict(platform=platform.platform(),python=platform.python_version(),
  binary_sha256={label:hashlib.sha256(binary.read_bytes()).hexdigest() for label,binary in binaries.items()},
  mode='dyld interposer on write(2), fd 1 only; deterministic, not timing. The interposed run is a diagnostic run; the timed runs use the uninstrumented binary.',
  cases=[])
 for verb,name in cases:
  path=str(Path(sysconfig.get_path('stdlib'))/name)
  row=dict(verb=verb,file=name,**{label:count(binary,verb,path) for label,binary in binaries.items()})
  for label in binaries:
   assert row[label]['bytes']==row[next(iter(binaries))]['bytes'],row
  report['cases'].append(row)
  shown=' '.join(f"{label} {row[label]['writes']}" for label in binaries)
  print(f"{verb:8s} {name:22s} {row[next(iter(binaries))]['lines']:6d} lines   writes: {shown}",flush=True)
 args.output.write_text(json.dumps(report,indent=2)+'\n')
