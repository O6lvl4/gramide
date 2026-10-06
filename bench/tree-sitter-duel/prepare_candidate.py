#!/usr/bin/env python3
"""Materialize benchmark-only path overlays, never mutate git dependency caches."""
from pathlib import Path
import json,shutil
ROOT=Path(__file__).resolve().parent
SOURCEROOT=ROOT/'sources'
SOURCES={
 'gramide-json':SOURCEROOT/'gramide-json',
 'gramide-typescript':SOURCEROOT/'gramide-typescript',
 'gramide-javascript':SOURCEROOT/'gramide-javascript',
 'gramide-java':SOURCEROOT/'gramide-java',
}
for name,source in SOURCES.items():
 dest=ROOT/'candidate-packages'/name;dest.mkdir(parents=True,exist_ok=True)
 shutil.copytree(source/'src',dest/'src',dirs_exist_ok=True)
 text=(source/'almide.toml').read_text()
 lines=[]
 for line in text.splitlines():
  if line.startswith('gramide = '):line='gramide = { path = '+json.dumps(str(SOURCEROOT/'gramide'))+' }'
  elif line.startswith('gramide_javascript = '):line='gramide_javascript = { path = '+json.dumps(str(ROOT/'candidate-packages/gramide-javascript'))+' }'
  lines.append(line)
 (dest/'almide.toml').write_text('\n'.join(lines)+'\n')
harness=ROOT/'gramide-harness-candidate';(harness/'src').mkdir(parents=True,exist_ok=True)
adapter=ROOT/'gramide-harness/src/main.almd.in'
if not adapter.exists():adapter=ROOT/'gramide-harness/src/main.almd'
shutil.copyfile(adapter,harness/'src/main.almd')
text=(ROOT/'gramide-harness/almide.toml').read_text()
lines=[]
for line in text.splitlines():
 if line.startswith('gramide = '):line='gramide = { path = '+json.dumps(str(SOURCEROOT/'gramide'))+' }'
 elif line.startswith('gramide_json = '):line='gramide_json = { path = '+json.dumps(str(ROOT/'candidate-packages/gramide-json'))+' }'
 elif line.startswith('gramide_java = '):line='gramide_java = { path = '+json.dumps(str(ROOT/'candidate-packages/gramide-java'))+' }'
 elif line.startswith('gramide_typescript = '):line='gramide_typescript = { path = '+json.dumps(str(ROOT/'candidate-packages/gramide-typescript'))+' }'
 lines.append(line)
(harness/'almide.toml').write_text('\n'.join(lines)+'\n')
(ROOT/'candidate-sources.json').write_text(json.dumps({'unchanged':{k:str(v) for k,v in SOURCES.items() if k not in ['gramide-java','gramide-json']},'changed':['gramide/src/incremental.almd','gramide-java/src/grammar.almd','gramide-java/src/table.almd','gramide-json/src/grammar.almd','gramide-json/src/table.almd']},indent=2)+'\n')
