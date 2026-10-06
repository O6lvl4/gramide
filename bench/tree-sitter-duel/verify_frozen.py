#!/usr/bin/env python3
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=ROOT/'corpus/manifest.json'
assert sha(m)=='e4911aa80bd8e4bd1755d1763eea9fb7b1ee81b8351ab1f98ffb86b64881eccd'
for f in json.loads(m.read_text())['files']:
 assert sha(ROOT/'corpus'/f['path'])==f['sha256'],f['id']
 for p in f['license_paths']:assert (ROOT/'corpus'/p).is_file(),p
for f in json.loads((ROOT/'edits/manifest.json').read_text())['files']:
 assert sha(ROOT/'edits'/f['script'])==f['script_sha256'],f['script']
 assert sha(ROOT/'corpus'/f['source_path'])==f['source_sha256'],f['source_path']
print('70 frozen inputs, licenses, and nine edit streams verified')
