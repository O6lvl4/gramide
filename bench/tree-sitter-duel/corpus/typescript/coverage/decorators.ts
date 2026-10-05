function logged(value: Function, context: ClassMethodDecoratorContext) { return value; } class Service { @logged run() {} }
