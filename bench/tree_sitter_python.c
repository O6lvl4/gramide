// Full parse + declaration ranges. No old tree, queries or incremental reuse.
#include <tree_sitter/api.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
extern const TSLanguage *tree_sitter_python(void);
static const char *source;
static int comma;
static int is(TSNode n, const char *kind) { return !strcmp(ts_node_type(n), kind); }
static void json_string(const char *s) {
  putchar('"');
  for (; *s; s++) {
    unsigned char c = (unsigned char)*s;
    if (c == '"' || c == '\\') printf("\\%c", c);
    else if (c < 32) printf("\\u%04x", c);
    else putchar(c);
  }
  putchar('"');
}
static char *text(TSNode n) {
  uint32_t start = ts_node_start_byte(n), length = ts_node_end_byte(n) - start;
  char *out = malloc((size_t)length + 1);
  if (!out) exit(2);
  memcpy(out, source + start, length); out[length] = 0; return out;
}
static char *join(const char *prefix, const char *name) {
  size_t a = strlen(prefix), b = strlen(name);
  char *out = malloc(a + b + 2); if (!out) exit(2);
  memcpy(out, prefix, a); if (a) out[a++] = '.';
  memcpy(out+a, name, b+1); return out;
}
// Comments are extras in tree-sitter, not part of the CPython declaration end.
static TSNode last_code(TSNode n) {
  uint32_t count = ts_node_child_count(n);
  while (count) {
    TSNode child = ts_node_child(n, --count);
    if (!is(child, "comment")) return last_code(child);
  }
  return n;
}
static TSNode first_identifier(TSNode n) {
  if (is(n, "identifier")) return n;
  for (uint32_t i = 0; i < ts_node_named_child_count(n); i++) {
    TSNode found = first_identifier(ts_node_named_child(n, i));
    if (!ts_node_is_null(found)) return found;
  }
  return (TSNode){0};
}
static void walk(TSNode n, const char *prefix, int class_owner) {
  if (is(n, "decorated_definition")) {
    TSNode definition = ts_node_child_by_field_name(n, "definition", 10);
    // Handle the envelope below without visiting decorators as declarations.
    if (ts_node_is_null(definition)) exit(2);
  }
  TSNode decl = is(n, "decorated_definition") ? ts_node_child_by_field_name(n, "definition", 10) : n;
  int function = is(decl, "function_definition"), cls = is(decl, "class_definition"), alias = is(decl, "type_alias_statement");
  if (function || cls || alias) {
    TSNode name_node = alias ? first_identifier(ts_node_child_by_field_name(decl,"left",4)) : ts_node_child_by_field_name(decl,"name",4);
    if (ts_node_is_null(name_node)) exit(2);
    char *name = text(name_node), *qualified = join(prefix, name);
    TSNode end = last_code(decl);
    printf("%s{\"name\":", comma ? ",\n" : ""); json_string(qualified);
    printf(",\"kind\":"); json_string(function ? (class_owner ? "method" : "function") : cls ? "class" : "type");
    printf(",\"owner\":"); json_string(function && class_owner ? prefix : "");
    printf(",\"start\":%u,\"end\":%u,\"start_byte\":%u,\"end_byte\":%u}",
      ts_node_start_point(n).row+1, ts_node_end_point(end).row+1, ts_node_start_byte(n), ts_node_end_byte(end));
    comma = 1;
    if (function || cls) walk(ts_node_child_by_field_name(decl,"body",4),qualified,cls);
    free(name);free(qualified);return;
  }
  for (uint32_t i=0; i<ts_node_named_child_count(n); i++) walk(ts_node_named_child(n,i),prefix,class_owner);
}
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  FILE *file = fopen(argv[1],"rb");
  if (!file || fseek(file,0,SEEK_END)) return 2;
  long size = ftell(file);
  if (size < 0 || (unsigned long)size > UINT32_MAX || fseek(file,0,SEEK_SET)) return 2;
  char *buffer = malloc((size_t)size+1);
  if (!buffer || fread(buffer,1,(size_t)size,file)!=(size_t)size) return 2;
  fclose(file); buffer[size]=0; source=buffer;
  TSParser *parser=ts_parser_new();
  if (!parser || !ts_parser_set_language(parser,tree_sitter_python())) return 2;
  TSTree *tree=ts_parser_parse_string(parser,NULL,buffer,(uint32_t)size);
  if (!tree || ts_node_has_error(ts_tree_root_node(tree))) return 1;
  puts("["); walk(ts_tree_root_node(tree),"",0); puts("\n]");
  ts_tree_delete(tree);ts_parser_delete(parser);free(buffer);return 0;
}
