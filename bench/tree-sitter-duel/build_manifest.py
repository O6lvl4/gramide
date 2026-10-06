#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,subprocess,os,time,shutil
ROOT=Path(__file__).resolve().parent
ap=argparse.ArgumentParser();ap.add_argument('--binary',type=Path,required=True);ap.add_argument('--candidate',action='store_true');args=ap.parse_args()
cache=Path(os.environ.get('GRAMIDE_BENCH_HOME',str(Path.home())))/'.almide/cache'
refs={'gramide':('gramide','c7c768e4da3c5472a81f5f737dc8e4ab75d72197'),'gramide-json':('gramide_json','fb26545e859d3ccffd0e0e16baffea1686f24f93'),'gramide-java':('gramide_java','8ad7b1d7c3a382bff25b0d335f80497acbc3d336'),'gramide-typescript':('gramide_typescript','39537a672e09d43a35150712d5fc95c0128b3a01'),'gramide-javascript':('gramide_javascript','809e55f631b465652a2b96903b6f0c0b9409c950')}
paths={name:cache/alias/sha[:12] for name,(alias,sha) in refs.items()}
if args.candidate:paths={'gramide':ROOT/'sources/gramide',**{n:ROOT/'candidate-packages'/n for n in refs if n!='gramide'}}
paths['harness']=ROOT/('gramide-harness-candidate' if args.candidate else 'gramide-harness')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
inputs={name:{str(p.relative_to(path)):sha(p) for p in sorted([*path.glob('src/**/*.almd'),path/'almide.toml']) if p.is_file()} for name,path in paths.items()}
compiler=Path(shutil.which(os.environ.get('ALMIDE_BIN','almide')) or os.environ.get('ALMIDE_BIN','almide'))
r={'binary_sha256':sha(args.binary),'built_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'compiler_version':subprocess.check_output([str(compiler),'--version'],text=True).strip(),'compiler_sha256':sha(compiler),'compiler_source_checkout_commit':os.environ.get('ALMIDE_SOURCE_COMMIT'),'compiler_source_relationship':'optional caller-supplied checkout metadata; compiler binary SHA-256 is authoritative','mode':'candidate' if args.candidate else 'baseline','build_flags':['--release'],'inputs_sha256':inputs,'upstream_base_commits':{n:v[1] for n,v in refs.items()},'candidate_pins':json.loads((ROOT/'source-pins.json').read_text()) if args.candidate else None,'harness_manifest':(paths['harness']/'almide.toml').read_text(),'rustc':subprocess.check_output(['rustc','--version'],text=True).strip(),'generated_cargo_manifest':(Path(os.environ.get('GRAMIDE_BENCH_TMPDIR',str(ROOT/'build-cache')))/'almide-run/Cargo.toml').read_text(),'generated_cargo_lock_sha256':sha(Path(os.environ.get('GRAMIDE_BENCH_TMPDIR',str(ROOT/'build-cache')))/'almide-run/Cargo.lock'),'rustflags':os.environ.get('RUSTFLAGS','')}
Path(str(args.binary)+'.build.json').write_text(json.dumps(r,indent=2)+'\n')
