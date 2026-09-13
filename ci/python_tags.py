"""What the Python package reports as definitions and references, and what it does not.

`tags` is the repo map's input: definitions to rank, references to rank them by.
Python has no node that means "a type", so a type mention is read from the three
places one can be written — after a `:`, after a `->`, and in a class's bases —
and only when what is written there is a bare name. Everything this does not
cover is listed at the bottom of this file, as a case with no output, so that
adding it later is a diff here rather than a surprise.
"""
from pathlib import Path
import subprocess, tempfile

BIN = Path(__file__).resolve().parents[1] / "gramide"

COVERED = [
 ("a plain call", "def f():\n    return helper(1)\n",
  ["def function f L1-2", "ref call helper L2"]),
 ("a call through an attribute", "def f(p):\n    return p.join('x')\n",
  ["def function f L1-2", "ref call p.join L2"]),
 ("a class instantiated is a call", "def f():\n    return Thing()\n",
  ["def function f L1-2", "ref call Thing L2"]),
 ("a decorator that is applied", "@app.route('/x')\ndef f():\n    ...\n",
  ["def function f L1-3", "ref call app.route L1"]),
 ("a base class", "class Sub(Thing):\n    ...\n",
  ["def class Sub L1-2", "ref type Thing L1"]),
 ("a parameter annotation", "def f(x: Foo):\n    ...\n",
  ["def function f L1-2", "ref type Foo L1"]),
 ("a return annotation", "def f() -> Baz:\n    ...\n",
  ["def function f L1-2", "ref type Baz L1"]),
 ("an annotated assignment", "class D:\n    total: Counter = 0\n",
  ["def class D L1-2", "ref type Counter L2"]),
 ("methods are named with their class", "class D:\n    def m(self):\n        ...\n",
  ["def class D L1-3", "def method D.m L2-3"]),
 ("a function inside a function is named with it", "def outer():\n    def inner():\n        ...\n",
  ["def function outer L1-3", "def function outer.inner L2-3"]),
 ("async is a function like any other", "async def f():\n    await g()\n",
  ["def function f L1-2", "ref call g L2"]),
 ("a type alias", "type Alias = int\n", ["def type Alias L1-1"]),
]

# Each of these is a reference a reader can see and `tags` does not report. None
# is a defect to be fixed quietly: each is a decision, and changing one should
# change this list.
NOT_COVERED = [
 ("a bare-name decorator names a callable, but there is no call to see",
  "@decorator\ndef f():\n    ...\n", ["def function f L1-3"]),
 ("an import is a reference, and Rust's `use` is not reported either",
  "from a import Thing\nimport os.path\n", []),
 ("a subscripted annotation is an expression, not a name",
  "def f(x: list[int]):\n    ...\n", ["def function f L1-2"]),
 ("a string annotation is a string until something decodes it",
  "def f(x: 'Bar'):\n    ...\n", ["def function f L1-2"]),
 ("a union annotation is two names and the rule takes the first thing only",
  "def f(x: Foo | None):\n    ...\n", ["def function f L1-2"]),
 ("a second base class, for the same reason: one mention per place one is written",
  "class Sub(Base, Mixin):\n    ...\n", ["def class Sub L1-2", "ref type Base L1"]),
]

with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    for label, source, expected in COVERED + NOT_COVERED:
        path = root / "case.py"
        path.write_text(source)
        result = subprocess.run([str(BIN), "tags", str(path)], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0 and not result.stderr, (label, result.returncode, result.stderr)
        assert result.stdout.split("\n")[:-1] == expected, (label, source, expected, result.stdout)
print(f"Python tags: {len(COVERED)} reported cases and {len(NOT_COVERED)} deliberately unreported ones")
