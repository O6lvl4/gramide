"""Deterministic invalid-line edits in complete Python stdlib source files."""
from pathlib import Path
import argparse,ast,hashlib,json,platform,subprocess,sys,sysconfig,tempfile
from python_recovery import FIELDS,compare
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ci'))
from python_symbols import expected

FILES=['keyword','token','stat','copyreg','genericpath','reprlib','textwrap','inspect','tokenize','ast','dataclasses','typing']
EDITS={'assignment':'x =','missing-colon':'if True','stray-closer':')','invalid-character':'$','single-string':'x = "unfinished'}


def anchors(source):
    lines=source.splitlines(keepends=True)
    offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line.encode()))
    found={}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):continue
        stmt=node.body[0]
        decorators=getattr(stmt,'decorator_list',[])
        line=min([stmt.lineno]+[d.lineno for d in decorators])
        # Skip inline suites and use whole physical lines before decorators.
        if line<=node.lineno:continue
        raw=lines[line-1]
        indent=raw[:len(raw)-len(raw.lstrip(' \t'))]
        assert indent, (node.name,line)
        found[offsets[line-1]]=dict(offset=offsets[line-1],line=line,indent=indent,scope=node.name)
    ordered=[found[k] for k in sorted(found)]
    # Evenly distributed anchors are selected before either parser is invoked.
    chosen=sorted({i*(len(ordered)-1)//3 for i in range(4)}) if ordered else []
    return [dict(offset=0,line=1,indent='',scope='<module>')]+[ordered[i] for i in chosen]


def shifted(rows,offset,inserted,omit_damaged):
    delta=len(inserted.encode());line_delta=inserted.count('\n')
    result=[]
    for row in rows:
        item=dict(row)
        if row['start_byte']<offset<row['end_byte']:
            if omit_damaged:continue
            item['end_byte']+=delta;item['end']+=line_delta
        elif row['start_byte']>=offset:
            item['start_byte']+=delta;item['end_byte']+=delta
            item['start']+=line_delta;item['end']+=line_delta
        result.append(item)
    return result


def invoke(binary,label,path,recovery):
    flags=(['symbols-recovered' if recovery else 'symbols'] if label=='gramide' else ['--recover'] if recovery else [])
    try:r=subprocess.run([str(binary),*flags,str(path)],capture_output=True,text=True,timeout=15)
    except subprocess.TimeoutExpired:return dict(unavailable='timeout after 15s')
    if r.returncode:return dict(unavailable=f'exit {r.returncode}',diagnostic=r.stderr.replace(str(path),'<input>'))
    payload=json.loads(r.stdout)
    rows=payload['symbols'] if label=='gramide' else payload
    return dict(rows=[{k:s[k] for k in FIELDS} for s in rows],complete=payload['complete'] if label=='gramide' else None)


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    for name in ['gramide','tree-sitter','references','output']:ap.add_argument('--'+name,type=Path,required=True)
    args=ap.parse_args()
    if sys.version_info[:2]!=(3,14):raise SystemExit('Run with Python 3.14 for the CPython oracle')
    bins={'gramide':args.gramide.resolve(),'tree_sitter':args.tree_sitter.resolve()}
    report=dict(python=platform.python_version(),platform=platform.platform(),
        scope='Five invalid-line insertions at module start and up to four evenly sampled function/class body starts in 12 complete stdlib files. This is a deterministic edit model, not representative keystrokes or all Python.',
        policy='Exclude declarations containing the insertion; preserve all other original names, kinds, owners and ranges shifted by the edit. Invalid lines are intended as isolated damage, not new lexical scopes. This desired recovery policy is not a CPython AST for invalid input.',
        validation='Both unedited parsers must match CPython. A pass-line control must preserve original AST declarations and shifted ranges. Every damaged input must be rejected by CPython ast.parse.',
        mode='Fresh full-file parse and symbol extraction per edit; no incremental reuse or performance measurement. Same conservative tree-sitter adapter as python_recovery.py.',
        binary_sha256={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in bins.items()},
        source_sha256={n:hashlib.sha256((Path(__file__).parent/n).read_bytes()).hexdigest() for n in ['python_edit_corpus.py','python_recovery.py','tree_sitter_python.c']},
        reference_commits={n:subprocess.check_output(['git','rev-parse','HEAD'],cwd=args.references/n,text=True).strip() for n in ['tree-sitter','tree-sitter-python']},files=[],cases=[])
    with tempfile.TemporaryDirectory() as tmp:
        path=Path(tmp)/'edited.py'
        for name in FILES:
            original=Path(sysconfig.get_path('stdlib'))/(name+'.py')
            source=original.read_text();raw=source.encode();want=expected(source)
            path.write_bytes(raw)
            for label,binary in bins.items():
                result=invoke(binary,label,path,False)
                assert 'rows' in result and result['rows']==want,(name,label,result)
            points=anchors(source)
            report['files'].append(dict(file=original.name,source_sha256=hashlib.sha256(raw).hexdigest(),bytes=len(raw),declarations=len(want),anchors=points))
            for point in points:
                offset=point['offset'];indent=point['indent']
                control=indent+'pass\n'
                assert expected((raw[:offset]+control.encode()+raw[offset:]).decode())==shifted(want,offset,control,False),(name,point)
                for kind,text in EDITS.items():
                    inserted=indent+text+'\n'
                    edited=raw[:offset]+inserted.encode()+raw[offset:]
                    try:ast.parse(edited.decode())
                    except SyntaxError:pass
                    else:raise AssertionError((name,point,kind))
                    path.write_bytes(edited)
                    target=shifted(want,offset,inserted,True)
                    case=dict(file=original.name,anchor=point,edit=kind,inserted=inserted,edited_sha256=hashlib.sha256(edited).hexdigest(),expected_count=len(target),results={})
                    for label,binary in bins.items():
                        result=invoke(binary,label,path,True)
                        if 'rows' not in result:case['results'][label]=result;continue
                        case['results'][label]=dict(actual_count=len(result['rows']),complete=result['complete'],**compare(result['rows'],target))
                    report['cases'].append(case)
            print(name,len(points)*len(EDITS),'edits',flush=True)
    report['totals']={}
    for label in bins:
        report['totals'][label]={}
        for kind in ['all',*EDITS]:
            cases=[c for c in report['cases'] if kind=='all' or c['edit']==kind]
            results=[c['results'][label] for c in cases]
            report['totals'][label][kind]=dict(cases=len(cases),exact=sum(r.get('exact',False) for r in results),unavailable=sum('unavailable' in r for r in results),missing=sum(len(r.get('missing',[])) for r in results),spurious=sum(len(r.get('spurious',[])) for r in results),incorrect=sum(len(r.get('incorrect',[])) for r in results))
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps(report['totals'],indent=2))


if __name__=='__main__':main()
