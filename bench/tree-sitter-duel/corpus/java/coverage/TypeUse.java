import java.lang.annotation.*; import java.util.List; @Target(ElementType.TYPE_USE) @interface Marker {} class TypeUse { List<@Marker String> names; }
