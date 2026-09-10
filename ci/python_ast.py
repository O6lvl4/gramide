"""Shared CPython/gramide structural normalization; no code is evaluated."""
import ast

OP={ast.Add:'+',ast.Sub:'-',ast.Mult:'*',ast.Div:'/',ast.FloorDiv:'//',ast.Mod:'%',ast.MatMult:'@',ast.Pow:'**',ast.LShift:'<<',ast.RShift:'>>',ast.BitAnd:'&',ast.BitXor:'^',ast.BitOr:'|',ast.And:'and',ast.Or:'or',ast.Eq:'==',ast.NotEq:'!=',ast.Lt:'<',ast.LtE:'<=',ast.Gt:'>',ast.GtE:'>=',ast.In:'in',ast.NotIn:'not in',ast.Is:'is',ast.IsNot:'is not',ast.USub:'-',ast.UAdd:'+',ast.Invert:'~',ast.Not:'not'}
def reference_fields(n,source):
    fields=[]
    for v in n.values:
        if isinstance(v,(ast.FormattedValue,ast.Interpolation)):
            fields.append([reference(v.value,source),chr(v.conversion) if v.conversion>=0 else None,
                           reference_fields(v.format_spec,source) if v.format_spec is not None else None])
    return fields
def reference(n,source):
    if isinstance(n,(ast.JoinedStr,ast.TemplateStr)):
        family='template' if isinstance(n,ast.TemplateStr) else 'text'
        return ['strings',family,reference_fields(n,source)]
    if isinstance(n,ast.Constant) and isinstance(n.value,(str,bytes)):
        return ['strings','bytes' if isinstance(n.value,bytes) else 'text',[]]
    if isinstance(n,(ast.Name,ast.Constant)):return ['atom',ast.get_source_segment(source,n)]
    if isinstance(n,ast.Lambda):
        a=n.args;pos=a.posonlyargs+a.args
        defaults=[None]*(len(pos)-len(a.defaults))+[reference(v,source) for v in a.defaults]
        pairs=[[v.arg,d] for v,d in zip(pos,defaults)];split=len(a.posonlyargs)
        params=dict(posonly=pairs[:split],positional=pairs[split:],vararg=a.vararg.arg if a.vararg else None,
                    keywordonly=[[v.arg,reference(d,source) if d else None] for v,d in zip(a.kwonlyargs,a.kw_defaults)],kwarg=a.kwarg.arg if a.kwarg else None)
        return ['lambda',params,reference(n.body,source)]
    if isinstance(n,(ast.Await,ast.Yield,ast.YieldFrom)):
        kind={ast.Await:'await',ast.Yield:'yield',ast.YieldFrom:'yield_from'}[type(n)]
        return [kind,reference(n.value,source) if n.value else None]
    if isinstance(n,ast.NamedExpr):return ['named',reference(n.target,source),reference(n.value,source)]
    if isinstance(n,(ast.ListComp,ast.SetComp,ast.DictComp,ast.GeneratorExp)):
        kind={ast.ListComp:'listcomp',ast.SetComp:'setcomp',ast.DictComp:'dictcomp',ast.GeneratorExp:'generator'}[type(n)]
        values=[reference(n.key,source),reference(n.value,source)] if isinstance(n,ast.DictComp) else [reference(n.elt,source)]
        clauses=[[g.is_async,reference(g.target,source),reference(g.iter,source),[reference(v,source) for v in g.ifs]] for g in n.generators]
        return [kind,values,clauses]
    if isinstance(n,ast.BinOp):return ['bin',OP[type(n.op)],reference(n.left,source),reference(n.right,source)]
    if isinstance(n,ast.UnaryOp):return ['unary',OP[type(n.op)],reference(n.operand,source)]
    if isinstance(n,ast.BoolOp):
        out=reference(n.values[0],source)
        for v in n.values[1:]:out=['bool',OP[type(n.op)],out,reference(v,source)]
        return out
    if isinstance(n,ast.Compare):return ['compare',reference(n.left,source),[[OP[type(op)],reference(v,source)] for op,v in zip(n.ops,n.comparators)]]
    if isinstance(n,ast.IfExp):return ['if',reference(n.test,source),reference(n.body,source),reference(n.orelse,source)]
    if isinstance(n,(ast.List,ast.Tuple,ast.Set)):return [type(n).__name__.lower(),[reference(v,source) for v in n.elts]]
    if isinstance(n,ast.Starred):return ['starred',reference(n.value,source)]
    if isinstance(n,ast.Dict):return ['dict',[[reference(k,source) if k else None,reference(v,source)] for k,v in zip(n.keys,n.values)]]
    if isinstance(n,ast.Slice):return ['slice',*[reference(v,source) if v else None for v in (n.lower,n.upper,n.step)]]
    if isinstance(n,ast.Attribute):return ['attr',reference(n.value,source),n.attr]
    if isinstance(n,ast.Call):return ['call',reference(n.func,source),[reference(v,source) for v in n.args],[[v.arg,reference(v.value,source)] for v in n.keywords]]
    if isinstance(n,ast.Subscript):return ['sub',reference(n.value,source),reference(n.slice,source)]
    raise AssertionError(ast.dump(n))
def actual_fields(nodes):
    fields=[]
    for n in nodes:
        if n['kind']!='replacement':continue
        parts=n['kids'];conversion=None;format_=None;debug=False
        for part in parts[1:]:
            if part['kind']=='conversion':conversion=part['kids'][0]['text']
            elif part['kind']=='format':format_=actual_fields(part['kids'])
            elif part['text']=='=':debug=True
        if debug and conversion is None and format_ is None:conversion='r'
        fields.append([actual(parts[0]),conversion,format_])
    return fields
def actual(n):
    kids=n['kids'];kind=n['kind']
    if kind in ('text_strings','byte_strings','template_strings'):
        family={'text_strings':'text','byte_strings':'bytes','template_strings':'template'}[kind]
        fields=[]
        for part in kids:
            if part['kind'] in ('fstring','tstring'):fields.extend(actual_fields(part['kids']))
        return ['strings',family,fields]
    if kind=='lambda':
        params=dict(posonly=[],positional=[],vararg=None,keywordonly=[],kwarg=None)
        keywordonly=False
        for p in kids[0]['kids']:
            if p['text']=='/' and not p['kids']:
                params['posonly']=params['positional'];params['positional']=[]
            elif p['text']=='*' and not p['kids']:keywordonly=True
            elif p['kind'] in ('vararg','kwarg'):
                params[p['kind']]=p['kids'][0]['kids'][0]['text'];keywordonly=True
            else:
                pair=[p['kids'][0]['text'],actual(p['kids'][1]) if len(p['kids'])>1 else None]
                params['keywordonly' if keywordonly else 'positional'].append(pair)
        return ['lambda',params,actual(kids[1])]
    if kind in ('await','yield','yield_from'):return [kind,actual(kids[0]) if kids else None]
    if kind=='named':return ['named',actual(kids[0]),actual(kids[1])]
    if kind in ('listcomp','setcomp','dictcomp','generator'):
        count=2 if kind=='dictcomp' else 1
        clauses=[]
        for clause in kids[count:]:
            parts=clause['kids'];async_=int(parts[0]['text']=='async')
            clauses.append([async_,actual(parts[async_]),actual(parts[async_+1]),[actual(v['kids'][0]) for v in parts[async_+2:]]])
        return [kind,[actual(v) for v in kids[:count]],clauses]
    if kind in ('list','tuple','set'):return [kind,[actual(k) for k in kids]]
    if kind=='starred':return ['starred',actual(kids[0])]
    if kind=='dict':return ['dict',[[None,actual(k['kids'][0])] if k['kind']=='dict_unpack' else [actual(k['kids'][0]),actual(k['kids'][1])] for k in kids]]
    if kind=='slice':
        parts=[None,None,None];index=0
        for k in kids:
            if k['text']==':' and not k['kids']:index+=1
            else:parts[index]=actual(k)
        return ['slice',*parts]
    if not kids:return ['atom',n['text']]
    if kind in ('binary','boolean'):return ['bin' if kind=='binary' else 'bool',kids[1]['text'],actual(kids[0]),actual(kids[2])]
    if kind=='unary':return ['unary',kids[0]['text'],actual(kids[1])]
    if kind=='power' and len(kids)>1:return ['bin','**',actual(kids[0]),actual(kids[2])]
    if kind=='conditional' and len(kids)>1:return ['if',actual(kids[2]),actual(kids[0]),actual(kids[4])]
    if kind=='comparison' and len(kids)>1:return ['compare',actual(kids[0]),[[' '.join(k['text'] for k in kids[i]['kids']),actual(kids[i+1])] for i in range(1,len(kids),2)]]
    if kind=='primary':
        out=actual(kids[0])
        for suffix in kids[1:]:
            if suffix['kind']=='attribute':out=['attr',out,suffix['kids'][0]['text']]
            elif suffix['kind']=='call':
                positional=[];keywords=[]
                for k in suffix['kids']:
                    if k['kind']=='keyword':keywords.append([k['kids'][0]['text'],actual(k['kids'][1])])
                    elif k['kind']=='mapping':keywords.append([None,actual(k['kids'][0])])
                    else:positional.append(actual(k))
                out=['call',out,positional,keywords]
            elif suffix['kind']=='subscript':out=['sub',out,actual(suffix['kids'][0])]
            else:raise AssertionError(suffix)
        return out
    assert len(kids)==1,n
    return actual(kids[0])


def decode_tree(result):
    """Rejoin token text once in Python; the native tree walk carries no tokens."""
    tokens=result['tokens']
    def visit(n):
        start=n.pop('start')
        n['text']=tokens[start] if not n['kids'] and start<len(tokens) else ''
        for k in n['kids']:visit(k)
        return n
    return visit(result['tree'])
