"""CPython AST rendered as gramide-compatible nested outline text."""
import ast

def expected(source):
 rows=[]
 def visit(node,depth=0,owner=''):
  function=isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
  cls=isinstance(node,ast.ClassDef)
  alias=isinstance(node,ast.TypeAlias)
  if function or cls or alias:
   name=node.name.id if alias else node.name
   kind='method' if function and owner else 'function' if function else 'class' if cls else 'type'
   start=min([node.lineno]+[d.lineno for d in getattr(node,'decorator_list',[])])
   rows.append('  '*depth+f'L{start}-{node.end_lineno} {kind} '+(owner+'.' if function and owner else '')+name)
   if function or cls:
    for child in node.body:visit(child,depth+1,name if cls else '')
  else:
   for child in ast.iter_child_nodes(node):visit(child,depth,owner)
 visit(ast.parse(source))
 return ''.join(r+'\n' for r in rows)
