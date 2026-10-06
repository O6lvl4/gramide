class Outer<T> { class Inner<U> {} } class QualifiedInner { Outer<String>.Inner<Integer> build(Outer<String> outer) { return outer.new Inner<Integer>(); } }
