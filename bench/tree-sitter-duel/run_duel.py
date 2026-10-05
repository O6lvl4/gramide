#!/usr/bin/env python3
"""Correctness-gated serial parser duel; raw timings are never discarded."""
from pathlib import Path
import argparse, bisect, hashlib, json, os, platform, random, statistics, subprocess, time

ROOT = Path(__file__).resolve().parent

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def command(binpath, mode, language, path, count=None):
    cmd = [str(binpath), mode, language, str(path)]
    if count is not None: cmd.append(str(count))
    return cmd

def run(cmd, timeout=120, env=None):
    t0 = time.perf_counter_ns()
    try:
        p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, env=env)
        return {'ns':time.perf_counter_ns()-t0,'returncode':p.returncode,'stdout':p.stdout.decode('utf8','replace'),'stderr':p.stderr.decode('utf8','replace')}
    except subprocess.TimeoutExpired as e:
        return {'ns':time.perf_counter_ns()-t0,'returncode':124,'stdout':(e.stdout or b'').decode('utf8','replace'),'stderr':'TIMEOUT '+(e.stderr or b'').decode('utf8','replace')}

def oracle(language,path):
    if language == 'json':
        def invalid(x): raise ValueError('nonfinite JSON constant '+x)
        try:
            json.loads(path.read_text(), parse_constant=invalid)
            return {'valid':True,'version':platform.python_version()}
        except (ValueError, UnicodeError) as e: return {'valid':False,'diagnostic':str(e),'version':platform.python_version()}
    if language == 'typescript': cmd = ['node',str(ROOT/'oracles/typescript.cjs'),str(path)]
    else: cmd = ['java','-cp',str(ROOT/'oracles'),'JavaParseOracle',str(path)]
    r = run(cmd)
    if r['returncode']: return {'valid':None,'error':r['stderr']}
    return json.loads(r['stdout'])

def stats(samples):
    xs = sorted(samples)
    return {'median_ns':statistics.median(xs),'p90_ns':xs[min(len(xs)-1,int(len(xs)*.9))],'min_ns':xs[0],'max_ns':xs[-1],'samples_ns':samples}

def normalize_symbols(records, source):
    # Lines are derived from exact UTF-8 ranges, never used to repair a range.
    output=[]
    newlines=[i for i,c in enumerate(source) if c==10]
    for row in records:
        assert set(row) == {'kind','name','start_byte','end_byte'}, row
        s,e = row['start_byte'],row['end_byte']
        assert isinstance(s,int) and isinstance(e,int) and 0 <= s < e <= len(source),row
        output.append({**row,'start':bisect.bisect_left(newlines,s)+1,'end':bisect.bisect_left(newlines,max(s,e-1))+1})
    return sorted(output,key=lambda x:(x['start_byte'],x['end_byte'],x['kind'],x['name']))

def rss(cmd):
    r=run([str(ROOT/'bin/resource-probe'),*cmd])
    if r['returncode']: return {'error':r}
    result=json.loads(r['stdout'])
    return {k:v for k,v in result.items() if k not in ['stdout','stderr']}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--gramide',type=Path,default=ROOT/'bin/gramide-baseline')
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--gate-only',action='store_true')
    ap.add_argument('--cold-samples',type=int,default=9)
    ap.add_argument('--warm-samples',type=int,default=31)
    ap.add_argument('--warm-batches',type=int,default=5)
    ap.add_argument('--seed',type=int,default=8924)
    ap.add_argument('--split',choices=['all','development','heldout'],default='all')
    ap.add_argument('--only',default='')
    args=ap.parse_args()
    assert args.cold_samples>0 and args.warm_samples>0
    manifest=json.loads((ROOT/'corpus/manifest.json').read_text())
    rng=random.Random(args.seed)
    report={'protocol':sha(ROOT/'PROTOCOL.md'),'references':json.loads((ROOT/'references.lock.json').read_text()),
      'memory_method':'native fork/exec wait4 Linux ru_maxrss; separate runs','platform':platform.platform(),'cpu_affinity':sorted(os.sched_getaffinity(0)),'cpu_model':next((l.split(':',1)[1].strip() for l in Path('/proc/cpuinfo').read_text().splitlines() if l.startswith('model name')),''),
      'manifest_sha256':sha(ROOT/'corpus/manifest.json'),'build_provenance':json.loads(Path(str(args.gramide)+'.build.json').read_text()),'tree_sitter_build_provenance':{},'seed':args.seed,'configuration':vars(args)|{'gramide':str(args.gramide),'out':str(args.out)},
      'binary_sha256':{'gramide':sha(args.gramide)},'files':[]}
    assert report['build_provenance']['binary_sha256']==sha(args.gramide)
    report['memory_launcher_control']=json.loads((ROOT/'evidence/rss-control.json').read_text())
    def save():
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps(report,indent=2)+'\n')
    for f in manifest['files']:
        if args.only and args.only not in f['id']: continue
        if args.split!='all' and f['split']!=args.split: continue
        if f.get('grammar_variant') == 'tsx':
            report['files'].append({**f,'not_tested_grammar_variant':'tsx','competitive_parse_eligible':False})
            save()
            continue
        path=ROOT/'corpus'/f['path']; data=path.read_bytes()
        assert sha(path)==f['sha256'],f['id']+' source changed after freeze'
        lang=f['language']; sitter=ROOT/'bin'/('tree-sitter-'+lang)
        bins={'gramide':args.gramide.resolve(),'tree_sitter':sitter.resolve()}
        report['binary_sha256']['tree_sitter_'+lang]=sha(sitter)
        c_provenance=json.loads(Path(str(sitter)+'.build.json').read_text())
        assert c_provenance['binary_sha256']==sha(sitter)
        assert c_provenance['adapter_sha256']==sha(ROOT/'tree_sitter_adapter.c')
        report['tree_sitter_build_provenance'][lang]=c_provenance
        row={**f,'started_at_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'oracle':oracle(lang,path),'gates':{}}
        commands={tool:command(binary,'parse',lang,path) for tool,binary in bins.items()}
        for tool,cmd in commands.items(): row['gates'][tool]=run(cmd)
        if f.get('minimum_java_release',0)>21 and row['oracle'].get('version','').startswith('21'):
            row['oracle']={'valid':None,'reason':'fixture requires Java '+str(f['minimum_java_release'])+'; available parse oracle is Java21','observed_java21':row['oracle']}
        accepted={t:r['returncode']==0 for t,r in row['gates'].items()}
        row['accepted']=accepted
        row['competitive_parse_eligible']=all(accepted.values()) and row['oracle']['valid'] is True
        row['symbols']={}
        if row['competitive_parse_eligible']:
            syms={}
            for tool,binary in bins.items():
                r=run(command(binary,'symbols',lang,path)); row['symbols'][tool]={'returncode':r['returncode'],'stderr':r['stderr']}
                if r['returncode']==0:
                    try: syms[tool]=normalize_symbols(json.loads(r['stdout']),data)
                    except (ValueError,AssertionError) as e: row['symbols'][tool]['error']=str(e)
            row['symbols_match']=len(syms)==2 and syms['gramide']==syms['tree_sitter']
            row['symbol_counts']={t:len(s) for t,s in syms.items()}
            if not row['symbols_match']: row['symbol_mismatch_records']=syms
            if not args.gate_only:
                row['cold_full_parse']={t:[] for t in bins}
                row['cold_selected_symbols']={t:[] for t in bins} if row['symbols_match'] else None
                # Each block has one run of each engine; engine order is shuffled.
                for mode,key in [('parse','cold_full_parse'),('symbols','cold_selected_symbols')]:
                    if row[key] is None: continue
                    for tool,binary in bins.items():
                        warm=run(command(binary,mode,lang,path)); assert warm['returncode']==0,warm
                    for _ in range(args.cold_samples):
                        order=list(bins);rng.shuffle(order)
                        for tool in order:
                            r=run(command(bins[tool],mode,lang,path)); assert r['returncode']==0,r
                            row[key][tool].append(r['ns'])
                    row[key]={t:stats(xs) for t,xs in row[key].items()}
                batches={t:[] for t in bins};row['warm_engine_orders']=[]
                for batch in range(args.warm_batches):
                    order=list(bins);rng.shuffle(order);row['warm_engine_orders'].append(order)
                    for tool in order:
                        r=run(command(bins[tool],'warm',lang,path,args.warm_samples)); assert r['returncode']==0,r
                        batches[tool].append(json.loads(r['stdout']))
                row['warm_full_parse']={t:{'batches':bs,'batch_medians_ns':[statistics.median(b['samples_ns']) for b in bs],
                    **stats([n for b in bs for n in b['samples_ns']])} for t,bs in batches.items()}
                row['memory']={t:[rss(commands[t]) for _ in range(3)] for t in bins}
        report['files'].append(row)
        save()
        print(f['id'],accepted,'oracle',row['oracle']['valid'],'symbols',row.get('symbols_match'),flush=True)
    report['summary']={'total':len(report['files']), 'parse_eligible':sum(f['competitive_parse_eligible'] for f in report['files']),
        'symbols_equal':sum(f.get('symbols_match',False) for f in report['files'])}
    save()
if __name__=='__main__': main()
