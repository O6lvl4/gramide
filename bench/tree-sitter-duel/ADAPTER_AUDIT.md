# Adapter audit before final timing

The initial local run was a diagnostic, not final published evidence.

- Gramide full parse calls `lang.parse_lang` and therefore `parser.parse_with`;
  it never substitutes `parser.verify` or skips creating its result tree.
- Generated Rust was inspected. The first adapter accidentally cloned the
  prepared Language value on every warm parse. `mut l` now borrows that value;
  the final baseline must be rebuilt with this correction. This is a harness
  fix, not a parser optimization or a claimed product speedup.
- The selected-kind table in the adapter is borrowed, not copied per node.
- Initial selected symbols exposed intentional TypeScript AST boundaries:
  semicolon separators and `declare` can sit on different wrapper nodes. The
  canonical extraction contract must define those consistently before timing.
- Python child RSS had an inherited ~8.4MiB floor and could not distinguish
  these small processes. Those memory numbers are INVALID. The final memory
  runner uses a tiny native fork/exec/wait4 launcher, whose overhead is reported.
- Two diagnostic runs briefly overlapped at the end of the first batch. That
  batch is PRELIMINARY and must not be used as final speed evidence. The final
  run is serialized in a separately reserved CPU window.
- Cross-output line normalization originally rescanned the source per symbol;
  it now builds one newline index and bisects it. This untimed oracle cost
  cannot be counted as parser performance.
- Every final result records binary/source/protocol/corpus hashes and UTC start.
