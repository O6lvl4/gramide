// Independent range oracle using Go's standard parser, not gramide's tree.
package main
import("encoding/json";"go/ast";"go/parser";"go/token";"os")
type Symbol struct { Name string `json:"name"`; Start int `json:"start"`; End int `json:"end"`; StartByte int `json:"start_byte"`; EndByte int `json:"end_byte"` }
func main(){
 fset:=token.NewFileSet(); f,err:=parser.ParseFile(fset,os.Args[1],nil,parser.AllErrors);if err!=nil{panic(err)}
 out:=[]Symbol{}
 ast.Inspect(f,func(n ast.Node)bool{
  fn,ok:=n.(*ast.FuncDecl);if !ok{return true};name:=fn.Name.Name
  if fn.Recv!=nil {typ:=fn.Recv.List[0].Type;if p,ok:=typ.(*ast.StarExpr);ok{typ=p.X};if id,ok:=typ.(*ast.Ident);ok{name=id.Name+"."+name}}
  a,b:=fset.Position(fn.Pos()),fset.Position(fn.End())
  out=append(out,Symbol{name,a.Line,fset.Position(fn.End()-1).Line,a.Offset,b.Offset});return true
 });if err:=json.NewEncoder(os.Stdout).Encode(out);err!=nil{panic(err)}
}
