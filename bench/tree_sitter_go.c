// Independent full-parse/range baseline. No incremental tree is reused.
#include <tree_sitter/api.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
extern const TSLanguage *tree_sitter_go(void);

int main(int argc, char **argv) {
  if (argc != 2) return 2;
  FILE *file = fopen(argv[1], "rb");
  if (!file || fseek(file, 0, SEEK_END)) return 2;
  long size = ftell(file);
  if (size < 0 || (unsigned long)size > UINT32_MAX || fseek(file, 0, SEEK_SET)) return 2;
  char *source = malloc((size_t)size + 1);
  if (!source || fread(source, 1, (size_t)size, file) != (size_t)size) return 2;
  fclose(file);
  source[size] = 0;
  TSParser *parser = ts_parser_new();
  if (!parser || !ts_parser_set_language(parser, tree_sitter_go())) return 2;
  TSTree *tree = ts_parser_parse_string(parser, NULL, source, (uint32_t)size);
  if (!tree || ts_node_has_error(ts_tree_root_node(tree))) return 1;
  TSTreeCursor cursor = ts_tree_cursor_new(ts_tree_root_node(tree));
  int comma = 0;
  puts("[");
  for (;;) {
    TSNode node = ts_tree_cursor_current_node(&cursor);
    const char *kind = ts_node_type(node);
    if (!strcmp(kind, "function_declaration") || !strcmp(kind, "method_declaration")) {
      TSNode name = ts_node_child_by_field_name(node, "name", 4);
      uint32_t start = ts_node_start_byte(name), end = ts_node_end_byte(name);
      // Go identifiers cannot contain JSON quotation or control characters.
      printf("%s{\"name\":\"%.*s\",\"start\":%u,\"end\":%u,\"start_byte\":%u,\"end_byte\":%u}",
        comma ? ",\n" : "", (int)(end-start), source+start,
        ts_node_start_point(node).row+1, ts_node_end_point(node).row+1,
        ts_node_start_byte(node), ts_node_end_byte(node));
      comma = 1;
    }
    if (ts_tree_cursor_goto_first_child(&cursor)) continue;
    while (!ts_tree_cursor_goto_next_sibling(&cursor)) {
      if (!ts_tree_cursor_goto_parent(&cursor)) goto done;
    }
  }
done:
  puts("\n]");
  ts_tree_cursor_delete(&cursor);
  ts_tree_delete(tree);
  ts_parser_delete(parser);
  free(source);
  return 0;
}
