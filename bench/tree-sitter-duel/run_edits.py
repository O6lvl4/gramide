#!/usr/bin/env python3
from pathlib import Path
import argparse,hashlib,json,os,random,statistics,subprocess,tempfile
from run_duel import run,sha,stats,ROOT
ap=argparse.ArgumentParser();ap.add_argument('--gramide',type=Path,default=ROOT/'bin/gramide-baseline');ap.add_argument('--out',type=Path,required=True);ap.add_argument('--gate-only',action='store_true');ap.add_argument('--repeats',type=int,default=3);args=ap.parse_args()
report={'build_provenance':json.loads(Path(str(args.gramide)+'.build.json').read_text()),'gramide_sha256':sha(args.gramide),'script_manifest_sha256':sha(ROOT/'edits/manifest.json'),'files':[]};rng=random.Random(8924)
for f in json.loads((ROOT/'edits/manifest.json').read_text())['files']:
    source=ROOT/'corpus'/f['source_path'];script=ROOT/'edits'/f['script'];language=f['language']
    assert sha(source)==f['source_sha256'] and sha(script)==f['script_sha256']
    bins={'gramide':args.gramide,'tree_sitter':ROOT/'bin'/('tree-sitter-'+language)}
    row={**f,'tree_sitter_build_provenance':json.loads(Path(str(bins['tree_sitter'])+'.build.json').read_text()),'gates':{},'initial_parse':{t:run([str(p),'parse',language,str(source)]) for t,p in bins.items()},'binary_sha256':{t:sha(p) for t,p in bins.items()}}
    with tempfile.TemporaryDirectory() as tmp:
        for tool,binary in bins.items():
            dump=Path(tmp)/(tool+'.source');env=dict(os.environ)
            cmd=[str(binary),'edits',language,str(source),str(script),'verify']
            if tool=='gramide':cmd.append(str(dump))
            else:env['TS_ADAPTER_FINAL_SOURCE']=str(dump)
            r=run(cmd,timeout=180,env=env)
            if r['returncode']==0:
                r['result']=json.loads(r.pop('stdout'));r['final_sha256']=sha(dump)
                assert r['result']['edit_count']==f['edits'],r
                assert len(r['result']['samples_ns'])==f['edits'],r
                steps=r['result']['outcomes'] if tool=='gramide' else r['result']['per_edit']
                assert len(steps)==f['edits'],r
                assert r['final_sha256']==f['final_source_sha256'],r
                assert r['result'].get('mismatches',r['result'].get('mismatch_count',0))==0,r
                r['category_validity_passed']=True
                if f['category'] in ['valid_structural','token_preserving']:
                    steps=r['result']['outcomes'] if tool=='gramide' else r['result']['per_edit']
                    valid=all(step.get('valid',not step.get('fresh_has_error',True)) for step in steps)
                    r['category_validity_passed']=valid
                    if not valid:r['category_validity_error']='supposedly valid edit produced a rejected strict parse'
            row['gates'][tool]=r
        row['eligible']=all(r['returncode']==0 and r.get('category_validity_passed',False) for r in row['gates'].values()) and all(r['returncode']==0 for r in row['initial_parse'].values())
        if row['eligible'] and not args.gate_only:
            raw={t:[] for t in bins}
            for i in range(args.repeats):
                order=list(bins);rng.shuffle(order)
                for tool in order:
                    r=run([str(bins[tool]),'edits',language,str(source),str(script),'timed'],timeout=180)
                    assert r['returncode']==0,r
                    value=json.loads(r['stdout']);assert value['edit_count']==f['edits'] and len(value['samples_ns'])==f['edits'];raw[tool].append(value)
            row['timing']={t:{'runs':runs,**stats([v for r in runs for v in r['samples_ns']])} for t,runs in raw.items()}
    report['files'].append(row);args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(language,f['category'],row['eligible'],flush=True)
