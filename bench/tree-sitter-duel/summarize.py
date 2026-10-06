#!/usr/bin/env python3
"""Render every frozen case, including failures; no timing sample is dropped."""
from pathlib import Path
import gzip,json,statistics,math
ROOT=Path(__file__).resolve().parent
def load(name):
 p=ROOT/'evidence'/name
 return json.loads(p.read_text() if p.exists() else gzip.decompress(Path(str(p)+'.gz').read_bytes()))
def ratio(row,key):return row[key]['tree_sitter']['median_ns']/row[key]['gramide']['median_ns']
def yes(v):return 'yes' if v else 'no'
d=load('final-duel.json');e=load('final-edits.json')
out=['# Recorded comparison: 2026-10-05','',
'This is a correctness-gated workload result, not a claim of complete language or tree parity. All selected real files remain in the denominator. The next optimization target is the structural/recovery, cold-process and memory losses shown below.','',
'Final timing ran serially on CPU 0, AMD EPYC 9V74, Linux x86-64, 2026-10-05 15:27–15:29 UTC. No concurrent model/compiler jobs. The reference is official Tree-sitter v0.27.0 with the exact grammars in `references.lock.json`. Candidate source pins are in `source-pins.json`; all raw samples and original build provenance are in `evidence/*.json.gz`.','',
'## Quality gates','',
'- 70 frozen files: 25 real, 3 generated scaling, 29 coverage probes, 13 malformed. One optional TSX probe is explicitly untested by the TypeScript-only adapter','- All 25 real files are accepted by both engines and exactly match the selected declaration names, kinds, UTF-8 ranges and derived line ranges','- Across all categories: 45 parse-eligible and 44 exact-symbol-equal cases. The matrix below retains unsupported, invalid, unknown-oracle and mismatch cases','- Java remains a core reader, not complete javac validation. A Java 25 probe lacks an appropriate independent oracle on this Java 21 host','- The separate 32-case strict JSON gate matches the Python oracle for Gramide. Official Tree-sitter JSON accepts 13 oracle-invalid inputs by design; it would need extra strict-validation checks. These are not timed as competitive successes','- Every incremental step is checked against a fresh parse from that engine, including positions. The edit harness additionally checks Gramide node IDs; separate regression tests assert fallback immutability. Valid streams must remain strict-valid at every step. Recovery trees across engines are not asserted equivalent','',
'## Real-file aggregate','',
'Ratios are Tree-sitter median / Gramide median; greater than 1 favors Gramide. Aggregates are geometric means of per-file ratios, not throughput weighted by file size. Warm: 5 process batches × 31 full-tree iterations after warmup. Cold: 11 balanced randomized paired fresh-process samples with warm filesystem cache.','',
'| Task | Language | Geomean ratio | Gramide wins | Per-file range |','|---|---|---:|---:|---:|']
for key,label in [('warm_full_parse','Warm full parse'),('cold_full_parse','Cold process full parse'),('cold_selected_symbols','Cold selected symbols')]:
 for lang in ['json','typescript','java']:
  fs=[f for f in d['files'] if f['category']=='real' and f['language']==lang]
  rs=[ratio(f,key) for f in fs]
  out.append(f'| {label} | {lang} | {statistics.geometric_mean(rs):.3f}× | {sum(x>1 for x in rs)}/{len(rs)} | {min(rs):.3f}–{max(rs):.3f}× |')
out+=['','Warm full parse wins on all 25 selected real files. Cold results are mixed. These adapters construct different full-tree representations; equal selected-symbol output does not prove full AST/CST equivalence. Gramide source/path copying remains inside its full-parse timer. Declaration serialization uses the same schema but different implementations.','',
'## Incremental update kernel','',
'Fixed development-file streams only, not a held-out editing study. Token-preserving edits modify long ASCII words in identifiers/strings/comments. The timer includes tree update, reparse, fallback and disposal, but excludes source application, point calculation and output materialization on both sides. Five replay runs per eligible stream.','',
'| Language | Stream | Gramide median µs | Tree-sitter median µs | TS/G ratio | Gate |','|---|---|---:|---:|---:|---|']
for f in e['files']:
 if f['eligible']:
  a=f['timing']['gramide']['median_ns'];b=f['timing']['tree_sitter']['median_ns']
  out.append(f"| {f['language']} | {f['category']} | {a/1000:.3f} | {b/1000:.3f} | {b/a:.4f}× | pass |")
 else:out.append(f"| {f['language']} | {f['category']} | — | — | — | Gramide recovery unsupported; no speed claim |")
out+=['','Structural edits and malformed intermediates remain substantial losses, and one JSON recovery stream fails. Token-preserving wins cannot stand in for all editor operations.','',
'## Every real file: timing and memory','',
'Peak RSS uses three separate native fork/exec/wait4 runs per engine; below are median peaks in MiB. The launcher `/bin/true` control was 0.375 MiB. This measures whole processes, not parser-owned allocation. The earlier Python-launcher RSS experiment had an inherited floor and is not used. Memory generally favors Tree-sitter. Incremental RSS was not measured.','',
'| File | Split | Warm TS/G | Cold TS/G | Symbols TS/G | RSS G MiB | RSS TS MiB |','|---|---|---:|---:|---:|---:|---:|']
for f in d['files']:
 if f['category']!='real':continue
 mem={t:statistics.median(v['peak_rss_bytes'] for v in vs)/1048576 for t,vs in f['memory'].items()}
 out.append(f"| {f['id']} | {f['split']} | {ratio(f,'warm_full_parse'):.3f}× | {ratio(f,'cold_full_parse'):.3f}× | {ratio(f,'cold_selected_symbols'):.3f}× | {mem['gramide']:.3f} | {mem['tree_sitter']:.3f} |")
out+=['','## Complete acceptance matrix','',
'Expected source intent is separate from observed independent oracle validity. Acceptance alone is not a conformance claim. Parse eligibility requires both engines and the oracle to accept.','',
'| Input | Category | Oracle valid | Gramide accepts | Tree-sitter accepts | Parse eligible | Symbols equal |','|---|---|---|---|---|---|---|']
for f in d['files']:
 if 'not_tested_grammar_variant' in f:out.append(f"| {f['id']} | {f['category']} | untested TSX | — | — | no | — |");continue
 out.append(f"| {f['id']} | {f['category']} | {f['oracle']['valid']} | {yes(f['accepted']['gramide'])} | {yes(f['accepted']['tree_sitter'])} | {yes(f['competitive_parse_eligible'])} | {f.get('symbols_match','—')} |")
out+=['','## Reproduction and scope','',
'Follow [README.md](README.md) and [PROTOCOL.md](PROTOCOL.md). Corpus provenance, selection made before parser runs, development/held-out split, source hashes and licenses are retained. This is a small purposive sample, not a random ecosystem study. Java real inputs are from Gson; TypeScript inputs are from TypeScript; JSON includes parser metadata.','',
'The original unmodified core/grammar baseline is pinned in `gramide-harness/almide.lock` and can be rebuilt with the same adapter. Earlier diagnostic timings are deliberately not used as optimized-vs-original speedup evidence. Final results compare the correctness-fixed candidate with the unchanged official Tree-sitter reference.','',
'Native compiler version, compiler/binary hashes, generated Cargo profile and source hashes are recorded. The measured Almide 0.62.0 binary uses generated Cargo release opt-level 3, LTO and one codegen unit; C uses -O3 -flto=1 -DNDEBUG. The nearby compiler checkout commit is metadata, not proof of the binary source identity. Host-specific paths inside raw build records describe the original run, not required reproduction paths.']
(ROOT/'REPORT.md').write_text('\n'.join(out)+'\n')
print('Rendered REPORT.md from all raw final records')
