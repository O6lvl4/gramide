/*
 * Full-tree Tree-sitter benchmark adapter. This is deliberately a selected
 * declaration extractor, not a claim to implement a production symbol API.
 *
 * Build once per grammar with LANG_FN and LANGUAGE_NAME. All byte offsets and
 * TSPoint columns are UTF-8 byte offsets, not Unicode code-point counts.
 *
 * symbols emits lexical names and exact declaration-node ranges. In particular,
 * TypeScript export_statement/ambient_declaration envelopes and optional
 * declare-prefix/semicolon separators are EXCLUDED by the shared contract.
 * Method forms, function signatures/generators, abstract classes, and Java
 * compact constructors are normalized as documented in selected_kind().
 *
 * parse/warm measure parse + error inspection + full tree deletion. warm has
 * one additional untimed construction/deletion. setup_ns measures only primary
 * parser creation and grammar selection. Input loading, sample allocation,
 * warm-up, and any independent verification parser setup are excluded.
 *
 * edits measures ONLY ts_tree_edit + incremental parse + old-tree deletion.
 * Source application, coordinate scanning, validation, and output are untimed.
 * verify walks every node, anonymous tokens included, against a fresh tree.
 * Syntax-error intermediate states are reported, not rejected. A structural
 * mismatch makes verify exit 1; usage, I/O, bounds, and allocation errors exit 2.
 * TS_ADAPTER_FINAL_SOURCE, if set, receives the exact final edited bytes.
 */
#define _POSIX_C_SOURCE 200809L
#include <tree_sitter/api.h>

#include <errno.h>
#include <inttypes.h>
#include <limits.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <time.h>

#ifndef LANG_FN
#error "Compile with -DLANG_FN=tree_sitter_LANGUAGE"
#endif
#ifndef LANGUAGE_NAME
#error "Compile with -DLANGUAGE_NAME=\"LANGUAGE\""
#endif
extern const TSLanguage *LANG_FN(void);

typedef struct { char *data; uint32_t len; } Source;
typedef struct {
  const char *kind;
  uint32_t name_start, name_end, start, end;
} Symbol;
typedef struct {
  uint32_t start, old_end, insertion_len;
  char *insertion;
  size_t line;
} Edit;
typedef struct {
  const char *reason;
  uint64_t node_index;
  const char *incremental_type, *fresh_type;
  uint32_t incremental_start, incremental_end, fresh_start, fresh_end;
} Mismatch;
typedef struct {
  uint32_t new_end, bytes;
  bool has_error, fresh_has_error, matches_fresh;
  Mismatch mismatch;
} EditResult;

static _Noreturn void fail(const char *format, ...) {
  va_list args;
  fputs("tree-sitter adapter: ", stderr);
  va_start(args, format);
  vfprintf(stderr, format, args);
  va_end(args);
  fputc('\n', stderr);
  exit(2);
}

static void *allocate(size_t count, size_t size) {
  if (size && count > SIZE_MAX / size) fail("allocation size overflow");
  size_t bytes = count * size;
  void *p = malloc(bytes ? bytes : 1);
  if (!p) fail("could not allocate %zu bytes", bytes);
  return p;
}

static void *resize(void *p, size_t count, size_t size) {
  if (size && count > SIZE_MAX / size) fail("allocation size overflow");
  size_t bytes = count * size;
  void *result = realloc(p, bytes ? bytes : 1);
  if (!result) fail("could not allocate %zu bytes", bytes);
  return result;
}

static size_t grow_capacity(size_t previous) {
  if (!previous) return 32;
  if (previous > SIZE_MAX / 2) fail("array size overflow");
  return previous * 2;
}

static uint64_t now_ns(void) {
  struct timespec t;
  if (clock_gettime(CLOCK_MONOTONIC, &t))
    fail("clock_gettime: %s", strerror(errno));
  if (t.tv_sec < 0 || (uint64_t)t.tv_sec > UINT64_MAX / UINT64_C(1000000000))
    fail("monotonic clock out of range");
  return (uint64_t)t.tv_sec * UINT64_C(1000000000) + (uint64_t)t.tv_nsec;
}

static Source read_source(const char *path) {
  FILE *file = fopen(path, "rb");
  if (!file) fail("open '%s': %s", path, strerror(errno));
  size_t cap = 8192, len = 0;
  char *data = allocate(cap, 1);
  for (;;) {
    if (len == cap) {
      /* Reserve one trailing zero, although Tree-sitter receives an explicit length. */
      const uint64_t max_capacity = (uint64_t)UINT32_MAX + 1;
      uint64_t next = (uint64_t)cap * 2;
      if (next > max_capacity) next = max_capacity;
      if (next > SIZE_MAX || next <= cap) fail("input '%s' is too large", path);
      cap = (size_t)next;
      data = resize(data, cap, 1);
    }
    size_t n = fread(data + len, 1, cap - len, file);
    len += n;
    if (len > UINT32_MAX) fail("input '%s' exceeds Tree-sitter's 32-bit byte limit", path);
    if (!n) {
      if (ferror(file)) fail("read '%s': %s", path, strerror(errno));
      break;
    }
  }
  if (fclose(file)) fail("close '%s': %s", path, strerror(errno));
  if (len == SIZE_MAX) fail("input length overflow");
  if (len == cap) data = resize(data, len + 1, 1);
  data[len] = '\0';
  return (Source){data, (uint32_t)len};
}

static uint64_t parse_decimal(const char *text, const char *description) {
  if (!*text) fail("empty %s", description);
  uint64_t result = 0;
  for (const unsigned char *p = (const unsigned char *)text; *p; ++p) {
    if (*p < '0' || *p > '9') fail("invalid %s: '%s'", description, text);
    unsigned digit = (unsigned)(*p - '0');
    if (result > (UINT64_MAX - digit) / 10) fail("%s overflows: '%s'", description, text);
    result = result * 10 + digit;
  }
  return result;
}

static size_t parse_count(const char *text) {
  uint64_t n = parse_decimal(text, "iteration count");
  if (!n || n > SIZE_MAX / sizeof(uint64_t)) fail("iteration count out of range");
  return (size_t)n;
}

/* Valid UTF-8 stays lexical; an invalid byte is escaped instead of emitting
 * invalid JSON. Valid source names therefore round-trip without normalization. */
static size_t utf8_sequence_length(const unsigned char *p, size_t remaining) {
  if (p[0] < 0x80) return 1;
  size_t n;
  uint32_t value, minimum;
  if (p[0] >= 0xc2 && p[0] <= 0xdf) { n = 2; value = p[0] & 0x1f; minimum = 0x80; }
  else if (p[0] >= 0xe0 && p[0] <= 0xef) { n = 3; value = p[0] & 0x0f; minimum = 0x800; }
  else if (p[0] >= 0xf0 && p[0] <= 0xf4) { n = 4; value = p[0] & 7; minimum = 0x10000; }
  else return 0;
  if (remaining < n) return 0;
  for (size_t i = 1; i < n; ++i) {
    if ((p[i] & 0xc0) != 0x80) return 0;
    value = (value << 6) | (p[i] & 0x3f);
  }
  return value >= minimum && value <= 0x10ffff &&
    !(value >= 0xd800 && value <= 0xdfff) ? n : 0;
}

static void json_bytes(const char *data, size_t len) {
  putchar('"');
  for (size_t i = 0; i < len;) {
    unsigned char c = (unsigned char)data[i];
    if (c == '"' || c == '\\') { putchar('\\'); putchar(c); ++i; }
    else if (c < 0x20 || c == 0x7f) { printf("\\u%04x", (unsigned)c); ++i; }
    else if (c < 0x80) { putchar(c); ++i; }
    else {
      size_t n = utf8_sequence_length((const unsigned char *)data + i, len - i);
      if (n) { fwrite(data + i, 1, n, stdout); i += n; }
      else { printf("\\u%04x", (unsigned)c); ++i; }
    }
  }
  putchar('"');
}

static void json_string(const char *text) { json_bytes(text, strlen(text)); }
static const char *boolean(bool value) { return value ? "true" : "false"; }

static void finish_output(void) {
  putchar('\n');
  if (fflush(stdout) || ferror(stdout)) fail("writing standard output failed: %s", strerror(errno));
}

static TSParser *new_parser(void) {
  TSParser *parser = ts_parser_new();
  if (!parser) fail("could not allocate parser");
  const TSLanguage *language = LANG_FN();
  if (!language || !ts_parser_set_language(parser, language))
    fail("grammar '%s' has an incompatible Tree-sitter ABI", LANGUAGE_NAME);
  return parser;
}

static TSTree *parse_tree(TSParser *parser, const TSTree *old, Source source) {
  TSTree *tree = ts_parser_parse_string(parser, old, source.data, source.len);
  if (!tree) fail("Tree-sitter returned no tree");
  return tree;
}

static bool has_error(TSTree *tree) { return ts_node_has_error(ts_tree_root_node(tree)); }

static void require_valid(TSTree *tree, const char *path) {
  if (has_error(tree)) fail("'%s' contains syntax errors or missing nodes for %s", path, LANGUAGE_NAME);
}

static void print_samples(const uint64_t *samples, size_t count) {
  putchar('[');
  for (size_t i = 0; i < count; ++i) {
    if (i) putchar(',');
    printf("%" PRIu64, samples[i]);
  }
  putchar(']');
}

static int run_parse(const char *path, size_t count, bool warm) {
  Source source = read_source(path);
  uint64_t *samples = allocate(count, sizeof(*samples));
  uint64_t setup_start = now_ns();
  TSParser *parser = new_parser();
  uint64_t setup_ns = now_ns() - setup_start;
  if (warm) {
    TSTree *tree = parse_tree(parser, NULL, source);
    require_valid(tree, path);
    ts_tree_delete(tree);
  }
  for (size_t i = 0; i < count; ++i) {
    uint64_t start = now_ns();
    TSTree *tree = parse_tree(parser, NULL, source);
    bool error = has_error(tree);
    ts_tree_delete(tree);
    samples[i] = now_ns() - start;
    if (error) fail("'%s' contains syntax errors or missing nodes for %s (iteration %zu)", path, LANGUAGE_NAME, i);
  }
  printf("{\"language\":"); json_string(LANGUAGE_NAME);
  printf(",\"mode\":\"%s\",\"bytes\":%" PRIu32 ",\"count\":%zu,\"has_error\":false,\"setup_ns\":%" PRIu64 ",\"samples_ns\":",
         warm ? "warm" : "parse", source.len, count, setup_ns);
  print_samples(samples, count);
  putchar('}');
  finish_output();
  free(samples);
  ts_parser_delete(parser);
  free(source.data);
  return 0;
}

static bool is_kind(const char *actual, const char *expected) { return strcmp(actual, expected) == 0; }

static const char *selected_kind(const char *type) {
  if (is_kind(LANGUAGE_NAME, "json")) return is_kind(type, "pair") ? "pair" : NULL;
  if (is_kind(type, "class_declaration") || is_kind(type, "interface_declaration") ||
      is_kind(type, "enum_declaration")) return type;
  if (is_kind(LANGUAGE_NAME, "java")) {
    if (is_kind(type, "record_declaration") || is_kind(type, "method_declaration") ||
        is_kind(type, "constructor_declaration")) return type;
    if (is_kind(type, "compact_constructor_declaration")) return "constructor_declaration";
  } else if (is_kind(LANGUAGE_NAME, "typescript")) {
    if (is_kind(type, "function_declaration") || is_kind(type, "type_alias_declaration")) return type;
    if (is_kind(type, "function_signature") || is_kind(type, "generator_function_declaration")) return "function_declaration";
    if (is_kind(type, "abstract_class_declaration")) return "class_declaration";
    if (is_kind(type, "method_definition") || is_kind(type, "method_signature") ||
        is_kind(type, "abstract_method_signature")) return "method_declaration";
  }
  return NULL;
}

/* Iterative recursive-order traversal avoids an adapter C-stack limit. */
static bool cursor_next(TSTreeCursor *cursor) {
  if (ts_tree_cursor_goto_first_child(cursor)) return true;
  do {
    if (ts_tree_cursor_goto_next_sibling(cursor)) return true;
  } while (ts_tree_cursor_goto_parent(cursor));
  return false;
}

static bool blank_byte(unsigned char b) { return b==' ' || b=='\t' || b=='\n' || b=='\r'; }
/* Match the documented declaration-core contract on both adapters. */
static uint32_t declaration_start(Source source,uint32_t start,uint32_t end,const char *kind) {
  uint32_t at=start;
  if (!strcmp(LANGUAGE_NAME,"typescript") && strcmp(kind,"method_declaration") && end-start>7 &&
      !memcmp(source.data+start,"declare",7) && (blank_byte(source.data[start+7]) || source.data[start+7]=='/')) {
    at=start+7;
    while(at<end) {
      if(blank_byte(source.data[at])) {++at;continue;}
      if(at+1<end && source.data[at]=='/' && source.data[at+1]=='*') {
        at+=2;while(at+1<end && !(source.data[at]=='*' && source.data[at+1]=='/')) ++at;
        at+=2;continue;
      }
      if(at+1<end && source.data[at]=='/' && source.data[at+1]=='/') {
        while(at<end && source.data[at]!='\n') ++at;
        continue;
      }
      break;
    }
  }
  return at;
}
static uint32_t declaration_end(Source source,uint32_t start,uint32_t end) {
  if(!strcmp(LANGUAGE_NAME,"typescript") && end>start && source.data[end-1]==';') {
    --end;while(end>start && blank_byte(source.data[end-1])) --end;
  }
  return end;
}

static int run_symbols(const char *path) {
  Source source = read_source(path);
  TSParser *parser = new_parser();
  TSTree *tree = parse_tree(parser, NULL, source);
  require_valid(tree, path);
  Symbol *symbols = NULL;
  size_t count = 0, capacity = 0;
  TSTreeCursor cursor = ts_tree_cursor_new(ts_tree_root_node(tree));
  do {
    TSNode node = ts_tree_cursor_current_node(&cursor);
    const char *kind = selected_kind(ts_node_type(node));
    if (!kind) continue;
    const char *field = is_kind(LANGUAGE_NAME, "json") ? "key" : "name";
    TSNode name = ts_node_child_by_field_name(node, field, (uint32_t)strlen(field));
    if (ts_node_is_null(name)) fail("selected %s node has no %s field", kind, field);
    Symbol symbol = {kind, ts_node_start_byte(name), ts_node_end_byte(name),
                     ts_node_start_byte(node), ts_node_end_byte(node)};
    symbol.start=declaration_start(source,symbol.start,symbol.end,kind);
    symbol.end=declaration_end(source,symbol.start,symbol.end);
    if (symbol.name_start > symbol.name_end || symbol.name_end > source.len ||
        symbol.start > symbol.end || symbol.end > source.len)
      fail("selected node has invalid source bounds");
    if (count == capacity) {
      capacity = grow_capacity(capacity);
      symbols = resize(symbols, capacity, sizeof(*symbols));
    }
    symbols[count++] = symbol;
  } while (cursor_next(&cursor));
  ts_tree_cursor_delete(&cursor);
  putchar('[');
  for (size_t i = 0; i < count; ++i) {
    Symbol s = symbols[i];
    if (i) putchar(',');
    fputs("{\"kind\":", stdout); json_string(s.kind);
    fputs(",\"name\":", stdout); json_bytes(source.data + s.name_start, s.name_end - s.name_start);
    printf(",\"start_byte\":%" PRIu32 ",\"end_byte\":%" PRIu32 "}", s.start, s.end);
  }
  putchar(']');
  finish_output();
  free(symbols);
  ts_tree_delete(tree);
  ts_parser_delete(parser);
  free(source.data);
  return 0;
}

static unsigned hex_digit(char c, size_t line) {
  if (c >= '0' && c <= '9') return (unsigned)(c - '0');
  if (c >= 'a' && c <= 'f') return (unsigned)(c - 'a') + 10;
  if (c >= 'A' && c <= 'F') return (unsigned)(c - 'A') + 10;
  fail("invalid insertion hex at script line %zu", line);
  return 0;
}

static Edit *read_edits(const char *path, size_t *count) {
  FILE *file = fopen(path, "rb");
  if (!file) fail("open edit script '%s': %s", path, strerror(errno));
  Edit *edits = NULL;
  size_t capacity = 0, line_capacity = 0, line_number = 0;
  char *line = NULL;
  ssize_t length;
  *count = 0;
  while ((length = getline(&line, &line_capacity, file)) >= 0) {
    ++line_number;
    size_t len = (size_t)length;
    if (memchr(line, '\0', len)) fail("NUL byte at script line %zu", line_number);
    if (len && line[len - 1] == '\n') --len;
    if (len && line[len - 1] == '\r') --len;
    line[len] = '\0';
    if (!len || line[0] == '#') continue;
    char *second = strchr(line, '\t');
    if (!second) fail("script line %zu needs three tab-separated fields", line_number);
    *second++ = '\0';
    char *third = strchr(second, '\t');
    if (!third) fail("script line %zu needs three tab-separated fields", line_number);
    *third++ = '\0';
    if (strchr(third, '\t')) fail("extra field at script line %zu", line_number);
    uint64_t start = parse_decimal(line, "edit start"), old_end = parse_decimal(second, "edit old_end");
    if (start > UINT32_MAX || old_end > UINT32_MAX || start > old_end)
      fail("invalid edit bounds at script line %zu", line_number);
    size_t hex_length = strlen(third);
    if (!hex_length) fail("empty insertion at script line %zu; use '-'", line_number);
    bool empty = is_kind(third, "-");
    if (!empty && ((hex_length & 1) || hex_length / 2 > UINT32_MAX))
      fail("invalid insertion hex length at script line %zu", line_number);
    uint32_t insertion_len = empty ? 0 : (uint32_t)(hex_length / 2);
    char *insertion = allocate(insertion_len, 1);
    for (uint32_t i = 0; i < insertion_len; ++i)
      insertion[i] = (char)((hex_digit(third[(size_t)i * 2], line_number) << 4) |
                           hex_digit(third[(size_t)i * 2 + 1], line_number));
    if (*count == capacity) {
      capacity = grow_capacity(capacity);
      edits = resize(edits, capacity, sizeof(*edits));
    }
    edits[(*count)++] = (Edit){(uint32_t)start, (uint32_t)old_end, insertion_len, insertion, line_number};
  }
  if (ferror(file) || !feof(file)) fail("read edit script '%s': %s", path, strerror(errno));
  free(line);
  if (fclose(file)) fail("close edit script '%s': %s", path, strerror(errno));
  return edits;
}

static TSPoint advance_point(TSPoint point, const char *data, uint32_t length) {
  for (uint32_t i = 0; i < length; ++i) {
    if (data[i] == '\n') {
      if (point.row == UINT32_MAX) fail("edit row coordinate overflow");
      ++point.row;
      point.column = 0;
    } else {
      if (point.column == UINT32_MAX) fail("edit column coordinate overflow");
      ++point.column;
    }
  }
  return point;
}

static TSInputEdit apply_edit(Source *source, const Edit *edit) {
  if (edit->start > edit->old_end || edit->old_end > source->len)
    fail("script line %zu is out of bounds for current source (%" PRIu32 " bytes)", edit->line, source->len);
  uint64_t new_length = (uint64_t)source->len - (edit->old_end - edit->start) + edit->insertion_len;
  if (new_length > UINT32_MAX || new_length >= SIZE_MAX)
    fail("script line %zu would exceed the source length limit", edit->line);
  TSPoint start_point = advance_point((TSPoint){0, 0}, source->data, edit->start);
  TSPoint old_end_point = advance_point(start_point, source->data + edit->start, edit->old_end - edit->start);
  TSPoint new_end_point = advance_point(start_point, edit->insertion, edit->insertion_len);
  uint32_t new_end = edit->start + edit->insertion_len;
  char *data = allocate((size_t)new_length + 1, 1);
  memcpy(data, source->data, edit->start);
  memcpy(data + edit->start, edit->insertion, edit->insertion_len);
  memcpy(data + new_end, source->data + edit->old_end, source->len - edit->old_end);
  data[new_length] = '\0';
  free(source->data);
  source->data = data;
  source->len = (uint32_t)new_length;
  return (TSInputEdit){edit->start, edit->old_end, new_end, start_point, old_end_point, new_end_point};
}

static bool equal_point(TSPoint a, TSPoint b) { return a.row == b.row && a.column == b.column; }
static bool equal_nullable_string(const char *a, const char *b) {
  return a && b ? strcmp(a, b) == 0 : a == b;
}

/* A complete recursive structural comparison implemented as cursor DFS.
 * Unlike s-expressions this checks byte ranges, points, fields, anonymous nodes,
 * missing/error state, extra nodes, and child counts at every depth. */
static bool trees_equal(TSTree *incremental, TSTree *fresh, Mismatch *mismatch) {
  TSTreeCursor a = ts_tree_cursor_new(ts_tree_root_node(incremental));
  TSTreeCursor b = ts_tree_cursor_new(ts_tree_root_node(fresh));
  uint64_t index = 0;
  bool equal = true;
  for (;;) {
    TSNode an = ts_tree_cursor_current_node(&a), bn = ts_tree_cursor_current_node(&b);
    const char *reason = NULL;
    if (strcmp(ts_node_type(an), ts_node_type(bn))) reason = "type";
    else if (!equal_nullable_string(ts_tree_cursor_current_field_name(&a), ts_tree_cursor_current_field_name(&b))) reason = "field";
    else if (ts_node_is_named(an) != ts_node_is_named(bn)) reason = "named";
    else if (ts_node_is_missing(an) != ts_node_is_missing(bn)) reason = "missing";
    else if (ts_node_is_error(an) != ts_node_is_error(bn)) reason = "error";
    else if (ts_node_has_error(an) != ts_node_has_error(bn)) reason = "has_error";
    else if (ts_node_is_extra(an) != ts_node_is_extra(bn)) reason = "extra";
    else if (ts_node_start_byte(an) != ts_node_start_byte(bn)) reason = "start_byte";
    else if (ts_node_end_byte(an) != ts_node_end_byte(bn)) reason = "end_byte";
    else if (!equal_point(ts_node_start_point(an), ts_node_start_point(bn))) reason = "start_point";
    else if (!equal_point(ts_node_end_point(an), ts_node_end_point(bn))) reason = "end_point";
    else if (ts_node_child_count(an) != ts_node_child_count(bn)) reason = "child_count";
    if (reason) {
      *mismatch = (Mismatch){reason, index, ts_node_type(an), ts_node_type(bn),
                            ts_node_start_byte(an), ts_node_end_byte(an),
                            ts_node_start_byte(bn), ts_node_end_byte(bn)};
      equal = false;
      break;
    }
    bool more_a = cursor_next(&a), more_b = cursor_next(&b);
    if (more_a != more_b) {
      *mismatch = (Mismatch){"tree_shape", index, ts_node_type(an), ts_node_type(bn),
                            ts_node_start_byte(an), ts_node_end_byte(an),
                            ts_node_start_byte(bn), ts_node_end_byte(bn)};
      equal = false;
      break;
    }
    if (!more_a) break;
    ++index;
  }
  ts_tree_cursor_delete(&a);
  ts_tree_cursor_delete(&b);
  return equal;
}

static uint64_t source_hash(Source source) {
  uint64_t hash = UINT64_C(14695981039346656037);
  for (uint32_t i = 0; i < source.len; ++i) {
    hash ^= (unsigned char)source.data[i];
    hash *= UINT64_C(1099511628211);
  }
  return hash;
}

static void write_final_source(Source source) {
  const char *path = getenv("TS_ADAPTER_FINAL_SOURCE");
  if (!path) return;
  if (!*path) fail("TS_ADAPTER_FINAL_SOURCE is empty");
  FILE *file = fopen(path, "wb");
  if (!file) fail("open final-source output '%s': %s", path, strerror(errno));
  if (fwrite(source.data, 1, source.len, file) != source.len)
    fail("write final-source output '%s': %s", path, strerror(errno));
  if (fclose(file)) fail("close final-source output '%s': %s", path, strerror(errno));
}

static void print_mismatch(const Mismatch *m) {
  fputs("{\"reason\":", stdout); json_string(m->reason);
  printf(",\"node_index\":%" PRIu64 ",\"incremental\":{\"type\":", m->node_index);
  json_string(m->incremental_type);
  printf(",\"start_byte\":%" PRIu32 ",\"end_byte\":%" PRIu32 "},\"fresh\":{\"type\":", m->incremental_start, m->incremental_end);
  json_string(m->fresh_type);
  printf(",\"start_byte\":%" PRIu32 ",\"end_byte\":%" PRIu32 "}}", m->fresh_start, m->fresh_end);
}

static int run_edits(const char *path, const char *script, bool verify) {
  Source source = read_source(path);
  size_t count;
  Edit *edits = read_edits(script, &count);
  EditResult *results = allocate(count, sizeof(*results));
  uint64_t *samples = allocate(count, sizeof(*samples));
  uint64_t setup_start = now_ns();
  TSParser *parser = new_parser();
  uint64_t setup_ns = now_ns() - setup_start;
  TSParser *fresh_parser = verify ? new_parser() : NULL;
  TSTree *tree = parse_tree(parser, NULL, source);
  bool initial_error = has_error(tree);
  uint32_t initial_bytes = source.len;
  size_t error_count = 0, mismatch_count = 0;
  for (size_t i = 0; i < count; ++i) {
    TSInputEdit input_edit = apply_edit(&source, &edits[i]);
    uint64_t start = now_ns();
    ts_tree_edit(tree, &input_edit);
    TSTree *next = parse_tree(parser, tree, source);
    ts_tree_delete(tree);
    samples[i] = now_ns() - start;
    tree = next;
    EditResult result = {0};
    result.new_end = input_edit.new_end_byte;
    result.bytes = source.len;
    result.has_error = has_error(tree);
    if (result.has_error) ++error_count;
    if (verify) {
      TSTree *fresh = parse_tree(fresh_parser, NULL, source);
      result.fresh_has_error = has_error(fresh);
      result.matches_fresh = trees_equal(tree, fresh, &result.mismatch);
      if (!result.matches_fresh) ++mismatch_count;
      ts_tree_delete(fresh);
    }
    results[i] = result;
  }
  write_final_source(source);
  fputs("{\"language\":", stdout); json_string(LANGUAGE_NAME);
  printf(",\"mode\":\"%s\",\"initial_bytes\":%" PRIu32 ",\"initial_has_error\":%s,\"edit_count\":%zu,\"error_edits\":%zu,\"mismatch_count\":",
         verify ? "verify" : "timed", initial_bytes, boolean(initial_error), count, error_count);
  if (verify) printf("%zu", mismatch_count); else fputs("null", stdout);
  printf(",\"verified\":%s,\"setup_ns\":%" PRIu64 ",\"samples_ns\":", boolean(verify), setup_ns);
  print_samples(samples, count);
  fputs(",\"per_edit\":[", stdout);
  for (size_t i = 0; i < count; ++i) {
    EditResult r = results[i];
    if (i) putchar(',');
    printf("{\"index\":%zu,\"script_line\":%zu,\"start_byte\":%" PRIu32 ",\"old_end_byte\":%" PRIu32 ",\"new_end_byte\":%" PRIu32 ",\"bytes\":%" PRIu32 ",\"has_error\":%s,\"fresh_has_error\":",
           i, edits[i].line, edits[i].start, edits[i].old_end, r.new_end, r.bytes, boolean(r.has_error));
    fputs(verify ? boolean(r.fresh_has_error) : "null", stdout);
    fputs(",\"matches_fresh\":", stdout);
    fputs(verify ? boolean(r.matches_fresh) : "null", stdout);
    fputs(",\"mismatch\":", stdout);
    if (verify && !r.matches_fresh) print_mismatch(&r.mismatch); else fputs("null", stdout);
    putchar('}');
  }
  printf("],\"final_bytes\":%" PRIu32 ",\"final_source_fnv1a64\":\"%016" PRIx64 "\"}", source.len, source_hash(source));
  finish_output();
  for (size_t i = 0; i < count; ++i) free(edits[i].insertion);
  free(edits);
  free(results);
  free(samples);
  free(source.data);
  ts_tree_delete(tree);
  if (fresh_parser) ts_parser_delete(fresh_parser);
  ts_parser_delete(parser);
  return mismatch_count ? 1 : 0;
}

static _Noreturn void usage(const char *program) {
  fprintf(stderr, "Usage:\n  %s parse %s PATH [COUNT]\n  %s warm %s PATH COUNT\n  %s symbols %s PATH\n  %s edits %s PATH SCRIPT_PATH [verify|timed]\n",
          program, LANGUAGE_NAME, program, LANGUAGE_NAME,
          program, LANGUAGE_NAME, program, LANGUAGE_NAME);
  exit(2);
}

int main(int argc, char **argv) {
  if (argc < 4) usage(argv[0]);
  if (strcmp(argv[2], LANGUAGE_NAME))
    fail("this binary supports '%s', not '%s'", LANGUAGE_NAME, argv[2]);
  if (is_kind(argv[1], "parse")) {
    if (argc != 4 && argc != 5) usage(argv[0]);
    return run_parse(argv[3], argc == 5 ? parse_count(argv[4]) : 1, false);
  }
  if (is_kind(argv[1], "warm")) {
    if (argc != 5) usage(argv[0]);
    return run_parse(argv[3], parse_count(argv[4]), true);
  }
  if (is_kind(argv[1], "symbols")) {
    if (argc != 4) usage(argv[0]);
    return run_symbols(argv[3]);
  }
  if (is_kind(argv[1], "edits")) {
    if (argc != 5 && argc != 6) usage(argv[0]);
    bool verify = argc == 5 || is_kind(argv[5], "verify");
    if (argc == 6 && !verify && !is_kind(argv[5], "timed")) usage(argv[0]);
    return run_edits(argv[3], argv[4], verify);
  }
  usage(argv[0]);
  return 2;
}
