"""The versioned API schema is derived from the same registry as runtime routing."""

from __future__ import annotations
import re
from typing import Any
from functools import lru_cache
from suzent.api.operations import LEGACY_PATHS, OPERATIONS


@lru_cache(maxsize=1)
def contract() -> dict[str, Any]:
    definitions: dict[str, Any] = {}
    paths: dict[str, Any] = {}
    for op in OPERATIONS:
        for model in (op.request, op.response, op.query):
            if model is None:
                continue
            schema = model.model_json_schema(
                ref_template="#/components/schemas/{model}"
            )
            definitions.update(schema.pop("$defs", {}))
            definitions[model.__name__] = schema
        operation = {
            "operationId": op.name,
            "x-legacy-path": LEGACY_PATHS.get(op.name),
            "x-actions": list(op.actions),
            "x-chat-scope": op.chat,
            "x-host-only": op.host_only,
            "x-transport": op.transport,
            "x-read-only": op.read_only or op.method == "GET",
            "responses": {
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": {
                                "$ref": "#/components/schemas/" + op.response.__name__
                            }
                        }
                    },
                }
            },
        }
        status = (
            "201"
            if op.name in {"createChat", "createProject"}
            else "202"
            if op.name in {"send", "steer"}
            else "200"
        )
        successful = operation["responses"].pop("200")
        operation["responses"][status] = successful
        if op.host_handler:
            operation["x-host-request"] = {
                "$ref": "#/components/schemas/HostFieldsRequest"
            }
        if op.transport in {"binary", "sse", "websocket"}:
            media_type = (
                "text/event-stream"
                if op.transport == "sse"
                else "application/octet-stream"
            )
            successful["content"] = {
                media_type: {"schema": {"type": "string", "format": "binary"}}
            }
            if op.transport == "sse":
                operation["responses"]["204"] = {"description": "No active stream"}
        if op.transport == "multipart":
            operation["requestBody"] = {
                "required": True,
                "content": {
                    "multipart/form-data": {
                        "schema": {
                            "type": "object",
                            "required": ["files"],
                            "properties": {
                                "files": {
                                    "type": "array",
                                    "maxItems": 10,
                                    "items": {"type": "string", "format": "binary"},
                                }
                            },
                        }
                    }
                },
            }
        params = [
            {"name": p, "in": "path", "required": True, "schema": {"type": "string"}}
            for p in re.findall(r"{(\w+)}", op.path)
        ]
        if op.query:
            query_schema = op.query.model_json_schema()
            for name, field in query_schema.get("properties", {}).items():
                params.append(
                    {
                        "name": name,
                        "in": "query",
                        "required": name in query_schema.get("required", []),
                        "schema": field,
                    }
                )
        if op.chat == "query":
            params.append(
                {
                    "name": "chat_id",
                    "in": "query",
                    "required": True,
                    "schema": {"type": "string", "minLength": 1, "maxLength": 200},
                }
            )
        if params:
            operation["parameters"] = params
        if op.request:
            operation["requestBody"] = {
                "required": op.request.__name__ != "EmptyRequest",
                "content": {
                    "application/json": {
                        "schema": {
                            "$ref": "#/components/schemas/" + op.request.__name__
                        }
                    }
                },
            }
        paths.setdefault("/api/v1" + op.path, {})[op.method.lower()] = operation
    return {
        "openapi": "3.1.0",
        "info": {"title": "Suzent resource API", "version": "1.0.0"},
        "paths": paths,
        "components": {"schemas": definitions},
    }
