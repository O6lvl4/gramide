#!/usr/bin/env python3
"""Build explicit replay scripts; no parser is called while creating them."""
from pathlib import Path
import hashlib,json,re
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'edits';OUT.mkdir(exist_ok=True)
SELECTED=['java/real/LinkedTreeMap.java','typescript/real/watchUtilities.ts','json/real/tree-sitter-java__src__node-types.json']
manifest=json.loads((ROOT/'corpus/manifest.json').read_text())
result=[]
for fixture_id in SELECTED:
    entry=next(f for f in manifest['files'] if f['id']==fixture_id)
    original=(ROOT/'corpus'/entry['path']).read_bytes()
    for category in ['token_preserving','valid_structural','temporary_broken']:
        source=original;rows=[]
        def apply(start,end,insert):
            global source
            assert 0<=start<=end<=len(source)
            rows.append(f'{start}\t{end}\t{insert.hex() or "-"}')
            source=source[:start]+insert+source[end:]
        if category=='token_preserving':
            state=7
            for i in range(200):
                state=(state*1103515245+12345)%2147483648
                start=state%(len(source)+1)
                found=None
                for region_start in [start,0]:
                    for m in re.finditer(rb'[A-Za-z_]{13,}',source[region_start:]):
                        s=region_start+m.start()
                        if s==0 or not 48<=source[s-1]<=57:
                            found=s+6;break
                    if found is not None:break
                if found is None:raise ValueError(f'no long word in {fixture_id}')
                apply(found,found if i%2==0 else found+1,bytes([97+(state//65536)%26]) if i%2==0 else b'')
        elif category=='valid_structural':
            for i in range(20):
                apply(0,0,b'\n ');apply(0,2,b'')
                if entry['language']=='json':
                    end=len(source.rstrip())-1
                    assert source[end:end+1] in [b']',b'}']
                    payload=b',null' if source[end:end+1]==b']' else b',"benchmark_added_property":true'
                    apply(end,end,payload);apply(end,end+len(payload),b'')
                else:
                    end=len(source)
                    payload=(f'\nclass BenchmarkAdded{i} {{ int benchmarkValue() {{ return 1; }} }}\n' if entry['language']=='java' else f'\nfunction benchmarkAdded{i}(value: number): number {{ return value + 1; }}\n').encode()
                    apply(end,end,payload);apply(end,end+len(payload),b'')
        else:
            for i in range(10):
                at=max(source.rfind(b'}'),source.rfind(b']'))
                assert at>=0
                deleted=source[at:at+1];apply(at,at+1,b'');apply(at,at,deleted)
                apply(0,0,b'{');apply(0,1,b'')
        name=entry['language']+'-'+category+'.tsv';path=OUT/name
        path.write_text('# start_byte\told_end_byte\tinserted_utf8_hex_or_dash\n'+'\n'.join(rows)+'\n')
        result.append({'fixture_id':fixture_id,'source_path':entry['path'],'source_sha256':entry['sha256'],'language':entry['language'],'category':category,'script':name,'edits':len(rows),'script_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'final_source_sha256':hashlib.sha256(source).hexdigest()})
(OUT/'manifest.json').write_text(json.dumps({'files':result},indent=2)+'\n')
