#!/usr/bin/env python3
"""Prepare or verify frozen parse-only inputs; never execute a tested parser.

Default: materialize the selected sources, generated probes, controls and manifest.
--verify: read hashes only; usable without the original source installations.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "corpus"
WORKSPACE = ROOT.parent
TS = Path(os.environ.get("TYPESCRIPT_ORACLE", str(ROOT / "node_modules/typescript")))
FROZEN_AT = "2026-10-05T13:26:00Z"
TS_INTEGRITY = "sha512-jl1vZzPDinLr9eUt3J/t7V6FgNEw9QjvBPdysz9KfQDD41fQrC2Y4vKQdiaUpFT4bXlb1RHhLpp8wtm6M5TgSw=="
ENTRIES = []
LICENSES = {}


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write(relative, data):
    if isinstance(data, str):
        data = data.encode("utf-8")
    target = CORPUS / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return data


def json_write(relative, obj):
    write(relative, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def git_bytes(repo, path):
    """Read the pinned committed blob, not a potentially edited worktree file."""
    head = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
    data = subprocess.check_output(["git", "-C", str(repo), "show", f"{head}:{path}"])
    blob = subprocess.check_output(["git", "-C", str(repo), "rev-parse", f"{head}:{path}"], text=True).strip()
    return data, head, blob


def license_file(name, data, spdx, origin_url):
    path = "licenses/" + name
    write(path, data)
    LICENSES[name] = {"path": path, "spdx": spdx,
                      "sha256": sha256(data), "origin_url": origin_url}
    return path


def add(language, name, data, *, category, split, features, origin,
        licenses, expected_syntax="valid", grammar_variant=None, **extra):
    path = f"{language}/{category}/{name}"
    data = write(path, data)
    entry = {
        "id": f"{language}/{category}/{name}", "language": language,
        "grammar_variant": grammar_variant or language,
        "path": path, "category": {"scaling": "generated", "coverage": "coverage_probe"}.get(category, category), "purpose": category, "split": split,
        "expected_syntax": expected_syntax, "expected_valid": expected_syntax == "valid", "oracle_validation": "not_run_during_preparation",
        "bytes": len(data), "lines": data.count(b"\n") + bool(data and not data.endswith(b"\n")),
        "size_band": "small" if len(data) < 4096 else "medium" if len(data) < 32768 else "large",
        "sha256": sha256(data), "features": features, "origin": origin,
        "license_paths": licenses, "license_path": licenses[0],
        "source_url": origin.get("url") or origin.get("upstream", {}).get("url"),
        "headline_group": "real" if category == "real" else "separate_" + category,
        **extra,
    }
    ENTRIES.append(entry)
    return entry


def upstream_cached(language, basename, split, features, license_path):
    obj = json.loads((CORPUS / "upstream-cache" / f"{language}--{basename}.response.json").read_text())
    assert obj["encoding"] == "utf-8"
    data = obj["content"].encode("utf-8")
    git_hash = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    assert git_hash == obj["sha"], (basename, "Git blob identity mismatch")
    return add(language, basename, data, category="real", split=split, features=features,
               licenses=[license_path], origin={
                   "kind": "official_github_source", "repository": obj["repo"],
                   "revision": obj["ref"], "source_path": obj["path"],
                   "url": f"https://github.com/{obj['repo']}/blob/{obj['ref']}/{obj['path']}",
                   "git_blob_sha1": obj["sha"], "upstream_sha256": sha256(data),
                   "retrieval": "GitHub connector; UTF-8 bytes independently matched to Git blob SHA-1",
               })


def generated(language, name, source, features, *, split="development", expected="valid", **extra):
    return add(language, name, source, category="coverage", split=split, features=features,
               licenses=["licenses/GENERATED-MIT.txt"], expected_syntax=expected,
               origin={"kind": "original_generated_fixture", "generator": "corpus_prepare.py",
                       "version": 1}, **extra)


def malformed_from(entry, operation, reason):
    source = (CORPUS / entry["path"]).read_bytes()
    at = len(source.rstrip()) - 1
    assert source[at:at+1] == b"}", entry["id"]
    edited = source[:at] + source[at+1:]
    name = Path(entry["path"]).name
    stem, ext = name.rsplit(".", 1)
    return add(entry["language"], f"{stem}.{operation}.{ext}", edited,
               category="malformed", split=entry["split"], features=[operation],
               licenses=entry["license_paths"], expected_syntax="invalid",
               origin={"kind": "controlled_edit", "parent_id": entry["id"],
                       "parent_sha256": entry["sha256"], "upstream": entry["origin"]},
               mutation={"operation": operation, "byte_offset": at,
                         "removed_hex": "7d", "inserted_hex": "", "rationale": reason},
               validation_scope="Syntax-only negative control; not a semantic/type-checking claim")


def prepare():
    pins = json.loads((CORPUS / "upstream-cache/pins.json").read_text())
    selection = json.loads((CORPUS / "selection.json").read_text())
    assert pins == selection["pins"]
    gson_license = json.loads((CORPUS / "upstream-cache/gson-license.response.json").read_text())
    gson_lic = license_file("gson-APACHE-2.0.txt", gson_license["content"].encode(), "Apache-2.0",
                           f"https://github.com/google/gson/blob/{pins['gson']}/LICENSE")
    assert json.loads((TS / "package.json").read_text())["version"] == "5.9.3"
    ts_lic = license_file("typescript-APACHE-2.0.txt", (TS / "LICENSE.txt").read_bytes(), "Apache-2.0",
                         f"https://github.com/microsoft/TypeScript/blob/{pins['typescript']}/LICENSE.txt")
    ts_notice = license_file("typescript-ThirdPartyNoticeText.txt", (TS / "ThirdPartyNoticeText.txt").read_bytes(),
                            "LicenseRef-TypeScript-ThirdParty-Notices",
                            f"https://github.com/microsoft/TypeScript/blob/{pins['typescript']}/ThirdPartyNoticeText.txt")
    license_file("GENERATED-MIT.txt", b"""MIT License

Copyright (c) 2026 gramide benchmark contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the \"Software\"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
""", "MIT", "original benchmark fixtures; no third-party source copied")

    java_roles = [
        ("JsonNull.java", "development", ["small_value_class", "overrides", "instanceof"]),
        ("Strictness.java", "heldout", ["enum", "documentation_comments"]),
        ("ExclusionStrategy.java", "development", ["public_interface", "wildcard_generic"]),
        ("JsonParser.java", "heldout", ["static_methods", "try_catch", "throws"]),
        ("JsonElement.java", "development", ["abstract_class", "annotations", "method_calls"]),
        ("JsonPrimitive.java", "heldout", ["numeric_literals", "casts", "boolean_expressions"]),
        ("LinkedTreeMap.java", "development", ["nested_classes", "generics", "loops", "collections"]),
        ("JsonReader.java", "heldout", ["large_implementation", "switch_statements", "character_escapes"]),
    ]
    for name, split, features in java_roles:
        upstream_cached("java", name, split, features, gson_lic)
    for name, split, features in [
        ("corePublic.ts", "development", ["interfaces", "generic_types", "const_enum"]),
        ("performance.ts", "heldout", ["runtime_implementation", "optional_chaining", "nullish_coalescing"]),
        ("watchUtilities.ts", "development", ["runtime_implementation", "callbacks", "generics"]),
        ("core.ts", "heldout", ["large_runtime_implementation", "overloads", "type_predicates"]),
    ]:
        upstream_cached("typescript", name, split, features, ts_lic)

    def npm_source(language, source_path, split, features):
        data = (TS / source_path).read_bytes()
        return add(language, source_path.replace("/", "__"), data, category="real", split=split,
                   features=features, licenses=[ts_lic, ts_notice], origin={
                       "kind": "installed_official_npm_package", "package": "typescript", "version": "5.9.3",
                       "source_path": source_path, "revision": pins["typescript"],
                       "url": "https://www.npmjs.com/package/typescript/v/5.9.3",
                       "tarball_url": "https://registry.npmjs.org/typescript/-/typescript-5.9.3.tgz",
                       "package_integrity_from_pnpm_lock": TS_INTEGRITY,
                       "integrity_verification": "Package tarball not re-downloaded; installed source bytes SHA-256 frozen",
                       "upstream_sha256": sha256(data),
                   })

    for path, split, features in [
        ("lib/lib.es2015.symbol.d.ts", "development", ["declarations", "symbol", "small_standard_library"]),
        ("lib/lib.es2021.promise.d.ts", "heldout", ["declarations", "promise", "mapped_conditional_types"]),
        ("lib/lib.es2015.iterable.d.ts", "development", ["declarations", "iterators", "computed_properties"]),
        ("lib/lib.es5.d.ts", "heldout", ["large_declarations", "overloads", "generic_interfaces"]),
    ]:
        npm_source("typescript", path, split, features)

    for repo_name, path, split, features in [
        ("tree-sitter-json", "tree-sitter.json", "development", ["small_config", "objects", "arrays"]),
        ("tree-sitter-json", "package.json", "heldout", ["package_manifest", "strings", "arrays"]),
        ("tree-sitter-json", "src/node-types.json", "development", ["schema_like_metadata", "object_array", "booleans"]),
        ("tree-sitter-json", "src/grammar.json", "heldout", ["grammar_data", "nested_objects"]),
        ("tree-sitter-java", "src/node-types.json", "development", ["larger_schema_like_metadata", "object_array"]),
        ("tree-sitter-typescript", "typescript/src/grammar.json", "heldout", ["large_grammar_data", "deep_objects", "escaped_regex_strings"]),
    ]:
        repo = ROOT / "references" / repo_name
        data, revision, blob = git_bytes(repo, path)
        lic_name = repo_name + "-MIT.txt"
        if lic_name not in LICENSES:
            lic_data, lic_rev, _ = git_bytes(repo, "LICENSE")
            license_file(lic_name, lic_data, "MIT", f"https://github.com/tree-sitter/{repo_name}/blob/{lic_rev}/LICENSE")
        add("json", repo_name + "__" + path.replace("/", "__"), data, category="real", split=split,
            features=features, licenses=[LICENSES[lic_name]["path"]], origin={
                "kind": "official_git_source", "repository": "tree-sitter/" + repo_name,
                "revision": revision, "source_path": path,
                "url": f"https://github.com/tree-sitter/{repo_name}/blob/{revision}/{path}",
                "git_blob_sha1": blob, "upstream_sha256": sha256(data),
            })
    for path, split, features in [
        ("package.json", "development", ["package_manifest", "arrays", "nested_objects"]),
        ("lib/typesMap.json", "heldout", ["mapping_data", "escaped_regex_strings"]),
        ("lib/ja/diagnosticMessages.generated.json", "heldout", ["large_message_catalog", "utf8_japanese", "long_strings"]),
    ]:
        npm_source("json", path, split, features)

    # Three deterministic sizes; structured row repetition measures scaling, not a representative application workload.
    for count, split in [(8, "development"), (512, "development"), (8192, "heldout")]:
        row = {"id": 123, "name": "東京 benchmark", "enabled": True,
               "values": [0, -17, 0.125, 1.25e12, None], "meta": {"escaped": "line\nquote\"slash\\"}}
        data = json.dumps([row] * count, ensure_ascii=False, separators=(",", ":")).encode() + b"\n"
        add("json", f"rows-{count:05d}.json", data, category="scaling", split=split,
            features=["repeated_objects", "utf8", "escapes", "numbers", "booleans", "null"],
            licenses=["licenses/GENERATED-MIT.txt"],
            origin={"kind": "deterministic_generated_scaling", "generator": "corpus_prepare.py", "row_count": count})

    for name, source, features, split in [
        ("scalar-string.json", '"scalar root"\n', ["scalar_root"], "development"),
        ("numbers.json", '[0,-0,1,-1,0.0,1.5,1e3,1E-3,-2.4e+12,123456789012345678901234567890]\n', ["number_lexical_edges", "syntax_not_numeric_range"], "heldout"),
        ("escapes.json", '["\\\"", "\\\\", "\\/", "\\b\\f\\n\\r\\t", "\\u0041", "\\uD834\\uDD1E", "\\uDEAD"]\n', ["all_json_escape_forms", "escaped_surrogate_grammar"], "development"),
        ("duplicate-names.json", '{"x":1,"x":2}\n', ["duplicate_keys_allowed_by_syntax"], "heldout"),
        ("unicode.json", '{"日本語":"こんにちは","emoji":"😀","combining":"é"}\n', ["utf8_multibyte", "nonascii_keys"], "development"),
        ("nested-128.json", '[' * 128 + '0' + ']' * 128 + '\n', ["nesting_depth_128"], "heldout"),
    ]:
        generated("json", name, source, features, split=split)

    java_probes = [
        ("CoreDeclarations.java", 'package corpus; import java.util.List; interface Named { String name(); } record Item<T>(T value) {} enum Mode { ON, OFF } class CoreDeclarations<T extends Number & Comparable<T>> implements Named { private final List<? extends T> values; CoreDeclarations(List<? extends T> values) { this.values = values; } public String name() { return "core"; } <U> U echo(U value) { return value; } }\n', ["core_types", "generics", "record", "enum"], 17, False),
        ("CoreStatements.java", 'class CoreStatements { int sum(int[] values) throws Exception { int total = 0; for (int value : values) { if (value < 0) continue; total += value; } try (java.io.StringReader r = new java.io.StringReader("ok")) { total += r.read(); } catch (java.io.IOException e) { throw e; } finally { total++; } Runnable done = () -> System.out.println(totalValue()); done.run(); return total; } int totalValue() { return 1; } }\n', ["loops", "try_resources", "lambda"], 8, False),
        ("TextBlocksUnicode.java", 'class TextBlocksUnicode { String 日本語 = """\n  hello\n  world\n  """; double hex = 0x1.8p+2; int binary = 0b1010_0011; }\n', ["text_block", "utf8_identifier", "hex_float", "binary_literal"], 15, False),
        ("module-info.java", 'module corpus.example { requires java.base; exports corpus.example; }\n', ["module_declaration"], 9, True),
        ("SwitchExpression.java", 'class SwitchExpression { int value(int x) { return switch (x) { case 0 -> 1; case 1 -> { yield 2; } default -> 3; }; } }\n', ["switch_expression", "arrow_case", "yield"], 14, True),
        ("RecordPattern.java", 'record Point(int x, int y) {} class RecordPattern { int value(Object point) { return switch (point) { case Point(int x, int y) -> x + y; default -> 0; }; } }\n', ["record_pattern", "switch_pattern"], 21, True),
        ("TypeUse.java", 'import java.lang.annotation.*; import java.util.List; @Target(ElementType.TYPE_USE) @interface Marker {} class TypeUse { List<@Marker String> names; }\n', ["type_use_annotation"], 8, True),
        ("Receiver.java", 'class Receiver { void accept(Receiver this) {} }\n', ["receiver_parameter"], 8, True),
        ("NonSealed.java", 'sealed interface Shape permits Circle {} non-sealed class Circle implements Shape {}\n', ["sealed", "non_sealed"], 17, True),
        ("IntersectionCast.java", 'class IntersectionCast { Object value(Object input) { return (Runnable & java.io.Serializable) input; } }\n', ["intersection_cast"], 8, True),
        ("ClassLiterals.java", 'class ClassLiterals { Class<?> primitive = int.class; Class<?> array = int[].class; }\n', ["primitive_class_literal", "array_class_literal"], 5, True),
        ("QualifiedInner.java", 'class Outer<T> { class Inner<U> {} } class QualifiedInner { Outer<String>.Inner<Integer> build(Outer<String> outer) { return outer.new Inner<Integer>(); } }\n', ["generic_inner_class_creation"], 5, True),
        ("UnicodeEscapes.java", 'cl\\u0061ss UnicodeEscapes { int \\u0078 = 1; }\n', ["unicode_escape_preprocessing"], 5, True),
        ("CompactUnit.java", 'void main() { System.out.println("hello"); }\n', ["compact_compilation_unit", "instance_main"], 25, True),
    ]
    for index, (name, source, features, level, limit) in enumerate(java_probes):
        generated("java", name, source, features, split="heldout" if index % 2 else "development",
                  minimum_java_release=level, declared_gramide_limit=limit,
                  expectation_basis="Original syntax probe; language specification feature. No javac/compiler oracle has run.",
                  spec_url=f"https://docs.oracle.com/javase/specs/jls/se{max(level, 8)}/html/index.html")

    ts_probes = [
        ("types.ts", 'export type Getter<T> = { readonly [K in keyof T as `get${Capitalize<string & K>}`]?: () => T[K] }; export type Value<T> = T extends Promise<infer U> ? U : never;\n', ["mapped_types", "conditional_types", "template_literal_types"]),
        ("generics.ts", 'export function first<const T extends readonly unknown[]>(values: T): T[number] | undefined { return values[0]; } export interface Store<T> { get<K extends keyof T>(key: K): T[K]; }\n', ["const_type_parameters", "indexed_access_types", "generic_methods"]),
        ("expressions.ts", 'const config = { host: "localhost", port: 80 } satisfies Record<string, string | number>; const port = config?.port ?? 443; const pattern = /a(?:b|c)+/giu; export const format = (x: number) => `value=${x ** 2}`;\n', ["satisfies", "optional_chaining", "nullish_coalescing", "regex", "template_strings"]),
        ("namespace-enum.ts", 'namespace Models { export enum Mode { Idle, Running = 2 } export interface Item { id: number; } } export import Mode = Models.Mode;\n', ["namespace", "enum", "import_alias"]),
        ("class-private.ts", 'export class Counter { #value = 0; static { this.name; } constructor(public readonly label: string) {} get value(): number { return this.#value; } add(delta = 1): this { this.#value += delta; return this; } }\n', ["private_fields", "static_block", "parameter_property", "accessor"]),
        ("async-generator.ts", 'export async function* values(source: AsyncIterable<number>) { for await (const item of source) { yield await Promise.resolve(item); } }\n', ["async_generator", "for_await"]),
        ("decorators.ts", 'function logged(value: Function, context: ClassMethodDecoratorContext) { return value; } class Service { @logged run() {} }\n', ["decorator_syntax"]),
        ("import-attributes.ts", 'import data from "./data.json" with { type: "json" }; export type { Model } from "./model.js"; export { data };\n', ["import_attributes", "type_only_export"]),
    ]
    for index, (name, source, features) in enumerate(ts_probes):
        generated("typescript", name, source, features, split="heldout" if index % 2 else "development",
                  typescript_version="5.9.3", validation_scope="Syntactic parse only; imports need not resolve and type errors are outside scope")
    generated("typescript", "jsx.tsx", 'interface Props { title: string; } export const View = ({ title }: Props) => <section data-title={title}><h1>{title}</h1><input disabled /></section>;\n',
              ["tsx", "jsx_elements", "jsx_attributes"], split="heldout", grammar_variant="tsx",
              optional_variant=True, headline_group="separate_optional_tsx", typescript_version="5.9.3")

    # All edits retain origin attribution. Remove only the final syntactic closing brace.
    controls = {
        "java": {"JsonNull.java", "JsonReader.java"},
        "typescript": {"corePublic.ts", "performance.ts"},
        "json": {"tree-sitter-json__package.json", "tree-sitter-json__src__grammar.json"},
    }
    for entry in list(ENTRIES):
        if entry["category"] == "real" and Path(entry["path"]).name in controls.get(entry["language"], set()):
            malformed_from(entry, "missing-final-brace", "Remove the last required object/type/function closing brace; no other bytes changed")
    for language, name, source, rationale in [
        ("json", "trailing-comma.json", '{"x":1,}\n', "Trailing object comma is not JSON grammar"),
        ("json", "leading-zero.json", '[01]\n', "Leading zero with another integer digit is not JSON number grammar"),
        ("json", "unterminated-string.json", '{"x":"unfinished}\n', "String has no closing quote"),
        ("java", "MissingInitializer.java", 'class MissingInitializer { int value = ; }\n', "Required initializer expression is absent"),
        ("java", "UnterminatedString.java", 'class UnterminatedString { String value = "unfinished; }\n', "Ordinary string has no closing quote"),
        ("typescript", "missing-initializer.ts", 'export const value: number = ;\n', "Required initializer expression is absent"),
        ("typescript", "unterminated-string.ts", 'export const value = "unfinished;\n', "String has no closing quote"),
    ]:
        add(language, name, source, category="malformed", split="development", features=["malformed_syntax"],
            licenses=["licenses/GENERATED-MIT.txt"], expected_syntax="invalid",
            origin={"kind": "original_generated_negative_control", "generator": "corpus_prepare.py"},
            mutation={"rationale": rationale}, validation_scope="Syntax-only negative control, not compiler semantics")

    real = [entry for entry in ENTRIES if entry["category"] == "real"]
    source_lock = {entry["id"]: {"sha256": entry["sha256"], "origin": entry["origin"]} for entry in real}
    lock_path = CORPUS / "source-lock.json"
    if lock_path.exists():
        assert json.loads(lock_path.read_text()) == source_lock, "Frozen upstream sources changed; refusing to silently refreeze"
    json_write("source-lock.json", source_lock)
    totals = {}
    for language in ("json", "typescript", "java"):
        subset = [entry for entry in ENTRIES if entry["language"] == language]
        totals[language] = {
            "files": len(subset), "bytes": sum(entry["bytes"] for entry in subset),
            "categories": {category: sum(entry["category"] == category for entry in subset)
                           for category in ("real", "generated", "coverage_probe", "malformed")},
            "real_size_bands": {band: sum(entry["category"] == "real" and entry["size_band"] == band for entry in subset)
                                for band in ("small", "medium", "large")},
        }
    manifest = {
        "schema_version": 1, "corpus_id": "gramide-duel-20261005-v1", "frozen_at_utc": FROZEN_AT,
        "selection_sha256": sha256((CORPUS / "selection.json").read_bytes()),
        "selected_before_any_tested_parser_runs": True,
        "parser_runs_performed_during_preparation": False,
        "selection_method": "Purposive roles and file sizes, not parser acceptance; all preselected files retained",
        "expected_syntax_policy": "Upstream released sources or manually specified syntax probes; no compiler acceptance claimed",
        "held_out_policy": "Do not tune on heldout files. Preserve partition and report it separately. No known prior-use guarantee outside this task.",
        "reporting_policy": "Publish full fixed-set acceptance/error counts. Time successes separately; never silently omit a rejection or treat failure as fast success. Separate real, scaling, coverage and malformed results. TSX is an optional separate variant.",
        "total_files": len(ENTRIES), "totals": totals, "licenses": LICENSES, "files": ENTRIES,
    }
    json_write("manifest.json", manifest)
    coverage = [entry for entry in ENTRIES if entry["category"] in ("coverage_probe", "malformed")]
    json_write("coverage-plan.json", {
        "status": "unexecuted_plan", "not_a_conformance_certificate": True,
        "cases": [{key: entry[key] for key in ("id", "path", "language", "grammar_variant", "features", "expected_syntax", "split")}
                  | {key: entry[key] for key in ("minimum_java_release", "declared_gramide_limit", "optional_variant") if key in entry}
                  for entry in coverage],
    })
    checksums = []
    for path in sorted(CORPUS.rglob("*")):
        if path.is_file() and path.name != "checksums.sha256":
            checksums.append(f"{sha256(path.read_bytes())}  {path.relative_to(CORPUS)}")
    write("checksums.sha256", "\n".join(checksums) + "\n")
    print(json.dumps({"manifest": str(CORPUS / "manifest.json"), "total_files": len(ENTRIES), "totals": totals}, indent=2))


def verify():
    count = 0
    for line in (CORPUS / "checksums.sha256").read_text().splitlines():
        digest, relative = line.split("  ", 1)
        assert sha256((CORPUS / relative).read_bytes()) == digest, relative
        count += 1
    manifest = json.loads((CORPUS / "manifest.json").read_text())
    for entry in manifest["files"]:
        data = (CORPUS / entry["path"]).read_bytes()
        assert len(data) == entry["bytes"] and sha256(data) == entry["sha256"], entry["id"]
        for path in entry["license_paths"]:
            assert (CORPUS / path).is_file(), path
    print(f"Verified {count} retained files and {len(manifest['files'])} benchmark inputs; no parser executed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    options = parser.parse_args()
    verify() if options.verify else prepare()
