#!/usr/bin/env python3
"""What reading a file costs in memory: the peak resident size of one
process, gramide against the tree-sitter harness each language package
builds (`bench/tree_sitter_ranges.c`), best of three, in megabytes.

Three ways to read a file:
  check    gramide `check` (a verdict, no tree) / the harness parsing it (`--check`)
  outline  gramide `outline` (the tree and its declarations) / the harness
           listing declarations from its tree (`--recover KINDS`)
  edit     the file parsed and kept, one letter typed into a long word, and
           read again: gramide's incremental document (`reparse-bench
           --edits 1`) / the harness's tree (`--edits 1`), the same edit,
           drawn by the same generator
and an empty file, which is what a process costs before it reads anything.

    python3 bench/memory.py --out docs/evidence/memory.json \
        LABEL:GRAMIDE_BINARY:HARNESS:TS_KINDS:FILE ...

Writes the JSON the README cites; prints a table.
"""
import json, os, platform, re, subprocess, sys, tempfile

def arg(name, default=None):
    if name in sys.argv:
        i = sys.argv.index(name); v = sys.argv[i + 1]; del sys.argv[i:i + 2]; return v
    return default

out = arg("--out")
specs = sys.argv[1:]

def peak_mb(cmd):
    best = None
    for _ in range(3):
        p = subprocess.run(["/usr/bin/time", "-l"] + cmd, capture_output=True, text=True)
        m = re.search(r"(\d+)\s+maximum resident set size", p.stderr)
        if not m: raise SystemExit("no peak for " + " ".join(cmd) + ": " + p.stderr[-300:])
        v = int(m.group(1)) / 1e6
        best = v if best is None else min(best, v)
    return round(best, 1)

rows = []
with tempfile.TemporaryDirectory() as tmp:
    for spec in specs:
        label, gramide, harness, kinds, path = spec.split(":", 4)
        data = open(path, "rb").read()
        empty = os.path.join(tmp, "empty" + os.path.splitext(path)[1])
        open(empty, "wb").write(b"")
        row = {"label": label, "file": os.path.basename(path), "bytes": len(data),
               "empty": {"gramide": peak_mb([gramide, "outline", empty]), "tree_sitter": peak_mb([harness, "--check", empty])},
               "check": {"gramide": peak_mb([gramide, "check", path]), "tree_sitter": peak_mb([harness, "--check", path])},
               "outline": {"gramide": peak_mb([gramide, "outline", path]), "tree_sitter": peak_mb([harness, "--recover", kinds, path])},
               "edit": {"gramide": peak_mb([gramide, "reparse-bench", path, "--edits", "1", "--seed", "1", "--verify", "0"]),
                        "tree_sitter": peak_mb([harness, "--edits", "1", "--seed", "1", path])}}
        rows.append(row)
        print(f"{label:30} {row['bytes']:>9,} B" + "".join(f"  {k} {row[k]['gramide']:6.1f}/{row[k]['tree_sitter']:6.1f}" for k in ("empty", "check", "outline", "edit")), flush=True)

report = {"platform": platform.platform(), "unit": "MB, peak resident, best of three", "files": rows}
if out:
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    open(out, "w").write(json.dumps(report, indent=2) + "\n")
