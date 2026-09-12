"""Calibrate the diagnostic allocator with a known, optimizer-visible request."""
from pathlib import Path
import subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as tmp:
 root=Path(tmp);source=root/'input.rs';profile=root/'profile.rs';binary=root/'profile'
 source.write_text('''fn sample() {
    let value = std::hint::black_box(vec![0u8; 64]);
    std::hint::black_box(value);
}
fn main() {
    sample();
}
''')
 subprocess.run([sys.executable,str(ROOT/'bench/instrument_allocations.py'),str(source),str(profile)],check=True,capture_output=True)
 subprocess.run(['rustc',str(profile),'--edition=2021','-C','opt-level=3','-o',str(binary)],check=True,capture_output=True)
 result=subprocess.run([str(binary)],check=True,capture_output=True,text=True)
 assert not result.stdout,result
 rows={line.split('\t')[1]:line.split('\t')[2:] for line in result.stderr.splitlines()}
 assert rows['sample']==['1','0','64'],rows
print('Allocation profiler: one 64-byte request is attributed to sample exactly once')
