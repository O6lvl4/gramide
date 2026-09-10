"""Score missing overloads without consuming later exact declarations."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'bench'))
from python_recovery import compare
first=dict(name='overload',kind='function',owner='',start=1,end=1,start_byte=0,end_byte=10)
second={**first,'start':3,'end':3,'start_byte':20,'end_byte':30}
result=compare([second],[first,second])
assert result==dict(missing=[first],spurious=[],incorrect=[],exact=False),result
result=compare([second,second],[first,second])
assert len(result['incorrect'])==1 and not result['missing'] and not result['spurious'],result
assert len(compare([first,first],[first])['spurious'])==1
assert compare([first,second],[first,second])['exact']
assert compare([],[])['exact']
print('Recovery comparison: missing overload, duplicate and exact-match accounting passed')
