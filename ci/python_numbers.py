"""CPython compiler acceptance plus tokenizer byte endpoints for numeric literals."""
from pathlib import Path
import io,json,os,platform,shutil,subprocess,tempfile,tokenize,warnings
ROOT=Path(__file__).resolve().parents[1]
valid=set(['0','00','0_0','123','1_234','.5','1.','01.2','01e2','01j','1e999','1e-999'])
for base,digits in [('b','10101'),('o','76543'),('x','aB09F')]:
    for tag in [base,base.upper()]:
        for body in [digits,'_'.join(digits),'_'+digits,'_'+'_'.join(digits)]:valid.add('0'+tag+body)
for whole in ['0','00','01','1','12','1_2']:
    for fraction in ['', '.', '.0','.1_2']:
        for exponent in ['', 'e0','E+12','e-1_2']:
            for imaginary in ['', 'j','J']:
                candidate=whole+fraction+exponent+imaginary
                try:compile(candidate,'literal','eval')
                except SyntaxError:continue
                valid.add(candidate)
valid.update(['1and 2','1or 2','1if True else 2','1in [1]','1is 2','1not in [2]'])
cases=[];expected=[]
with warnings.catch_warnings():
    warnings.simplefilter('ignore',SyntaxWarning)
    for source in sorted(valid):
        compile(source,'literal','eval')
        first=next(tokenize.generate_tokens(io.StringIO(source).readline))
        assert first.type==tokenize.NUMBER,(source,first)
        for prefix in ['', '🪨 ']:
            cases.append(dict(source=prefix+source+' + 3',start=len(prefix.encode())))
            expected.append(len(prefix.encode())+len(first.string.encode()))
accepted=len(cases)
invalid=['01','0_1','000123','1_','1__2','0x','0x_','0x__1','0x1_','0x1g','0b2','0b102','0o8','0o789','0b_2','0o_8','1e','1e+','1e-','1e_2','1e+_2','1e2_','1e2j_','1._2','.5_','1j2','0x1j','1foo','1or2','1andrew','1.0f','1e2elsewhere']
for source in invalid:
    try:compile(source,'literal','eval')
    except SyntaxError:pass
    else:raise AssertionError(('CPython accepts invalid fixture',source))
    cases.append(dict(source=source,start=0));expected.append(None)
with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);(project/'src/packages/python').mkdir(parents=True)
    for file in ['tree.almd','names.almd','lex.almd','packages/python/numbers.almd']:
        shutil.copyfile(ROOT/'src'/file,project/'src'/file)
    shutil.copyfile(ROOT/'ci/python_numbers_probe.almd',project/'src/main.almd')
    (project/'almide.toml').write_text('[package]\nname = "numbers_probe"\nversion = "0.1.0"\nedition = "2026"\n')
    binary=project/'probe'
    subprocess.run([os.environ.get('ALMIDE_BIN','almide'),'build','-o',str(binary)],cwd=project,check=True)
    data=project/'cases.json';data.write_text(json.dumps({'cases':cases},ensure_ascii=False))
    result=json.loads(subprocess.check_output([str(binary),str(data)],text=True))
    assert len(result)==len(expected)
    for case,want,actual in zip(cases,expected,result):
        assert actual['ok']==(want is not None),(case,want,actual)
        if want is not None:assert actual['end']==want,(case,want,actual)
print(f'CPython {platform.python_version()}: {accepted} numeric boundaries and {len(invalid)} rejected literals match')
