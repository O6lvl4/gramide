"""Instrument generated native Rust with exclusive generated-function allocation counts.

Usage: python3 bench/instrument_allocations.py generated.rs instrumented.rs
Compile the output with the same almide_rt and Rust release flags as the input.
The profile binary writes normal stdout and ALLOC records to stderr on exit.
Counts include runtime calls in the innermost generated function, not a sampled
stack or exact source call site; they are not timing, live heap or peak RSS.
"""
from pathlib import Path
import re,sys

source=Path(sys.argv[1]).read_text()
pattern=re.compile(r'^(?:pub )?fn (\w+)[^\n]*\{\n',re.M)
names=['outside_generated_functions']+[m.group(1) for m in pattern.finditer(source)]
assert names.count('main')==1
index=0

def insert(match):
 global index
 index+=1
 extra='    let _allocation_report = AllocationReport;\n' if match.group(1)=='main' else ''
 return match.group(0)+extra+f'    let _allocation_scope = AllocationScope::enter({index});\n'

source=pattern.sub(insert,source)
source+='''
// Diagnostic-only allocator instrumentation. TLS/counter operations allocate no
// memory; reporting runs after the main scope is dropped and uses a snapshot.
use std::alloc::{GlobalAlloc, Layout, System};
use std::sync::atomic::{AtomicU64, Ordering};
thread_local! { static ALLOCATION_SCOPE: std::cell::Cell<usize> = const { std::cell::Cell::new(0) }; }
static ALLOCATION_CALLS: [AtomicU64; PROFILE_SIZE] = [const { AtomicU64::new(0) }; PROFILE_SIZE];
static REALLOCATION_CALLS: [AtomicU64; PROFILE_SIZE] = [const { AtomicU64::new(0) }; PROFILE_SIZE];
static ALLOCATION_BYTES: [AtomicU64; PROFILE_SIZE] = [const { AtomicU64::new(0) }; PROFILE_SIZE];
struct AllocationCounter;
#[global_allocator] static ALLOCATION_COUNTER: AllocationCounter = AllocationCounter;
fn record_allocation(size: usize, realloc: bool) {
 let _ = ALLOCATION_SCOPE.try_with(|scope| {
  let i=scope.get();
  if realloc { REALLOCATION_CALLS[i].fetch_add(1,Ordering::Relaxed); }
  else { ALLOCATION_CALLS[i].fetch_add(1,Ordering::Relaxed); }
  ALLOCATION_BYTES[i].fetch_add(size as u64,Ordering::Relaxed);
 });
}
unsafe impl GlobalAlloc for AllocationCounter {
 unsafe fn alloc(&self, layout: Layout) -> *mut u8 { record_allocation(layout.size(),false); System.alloc(layout) }
 unsafe fn alloc_zeroed(&self, layout: Layout) -> *mut u8 { record_allocation(layout.size(),false); System.alloc_zeroed(layout) }
 unsafe fn realloc(&self, ptr:*mut u8, layout:Layout, size:usize) -> *mut u8 { record_allocation(size,true); System.realloc(ptr,layout,size) }
 unsafe fn dealloc(&self, ptr:*mut u8, layout:Layout) { System.dealloc(ptr,layout) }
}
struct AllocationScope(usize);
impl AllocationScope {
 fn enter(index:usize)->Self { Self(ALLOCATION_SCOPE.with(|scope|scope.replace(index))) }
}
impl Drop for AllocationScope {
 fn drop(&mut self) { ALLOCATION_SCOPE.with(|scope|scope.set(self.0)); }
}
struct AllocationReport;
impl Drop for AllocationReport {
 fn drop(&mut self) {
  let mut rows=[(0u64,0u64,0u64);PROFILE_SIZE];
  for i in 0..PROFILE_SIZE { rows[i]=(ALLOCATION_CALLS[i].load(Ordering::Relaxed),REALLOCATION_CALLS[i].load(Ordering::Relaxed),ALLOCATION_BYTES[i].load(Ordering::Relaxed)); }
  for (i,(a,r,b)) in rows.into_iter().enumerate() {
   if a+r>0 { eprintln!("ALLOC\\t{}\\t{}\\t{}\\t{}",PROFILE_NAMES[i],a,r,b); }
  }
 }
}
'''
source+=f'const PROFILE_SIZE: usize = {len(names)};\n'
source+='static PROFILE_NAMES: [&str; PROFILE_SIZE] = ['+','.join('"'+n+'"' for n in names)+'];\n'
Path(sys.argv[2]).write_text(source)
print(f'Instrumented {index} generated functions')
