// Independent parse-only oracle; dependency resolution/type checking is not run.
import com.sun.source.util.JavacTask;
import java.nio.charset.StandardCharsets;
import java.util.List;
import javax.tools.Diagnostic;
import javax.tools.DiagnosticCollector;
import javax.tools.JavaCompiler;
import javax.tools.JavaFileObject;
import javax.tools.StandardJavaFileManager;
import javax.tools.ToolProvider;
public final class JavaParseOracle {
  public static void main(String[] args) throws Exception {
    if (args.length != 1) throw new IllegalArgumentException("one source path required");
    JavaCompiler compiler = ToolProvider.getSystemJavaCompiler();
    if (compiler == null) throw new IllegalStateException("JDK compiler unavailable");
    DiagnosticCollector<JavaFileObject> diagnostics = new DiagnosticCollector<>();
    try (StandardJavaFileManager fm = compiler.getStandardFileManager(diagnostics, null, StandardCharsets.UTF_8)) {
      JavacTask task = (JavacTask) compiler.getTask(null, fm, diagnostics,
          List.of("-proc:none", "-Xlint:none"), null, fm.getJavaFileObjects(args[0]));
      for (var ignored : task.parse()) { /* force all parse work, no attribution */ }
      long errors = diagnostics.getDiagnostics().stream().filter(d -> d.getKind() == Diagnostic.Kind.ERROR).count();
      System.out.println("{\"valid\":" + (errors == 0) + ",\"errors\":" + errors + ",\"version\":\"" + Runtime.version() + "\"}");
    }
  }
}
