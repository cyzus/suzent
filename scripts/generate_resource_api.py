"""Generate the common OpenAPI contract, DTOs and transport clients. Run with --check in CI."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from suzent.api.operations import LEGACY_PATHS, OPERATIONS
from suzent.api.schema import contract

ROOT = Path(__file__).resolve().parents[1]


def camel(name: str) -> str:
    return re.sub(r"_([a-z])", lambda m: m[1].upper(), name)


def swift_name(name: str) -> str:
    value = camel(name)
    return (
        f"`{value}`"
        if value
        in {
            "protocol",
            "class",
            "struct",
            "case",
            "default",
            "repeat",
            "in",
            "is",
            "init",
        }
        else value
    )


def nullable(schema: dict) -> bool:
    return any(s.get("type") == "null" for s in schema.get("anyOf", []))


def base_schema(schema: dict) -> dict:
    if "anyOf" in schema:
        choices = [s for s in schema["anyOf"] if s.get("type") != "null"]
        if len(choices) == 1:
            return choices[0]
    return schema


def wire_type(schema: dict, language: str) -> str:
    schema = base_schema(schema)
    if "$ref" in schema:
        return "Wire" + schema["$ref"].split("/")[-1]
    kind = schema.get("type")
    if language == "ts" and "enum" in schema:
        return " | ".join(json.dumps(v) for v in schema["enum"])
    if kind == "array":
        item = wire_type(schema.get("items", {}), language)
        return {
            "ts": f"Array<{item}>",
            "swift": f"[{item}]",
            "kotlin": f"List<{item}>",
        }[language]
    if kind == "object":
        additional = schema.get("additionalProperties", {})
        value = wire_type(additional if isinstance(additional, dict) else {}, language)
        return {
            "ts": f"Record<string, {value}>",
            "swift": f"[String: {value}]",
            "kotlin": f"Map<String, {value}>",
        }[language]
    return {
        "ts": {
            "string": "string",
            "integer": "number",
            "number": "number",
            "boolean": "boolean",
        },
        "swift": {
            "string": "String",
            "integer": "Int",
            "number": "Double",
            "boolean": "Bool",
        },
        "kotlin": {
            "string": "String",
            "integer": "Int",
            "number": "Double",
            "boolean": "Boolean",
        },
    }[language].get(
        kind, {"ts": "unknown", "swift": "JSONValue", "kotlin": "Any?"}[language]
    )


def default_value(schema: dict, language: str) -> str:
    value = schema.get("default")
    if value is None:
        return {"swift": "nil", "kotlin": "null", "ts": "undefined"}[language]
    if isinstance(value, list):
        return {"swift": "[]", "kotlin": "emptyList()", "ts": "[]"}[language]
    return json.dumps(value, ensure_ascii=False)


def kotlin_decode(schema: dict, expression: str, depth: int = 0) -> str:
    schema = base_schema(schema)
    if "$ref" in schema:
        return f"{wire_type(schema, 'kotlin')}.fromJson({expression} as JSONObject)"
    kind = schema.get("type")
    if kind == "array":
        item = f"item{depth}"
        return f"({expression} as org.json.JSONArray).let {{ array{depth} -> (0 until array{depth}.length()).map {{ {item} -> {kotlin_decode(schema.get('items', {}), f'array{depth}.get({item})', depth + 1)} }} }}"
    if kind == "object":
        additional = schema.get("additionalProperties", {})
        value = additional if isinstance(additional, dict) else {}
        return f"({expression} as JSONObject).let {{ obj{depth} -> obj{depth}.keys().asSequence().associateWith {{ key{depth} -> {kotlin_decode(value, f'obj{depth}.get(key{depth})', depth + 1)} }} }}"
    if kind in {"integer", "number"}:
        return (
            f"({expression} as Number).{'toInt' if kind == 'integer' else 'toDouble'}()"
        )
    if kind in {"string", "boolean"}:
        return f"({expression} as {wire_type(schema, 'kotlin')})"
    return f"resourceJsonValue({expression})"


def dtos(schemas: dict, language: str) -> str:
    lines = []
    for name, schema in sorted(schemas.items()):
        fields = schema.get("properties", {})
        required = schema.get("required", [])
        if language == "ts":
            lines.append(f"export interface Wire{name} {{")
            for key, value in fields.items():
                type_name = wire_type(value, language) + (
                    " | null" if nullable(value) else ""
                )
                lines.append(f"  {key}{'' if key in required else '?'}: {type_name};")
            if schema.get("additionalProperties") is True:
                lines.append("  [key: string]: unknown;")
            lines.append("}\n")
        elif language == "swift":
            lines.append(f"public struct Wire{name}: Codable, Sendable {{")
            if not fields:
                lines.extend(
                    [
                        "    public var values: [String: JSONValue]",
                        "    public init(values: [String: JSONValue] = [:]) { self.values = values }",
                        "    public init(from decoder: Decoder) throws { values = try .init(from: decoder) }",
                        "    public func encode(to encoder: Encoder) throws { try values.encode(to: encoder) }",
                        "}\n",
                    ]
                )
                continue
            extras = schema.get("additionalProperties") is True
            if extras:
                lines.append("    public var extraFields: [String: JSONValue]")
            args = []
            for key, value in fields.items():
                optional = key not in required or nullable(value)
                type_name = wire_type(value, language) + ("?" if optional else "")
                lines.append(f"    public var {swift_name(key)}: {type_name}")
                default = (
                    " = " + default_value(value, language)
                    if key not in required
                    else ""
                )
                args.append(f"{swift_name(key)}: {type_name}{default}")
            if extras:
                args.append("extraFields: [String: JSONValue] = [:]")
            lines.append(f"    public init({', '.join(args)}) {{")
            if extras:
                lines.append("        self.extraFields = extraFields")
            for key in fields:
                lines.append(f"        self.{swift_name(key)} = {swift_name(key)}")
            lines.extend(["    }", "    enum CodingKeys: String, CodingKey {"])
            for key in fields:
                lines.append(f'        case {swift_name(key)} = "{key}"')
            lines.append("    }")
            if extras:
                known = ", ".join(json.dumps(key) for key in fields)
                lines.extend(
                    [
                        "    public init(from decoder: Decoder) throws {",
                        "        let container = try decoder.container(keyedBy: CodingKeys.self)",
                    ]
                )
                for key, value in fields.items():
                    optional = key not in required or nullable(value)
                    decode = "decodeIfPresent" if optional else "decode"
                    lines.append(
                        f"        self.{swift_name(key)} = try container.{decode}({wire_type(value, language)}.self, forKey: .{swift_name(key)})"
                    )
                lines.append(
                    f"        extraFields = try [String: JSONValue](from: decoder).filter {{ ![{known}].contains($0.key) }}"
                )
                lines.extend(
                    [
                        "    }",
                        "    public func encode(to encoder: Encoder) throws {",
                        "        var container = encoder.container(keyedBy: ResourceCodingKey.self)",
                        "        for (key, value) in extraFields { try container.encode(value, forKey: ResourceCodingKey(key)) }",
                    ]
                )
                for key, value in fields.items():
                    encode = (
                        "encodeIfPresent"
                        if key not in required or nullable(value)
                        else "encode"
                    )
                    lines.append(
                        f'        try container.{encode}({swift_name(key)}, forKey: ResourceCodingKey("{key}"))'
                    )
                lines.append("    }")
            lines.append("}\n")
        else:
            if not fields:
                lines.extend(
                    [
                        f"data class Wire{name}(val values: Map<String, Any?> = emptyMap()) {{",
                        "    fun json(): JSONObject = resourceJsonObject(values)",
                        f"    companion object {{ fun fromJson(value: JSONObject) = Wire{name}(value.keys().asSequence().associateWith {{ resourceJsonValue(value.get(it)) }}) }}",
                        "}\n",
                    ]
                )
                continue
            args = []
            for key, value in fields.items():
                type_name = wire_type(value, language)
                if (key not in required or nullable(value)) and not type_name.endswith(
                    "?"
                ):
                    type_name += "?"
                default = (
                    " = " + default_value(value, language)
                    if key not in required
                    else ""
                )
                args.append(f"val {camel(key)}: {type_name}{default}")
            extras = schema.get("additionalProperties") is True
            if extras:
                args.append("val extraFields: Map<String, Any?> = emptyMap()")
            lines.append(f"data class Wire{name}({', '.join(args)}) {{")
            lines.append("    fun json(): JSONObject = JSONObject().apply {")
            if extras:
                lines.append(
                    "        extraFields.forEach { (key, value) -> put(key, resourceEncodeValue(value)) }"
                )
            for key, value in fields.items():
                prop = camel(key)
                if key not in required or nullable(value):
                    lines.append(
                        f'        {prop}?.let {{ put("{key}", resourceEncodeValue(it)) }}'
                    )
                else:
                    lines.append(f'        put("{key}", resourceEncodeValue({prop}))')
            lines.extend(
                [
                    "    }",
                    f"    companion object {{ fun fromJson(value: JSONObject): Wire{name} = Wire{name}(",
                ]
            )
            for key, value in fields.items():
                decoded = kotlin_decode(value, f'value.get("{key}")')
                if key not in required or nullable(value):
                    fallback = (
                        default_value(value, language)
                        if key not in required
                        else "null"
                    )
                    decoded = f'if (value.has("{key}") && !value.isNull("{key}")) {decoded} else {fallback}'
                lines.append(f"        {camel(key)} = {decoded},")
            if extras:
                known = ", ".join(json.dumps(key) for key in fields)
                lines.append(
                    f"        extraFields = value.keys().asSequence().filter {{ it !in setOf({known}) }}.associateWith {{ resourceJsonValue(value.get(it)) }},"
                )
            lines.extend(["    ) }", "}\n"])
    return "\n".join(lines)


def swift(schema: dict) -> str:
    lines = [
        "// Generated by scripts/generate_resource_api.py. Do not edit.",
        "import Foundation",
        """private struct ResourceCodingKey: CodingKey {
    let stringValue: String
    var intValue: Int? { nil }
    init(_ value: String) { stringValue = value }
    init?(stringValue: String) { self.init(stringValue) }
    init?(intValue: Int) { return nil }
}
""",
        dtos(schema, "swift"),
        """
public struct ResourceRequest: Sendable {
    public let path: String
    public let legacyPath: String?
    public let method: String
    public let body: Data?
    public let readOnly: Bool
    public func path(shared: Bool) -> String { shared ? path : (legacyPath ?? path) }
}

public enum ResourceRequests {
    private static func path(_ template: String, _ values: [String: String]) throws -> String {
        try template.split(separator: "/", omittingEmptySubsequences: false).map { segment in
            guard segment.hasPrefix("{"), segment.hasSuffix("}") else { return String(segment) }
            let key = String(segment.dropFirst().dropLast())
            guard let value = values[key], !value.isEmpty, value.count <= 200, !value.contains("/"), value != ".", value != ".." else { throw ClientError.invalidResponse }
            return value
        }.joined(separator: "/")
    }
""",
    ]
    for op in OPERATIONS:
        keys = re.findall(r"{(\w+)}", op.path)
        args = [f"{camel(key)}: String" for key in keys]
        if op.request:
            args.append(f"body: Wire{op.request.__name__}")
        values = (
            "[" + ", ".join(f'"{key}": {camel(key)}' for key in keys) + "]"
            if keys
            else "[:]"
        )
        path = f'try path("api/v1{op.path}", {values})'
        legacy = (
            f'try path("{LEGACY_PATHS[op.name].lstrip(chr(47))}", {values})'
            if op.name in LEGACY_PATHS
            else "nil"
        )
        body = (
            "try JSONEncoder().encode(body)"
            if op.request
            else (
                'Data("{}".utf8)'
                if op.method == "POST" and op.transport == "json"
                else "nil"
            )
        )
        lines.append(
            f'    public static func {op.name}({", ".join(args)}) throws -> ResourceRequest {{\n        ResourceRequest(path: {path}, legacyPath: {legacy}, method: "{op.method}", body: {body}, readOnly: {str(op.read_only or op.method == "GET").lower()})\n    }}'
        )
    lines.extend(
        [
            "}",
            """
public struct ResourceClient: Sendable {
    public let transport: @Sendable (ResourceRequest) async throws -> Data
    public init(transport: @escaping @Sendable (ResourceRequest) async throws -> Data) { self.transport = transport }
""",
        ]
    )
    for op in OPERATIONS:
        if op.transport != "json":
            continue
        keys = re.findall(r"{(\w+)}", op.path)
        args = [f"{camel(key)}: String" for key in keys]
        forwarded = [f"{camel(key)}: {camel(key)}" for key in keys]
        if op.request:
            args.append(f"body: Wire{op.request.__name__}")
            forwarded.append("body: body")
        lines.append(
            f"    public func {op.name}({', '.join(args)}) async throws -> Wire{op.response.__name__} {{\n        try JSONDecoder().decode(Wire{op.response.__name__}.self, from: await transport(ResourceRequests.{op.name}({', '.join(forwarded)})))\n    }}"
        )
    return "\n".join(lines + ["}", ""])


def kotlin(schema: dict) -> str:
    lines = [
        "// Generated by scripts/generate_resource_api.py. Do not edit.",
        "package com.suzent.mobile",
        "import org.json.JSONObject",
        """
private fun resourceJsonValue(value: Any?): Any? = when (value) {
    null, JSONObject.NULL -> null
    is JSONObject -> value.keys().asSequence().associateWith { resourceJsonValue(value.get(it)) }
    is org.json.JSONArray -> (0 until value.length()).map { resourceJsonValue(value.get(it)) }
    else -> value
}
private fun resourceJsonObject(value: Map<String, Any?>): JSONObject = JSONObject().apply { value.forEach { (key, item) -> put(key, resourceEncodeValue(item)) } }
private fun resourceEncodeValue(value: Any?): Any = when (value) {
    null -> JSONObject.NULL
    is Map<*, *> -> JSONObject().apply { value.forEach { (key, item) -> put(key.toString(), resourceEncodeValue(item)) } }
    is List<*> -> org.json.JSONArray().apply { value.forEach { put(resourceEncodeValue(it)) } }
""",
    ]
    for name in sorted(schema):
        lines.append(f"    is Wire{name} -> value.json()")
    lines.extend(
        [
            "    else -> value",
            "}",
            dtos(schema, "kotlin"),
            """
data class ResourceRequest(val path: String, val legacyPath: String?, val method: String, val body: JSONObject?, val readOnly: Boolean) {
    fun path(shared: Boolean): String = if (shared) path else legacyPath ?: path
}
object ResourceRequests {
    private fun path(template: String, values: Map<String, String>): String {
        return template.split("/").joinToString("/") { segment ->
            if (!segment.startsWith("{") || !segment.endsWith("}")) segment
            else {
                val value = requireNotNull(values[segment.drop(1).dropLast(1)])
                require(value.isNotEmpty() && value.length <= 200 && '/' !in value && value != "." && value != "..")
                value
            }
        }
    }
""",
        ]
    )
    for op in OPERATIONS:
        keys = re.findall(r"{(\w+)}", op.path)
        args = [f"{camel(key)}: String" for key in keys]
        if op.request:
            args.append(f"body: Wire{op.request.__name__}")
        values = "mapOf(" + ", ".join(f'"{key}" to {camel(key)}' for key in keys) + ")"
        legacy = (
            f'path("{LEGACY_PATHS[op.name].lstrip(chr(47))}", {values})'
            if op.name in LEGACY_PATHS
            else "null"
        )
        body = (
            "body.json()"
            if op.request
            else (
                "JSONObject()"
                if op.method == "POST" and op.transport == "json"
                else "null"
            )
        )
        lines.append(
            f'    fun {op.name}({", ".join(args)}): ResourceRequest = ResourceRequest(path("api/v1{op.path}", {values}), {legacy}, "{op.method}", {body}, {str(op.read_only or op.method == "GET").lower()})'
        )
    lines.extend(
        [
            "}",
            "class ResourceClient(private val transport: suspend (ResourceRequest) -> JSONObject) {",
        ]
    )
    for op in OPERATIONS:
        if op.transport != "json":
            continue
        keys = re.findall(r"{(\w+)}", op.path)
        args = [f"{camel(key)}: String" for key in keys]
        forwards = [camel(key) for key in keys]
        if op.request:
            args.append(f"body: Wire{op.request.__name__}")
            forwards.append("body")
        lines.append(
            f"    suspend fun {op.name}({', '.join(args)}): Wire{op.response.__name__} = Wire{op.response.__name__}.fromJson(transport(ResourceRequests.{op.name}({', '.join(forwards)})))"
        )
    return "\n".join(lines + ["}", ""])


def typescript(schema: dict) -> str:
    lines = [
        "// Generated by scripts/generate_resource_api.py. Do not edit.",
        dtos(schema, "ts"),
        """
export interface ResourceRequest { path: string; method: string; body?: unknown; readOnly: boolean; }
export type ResourceTransport = (request: ResourceRequest) => Promise<Response>;
function resourcePath(template: string, parameters: Record<string, string>): string {
  return template.replace(/\\{(\\w+)\\}/g, (_, key: string) => {
    const value = parameters[key];
    if (!value || value.length > 200 || value.includes('/') || value === '.' || value === '..') throw new Error('Invalid resource identifier');
    return encodeURIComponent(value);
  });
}
export const resourceRequests = {
""",
    ]
    for op in OPERATIONS:
        keys = re.findall(r"{(\w+)}", op.path)
        args = [f"{camel(key)}: string" for key in keys]
        if op.request:
            args.append(f"body: Wire{op.request.__name__}")
        mapping = "{" + ", ".join(f"{key}: {camel(key)}" for key in keys) + "}"
        body = ", body" if op.request else ""
        lines.append(
            f'  {op.name}: ({", ".join(args)}): ResourceRequest => ({{path: resourcePath("/api/v1{op.path}", {mapping}), method: "{op.method}", readOnly: {str(op.read_only or op.method == "GET").lower()}{body}}}),'
        )
    lines.append("};\nexport const resourcePaths = {")
    for op in OPERATIONS:
        keys = re.findall(r"{(\w+)}", op.path)
        args = [f"{camel(key)}: string" for key in keys]
        mapping = "{" + ", ".join(f"{key}: {camel(key)}" for key in keys) + "}"
        lines.append(
            f'  {op.name}: ({", ".join(args)}): string => resourcePath("/api/v1{op.path}", {mapping}),'
        )
    lines.extend(
        [
            "};",
            """
export class ResourceClient {
  constructor(private readonly transport: ResourceTransport) {}
  async raw(request: ResourceRequest): Promise<Response> { return this.transport(request); }
  private async json<T>(request: ResourceRequest): Promise<T> {
    const response = await this.transport(request);
    if (!response.ok) throw new Error(`Resource API HTTP ${response.status}`);
    return response.json() as Promise<T>;
  }
""",
        ]
    )
    for op in OPERATIONS:
        if op.transport != "json":
            continue
        keys = re.findall(r"{(\w+)}", op.path)
        args = [f"{camel(key)}: string" for key in keys]
        forwards = [camel(key) for key in keys]
        if op.request:
            args.append(f"body: Wire{op.request.__name__}")
            forwards.append("body")
        lines.append(
            f"  {op.name}({', '.join(args)}): Promise<Wire{op.response.__name__}> {{ return this.json(resourceRequests.{op.name}({', '.join(forwards)})); }}"
        )
    return "\n".join(lines + ["}", ""])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    spec = contract()
    schemas = spec["components"]["schemas"]
    files = {
        ROOT / "packages/api-contract/openapi.json": json.dumps(
            spec, ensure_ascii=False, indent=2
        )
        + "\n",
        ROOT
        / "packages/SuzentCore/Sources/SuzentCore/ResourceAPI.generated.swift": swift(
            schemas
        ),
        ROOT
        / "apps/android/app/src/main/java/com/suzent/mobile/ResourceAPI.generated.kt": kotlin(
            schemas
        ),
        ROOT / "frontend/src/lib/resourceAPI.generated.ts": typescript(schemas),
    }
    stale = []
    for path, content in files.items():
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    if stale:
        raise SystemExit(
            "Regenerate with uv run python scripts/generate_resource_api.py:\n"
            + "\n".join(stale)
        )


if __name__ == "__main__":
    main()
