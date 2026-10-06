record Point(int x, int y) {} class RecordPattern { int value(Object point) { return switch (point) { case Point(int x, int y) -> x + y; default -> 0; }; } }
