#!/usr/bin/env bash
# No fetch/install. All compiler invocations are strictly sequential.
# Usage: ./build_tree_sitter.sh [json|typescript|java ...]
# Default: all three. Outputs: bin/tree-sitter-{json,typescript,java}
set -euo pipefail
ROOT=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
REFERENCES="$ROOT/references"
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/tree-sitter"}
OUTPUT_DIR=${OUTPUT_DIR:-"$ROOT/bin"}
CC=${CC:-cc}
[[ $# -gt 0 ]] || set -- json typescript java
for language in "$@"; do
  case "$language" in json|typescript|java) ;; *) echo "Unknown language: $language" >&2; exit 2 ;; esac
done
command -v "$CC" >/dev/null || { echo "Compiler not found: $CC" >&2; exit 2; }
mkdir -p -- "$BUILD_DIR" "$OUTPUT_DIR"
flags=(-O3 -flto=1 -DNDEBUG -std=c11 -D_POSIX_C_SOURCE=200809L -D_DEFAULT_SOURCE -D_BSD_SOURCE -D_DARWIN_C_SOURCE)
extra_cflags=()
extra_ldflags=()
# Conventional whitespace-separated flags; CC is one executable, not shell code.
if [[ -n ${CFLAGS:-} ]]; then read -r -a extra_cflags <<< "$CFLAGS"; fi
if [[ -n ${LDFLAGS:-} ]]; then read -r -a extra_ldflags <<< "$LDFLAGS"; fi
includes=(-I"$REFERENCES/tree-sitter/lib/include" -I"$REFERENCES/tree-sitter/lib/src" -I"$REFERENCES/tree-sitter/lib/src/wasm")
echo "Compiling Tree-sitter runtime" >&2
"$CC" "${flags[@]}" "${extra_cflags[@]}" "${includes[@]}" \
  -c "$REFERENCES/tree-sitter/lib/src/lib.c" -o "$BUILD_DIR/runtime.o"
for language in "$@"; do
  grammar_dir="$REFERENCES/tree-sitter-$language/src"
  if [[ "$language" == typescript ]]; then grammar_dir="$REFERENCES/tree-sitter-typescript/typescript/src"; fi
  echo "Compiling Tree-sitter $language grammar" >&2
  "$CC" "${flags[@]}" "${extra_cflags[@]}" -I"$grammar_dir" \
    -c "$grammar_dir/parser.c" -o "$BUILD_DIR/$language-parser.o"
  objects=("$BUILD_DIR/runtime.o" "$BUILD_DIR/$language-parser.o")
  if [[ "$language" == typescript ]]; then
    "$CC" "${flags[@]}" "${extra_cflags[@]}" -I"$grammar_dir" \
      -c "$grammar_dir/scanner.c" -o "$BUILD_DIR/$language-scanner.o"
    objects+=("$BUILD_DIR/$language-scanner.o")
  fi
  "$CC" "${flags[@]}" "${extra_cflags[@]}" -Wall -Wextra -Wpedantic \
    "${includes[@]}" "-DLANG_FN=tree_sitter_$language" "-DLANGUAGE_NAME=\"$language\"" \
    -c "$ROOT/tree_sitter_adapter.c" -o "$BUILD_DIR/$language-adapter.o"
  "$CC" "${flags[@]}" "$BUILD_DIR/$language-adapter.o" \
    "${objects[@]}" "${extra_ldflags[@]}" -o "$OUTPUT_DIR/tree-sitter-$language"
  python3 "$ROOT/build_c_manifest.py" "$language" "$OUTPUT_DIR/tree-sitter-$language" "$CC" "${flags[@]}" "${extra_cflags[@]}" "${extra_ldflags[@]}"
  echo "Built $OUTPUT_DIR/tree-sitter-$language" >&2
done
