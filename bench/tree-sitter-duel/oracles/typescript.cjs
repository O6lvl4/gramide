// Parse-only independent oracle. No type checking or code execution.
const fs = require('node:fs');
const ts = require(process.env.TYPESCRIPT_ORACLE || 'typescript');
const path = process.argv[2];
const text = fs.readFileSync(path, 'utf8');
const sf = ts.createSourceFile(path, text, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
const ds = sf.parseDiagnostics.map(d => ({start: d.start, length: d.length, message: ts.flattenDiagnosticMessageText(d.messageText, '\n')}));
console.log(JSON.stringify({valid: ds.length === 0, version: ts.version, diagnostics: ds}));
