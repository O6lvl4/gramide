#!/usr/bin/env python3
"""Supplemental RFC-shaped syntax probes, independent of performance corpus."""
from pathlib import Path
import argparse,json
from run_duel import ROOT,run,sha,oracle
CASES={
 'empty':b'', 'whitespace_only':b' \t\r\n', 'two_documents':b'{} []',
 'line_comment':b'// comment\n{}', 'block_comment':b'{/* comment */"a":1}',
 'vertical_tab':b'\x0b{}', 'form_feed':b'\x0c{}','nonbreaking_space':'\u00a0{}'.encode(),
 'unfinished_fraction':b'1.', 'unfinished_exponent':b'1e+', 'leading_zero':b'01',
 'positive_sign':b'+1', 'nan':b'NaN', 'infinity':b'Infinity',
 'unicode_short':b'"\\u123"','unicode_nonhex':b'"\\uZZZZ"','unknown_escape':b'"\\q"',
 'raw_tab':b'"a\tb"','raw_nul':b'"a\x00b"','raw_cr':b'"a\rb"',
 'array_trailing_comma':b'[1,]','object_trailing_comma':b'{"a":1,}',
 'bare_key':b'{a:1}','missing_colon':b'{"a" 1}','missing_value':b'{"a":}',
 'valid_nested':b'{"a":[null,true,false,-1.25e+3],"b":{}}',
 'valid_surrogate_spelling':b'"\\uD834\\uDD1E"','valid_escaped_controls':b'"\\n\\r\\t\\b\\f\\u0000"',
 'valid_unicode':'{"日本語":"café 😀"}'.encode(), 'valid_duplicate_keys':b'{"a":1,"a":2}',
 'valid_cr_whitespace':b'{"a":1,\r"b":2}','valid_top_scalar':b'false',
}
ap=argparse.ArgumentParser();ap.add_argument('--gramide',type=Path,default=ROOT/'bin/gramide-baseline');ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
base=ROOT/'supplemental-json';base.mkdir(exist_ok=True);rows=[]
for key,data in CASES.items():
 p=base/(key+'.json');p.write_bytes(data);expected=oracle('json',p)
 engines={}
 for name,binary in [('gramide',args.gramide),('tree_sitter',ROOT/'bin/tree-sitter-json')]:
  r=run([str(binary),'parse','json',str(p)]);engines[name]={'accepted':r['returncode']==0,'returncode':r['returncode'],'stderr':r['stderr']}
 rows.append({'id':key,'sha256':sha(p),'valid':expected['valid'],'engines':engines})
report={'gramide_sha256':sha(args.gramide),'tree_sitter_sha256':sha(ROOT/'bin/tree-sitter-json'),'oracle':'Python json.loads with nonfinite constants rejected','cases':rows,
 'disagreements':{t:[r['id'] for r in rows if r['valid']!=r['engines'][t]['accepted']] for t in ['gramide','tree_sitter']}}
args.out.parent.mkdir(exist_ok=True,parents=True);args.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report['disagreements']))
if report['disagreements']['gramide']:raise SystemExit(1)
