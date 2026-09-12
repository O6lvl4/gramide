"""What a run costs before the parser sees a byte: the process floor, by language.

Usage: python3 bench/startup_floor.py --gramide ./gramide --tree-sitter <binary> \
           --almide almide --output docs/evidence/startup-floor.json [--samples 151]

The seven smallest files in the outline benchmark lose to tree-sitter by less
than half a millisecond, and none of it is parsing. This measures what each
binary costs before its own work starts, by building controls that differ in one
thing at a time: a C binary, the same binary padded to Rust's size, a Rust binary
that writes with write(2) and never touches std's formatting or stdout, a Rust
binary that calls println!, and an Almide binary that calls println. The minimum
of many runs is reported, not the median: the floor is what a startup cost is.
"""
from pathlib import Path
import argparse,hashlib,json,platform,random,statistics,subprocess,tempfile,time

ap=argparse.ArgumentParser(description=__doc__)
for name in ['gramide','tree-sitter','output']:ap.add_argument('--'+name,type=Path,required=True)
ap.add_argument('--almide',default='almide')
ap.add_argument('--samples',type=int,default=151)
args=ap.parse_args()
if args.samples<3:ap.error('--samples must be at least 3')

C_HELLO='#include <stdio.h>\nint main(void){puts("hi");return 0;}\n'
C_PADDED='#include <stdio.h>\nconst char pad[400000]={1};\nint main(void){puts("hi");return pad[0];}\n'
RUST_WRITE='''#![no_main]
extern "C" { fn write(fd: i32, buf: *const u8, n: usize) -> isize; }
#[no_mangle]
pub extern "C" fn main(_argc: i32, _argv: *const *const u8) -> i32 {
    unsafe { write(1, b"hi\\n".as_ptr(), 3); }
    0
}
'''
RUST_PRINTLN='fn main(){println!("hi");}\n'
ALMIDE_PRINTLN='fn main() -> Unit = println("hi")\n'

with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp)
 (root/'tiny.py').write_text('x = 1\n')
 def rustc(name,source):
  path=root/(name+'.rs');path.write_text(source)
  subprocess.run(['rustc','-O','-o',str(root/name),str(path)],check=True,capture_output=True)
  return root/name
 def cc(name,source):
  path=root/(name+'.c');path.write_text(source)
  subprocess.run(['cc','-O2','-o',str(root/name),str(path)],check=True,capture_output=True)
  return root/name
 project=root/'almide_hello';(project/'src').mkdir(parents=True)
 (project/'almide.toml').write_text('[package]\nname = "almide_hello"\nversion = "0.1.0"\n')
 (project/'src'/'main.almd').write_text(ALMIDE_PRINTLN)
 subprocess.run([args.almide,'build','--release'],cwd=project,check=True,capture_output=True)

 tiny=str(root/'tiny.py')
 cases={
  'true':(['/usr/bin/true'],'the cost of starting any process at all'),
  'c_hello':([str(cc('c_hello',C_HELLO))],'C, 33 KB, one puts'),
  'c_padded':([str(cc('c_padded',C_PADDED))],'the same C binary padded past 400 KB: mach-o size is not a startup cost'),
  'rust_write':([str(rustc('rust_write',RUST_WRITE))],'Rust with no std::rt::init and no std formatting or stdout: write(2) only'),
  'rust_println':([str(rustc('rust_println',RUST_PRINTLN))],'Rust, ordinary main, one println!'),
  'almide_println':([str(project/'almide_hello')],'Almide, one println: what every Almide binary pays'),
  'gramide_noargs':([str(args.gramide.resolve())],'gramide with no arguments: it prints usage and exits'),
  'gramide_tiny':([str(args.gramide.resolve()),'outline',tiny],'gramide reading a one-line file'),
  'tree_sitter_tiny':([str(args.tree_sitter.resolve()),'--outline',tiny],'tree-sitter reading the same one-line file'),
 }
 for command,_ in cases.values():
  for _ in range(5):subprocess.run(command,capture_output=True)
 samples={name:[] for name in cases}
 order=list(cases)*args.samples;random.Random(101).shuffle(order)
 for name in order:
  start=time.perf_counter();subprocess.run(cases[name][0],capture_output=True)
  samples[name].append(time.perf_counter()-start)
 floor=min(samples['true'])
 report=dict(platform=platform.platform(),samples_per_binary=args.samples,
  almide=subprocess.run([args.almide,'--version'],capture_output=True,text=True).stdout.strip(),
  rustc=subprocess.run(['rustc','--version'],capture_output=True,text=True).stdout.strip(),
  binary_sha256={name:hashlib.sha256(Path(command[0]).read_bytes()).hexdigest() for name,(command,_) in cases.items()},
  mode='fresh process per sample, shuffled; the minimum is reported because a floor is what a startup cost is, and the median only adds this machine\'s load',
  bytes={name:Path(command[0]).stat().st_size for name,(command,_) in cases.items()},
  cases={name:dict(what=what,command=[Path(command[0]).name]+command[1:],
   min_ms=min(samples[name])*1000,median_ms=statistics.median(samples[name])*1000,
   over_true_ms=(min(samples[name])-floor)*1000) for name,(command,what) in cases.items()})
 args.output.write_text(json.dumps(report,indent=2)+'\n')
 for name in cases:
  row=report['cases'][name]
  print(f"{name:18s} {row['min_ms']:7.3f} ms   over true {row['over_true_ms']:+7.3f}   {row['what']}")
