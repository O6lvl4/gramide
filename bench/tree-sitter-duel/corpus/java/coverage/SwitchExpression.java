class SwitchExpression { int value(int x) { return switch (x) { case 0 -> 1; case 1 -> { yield 2; } default -> 3; }; } }
