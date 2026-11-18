import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = BACKEND_ROOT / "openapi-project-management.json"
HTTP_METHODS = frozenset({"get", "post", "put", "patch", "delete", "head", "options", "trace"})
PM_TAG = "Project Management"
PM_PATH_PREFIX = "/api/v1/projects"


def load_current_schema() -> dict[str, Any]:
    if str(BACKEND_ROOT) not in sys.path:
        sys.path.insert(0, str(BACKEND_ROOT))
    from app.main import app

    return app.openapi()


def is_pm_operation(path: str, method: str, operation: dict[str, Any]) -> bool:
    return method in HTTP_METHODS and (
        path.startswith(PM_PATH_PREFIX) or PM_TAG in operation.get("tags", [])
    )


def collect_pm_paths(schema: dict[str, Any]) -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for path, path_item in schema.get("paths", {}).items():
        selected = {
            method: operation
            for method, operation in path_item.items()
            if method in HTTP_METHODS and isinstance(operation, dict) and is_pm_operation(path, method, operation)
        }
        if selected:
            path_level = {key: value for key, value in path_item.items() if key not in HTTP_METHODS}
            paths[path] = {**path_level, **selected}
    return paths


def iter_operations(paths: dict[str, Any]) -> Any:
    for path, path_item in paths.items():
        for method, operation in path_item.items():
            if method in HTTP_METHODS and isinstance(operation, dict):
                yield path, method, operation


def collect_refs(node: Any, found: set[str]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str) and value.startswith("#/components/schemas/"):
                found.add(value.rsplit("/", 1)[-1])
            else:
                collect_refs(value, found)
    elif isinstance(node, list):
        for value in node:
            collect_refs(value, found)


def build_snapshot(schema: dict[str, Any]) -> dict[str, Any]:
    paths = collect_pm_paths(schema)
    refs: set[str] = set()
    collect_refs(paths, refs)
    source_schemas = schema.get("components", {}).get("schemas", {})
    selected_schemas: dict[str, Any] = {}
    pending = list(refs)
    while pending:
        name = pending.pop()
        if name in selected_schemas or name not in source_schemas:
            continue
        selected_schemas[name] = source_schemas[name]
        discovered: set[str] = set()
        collect_refs(source_schemas[name], discovered)
        pending.extend(discovered)
    components: dict[str, Any] = {"schemas": selected_schemas}
    if "securitySchemes" in schema.get("components", {}):
        components["securitySchemes"] = schema["components"]["securitySchemes"]
    return {
        "openapi": schema.get("openapi"),
        "info": schema.get("info", {}),
        "paths": paths,
        "components": components,
    }


def schema_shape(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return None
    parts: list[Any] = []
    for key in ("$ref", "type", "format", "nullable"):
        if key in schema:
            parts.append((key, json.dumps(schema[key], sort_keys=True)))
    if "enum" in schema:
        parts.append(("enum", tuple(str(value) for value in schema["enum"])))
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema:
            parts.append((key, tuple(schema_shape(item) for item in schema[key])))
    if "items" in schema:
        parts.append(("items", schema_shape(schema["items"])))
    return tuple(parts)


def parameter_map(operation: dict[str, Any]) -> dict[tuple[Any, Any], dict[str, Any]]:
    return {
        (parameter.get("name"), parameter.get("in", "query")): parameter
        for parameter in operation.get("parameters", [])
        if isinstance(parameter, dict)
    }


def request_body(operation: dict[str, Any]) -> dict[str, Any] | None:
    body = operation.get("requestBody")
    if not isinstance(body, dict):
        return None
    return {
        "required": bool(body.get("required", False)),
        "content": {
            media: schema_shape(details.get("schema"))
            for media, details in body.get("content", {}).items()
            if isinstance(details, dict)
        },
    }


def response_map(operation: dict[str, Any]) -> dict[str, dict[str, Any]]:
    responses: dict[str, dict[str, Any]] = {}
    for code, details in operation.get("responses", {}).items():
        if not (str(code).startswith("2") or str(code) == "default") or not isinstance(details, dict):
            continue
        responses[str(code)] = {
            media: schema_shape(content.get("schema"))
            for media, content in (details.get("content") or {}).items()
            if isinstance(content, dict)
        }
    return responses


def compare_operation(path: str, method: str, before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    label = f"{method.upper()} {path}"
    errors: list[str] = []
    before_params = parameter_map(before)
    after_params = parameter_map(after)
    for name, baseline in before_params.items():
        current = after_params.get(name)
        if current is None:
            errors.append(f"{label}: removed parameter {name[0]} ({name[1]})")
            continue
        if not baseline.get("required", False) and current.get("required", False):
            errors.append(f"{label}: parameter {name[0]} ({name[1]}) became required")
        if schema_shape(baseline.get("schema")) != schema_shape(current.get("schema")):
            errors.append(f"{label}: parameter {name[0]} ({name[1]}) schema changed")

    before_body = request_body(before)
    after_body = request_body(after)
    if before_body is not None:
        if after_body is None:
            errors.append(f"{label}: request body removed")
        else:
            if before_body["required"] != after_body["required"]:
                errors.append(f"{label}: request body required flag changed")
            for media, shape in before_body["content"].items():
                if media not in after_body["content"]:
                    errors.append(f"{label}: request body media type {media} removed")
                elif shape != after_body["content"][media]:
                    errors.append(f"{label}: request body schema changed for {media}")

    before_responses = response_map(before)
    after_responses = response_map(after)
    for code, content in before_responses.items():
        if code not in after_responses:
            errors.append(f"{label}: response {code} removed")
            continue
        for media, shape in content.items():
            if media not in after_responses[code]:
                errors.append(f"{label}: response {code} media type {media} removed")
            elif shape != after_responses[code][media]:
                errors.append(f"{label}: response {code} schema changed for {media}")
    return errors


def compare(baseline: dict[str, Any], current: dict[str, Any]) -> list[str]:
    before_ops = {(path, method): op for path, method, op in iter_operations(baseline.get("paths", {}))}
    after_ops = {(path, method): op for path, method, op in iter_operations(current.get("paths", {}))}
    errors: list[str] = []
    for key in sorted(before_ops):
        if key not in after_ops:
            errors.append(f"removed operation: {key[0].upper()} {key[1]}")
        else:
            errors.extend(compare_operation(key[1], key[0], before_ops[key], after_ops[key]))
    return errors


def main() -> int:
    arguments = set(sys.argv[1:])
    if arguments - {"--update"}:
        print(f"usage: {Path(sys.argv[0]).name} [--update]", file=sys.stderr)
        return 2
    current = build_snapshot(load_current_schema())
    operation_count = sum(1 for _ in iter_operations(current["paths"]))
    if "--update" in arguments:
        SNAPSHOT_PATH.write_text(
            json.dumps(current, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"updated {SNAPSHOT_PATH.name}: {operation_count} PM operations snapshotted")
        return 0
    if not SNAPSHOT_PATH.exists():
        print(f"missing snapshot: {SNAPSHOT_PATH}", file=sys.stderr)
        return 1
    baseline = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    errors = compare(baseline, current)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"snapshot check FAILED: {len(errors)} breaking change(s)", file=sys.stderr)
        return 1
    print(f"snapshot check OK: {operation_count} PM operations, 0 breaking changes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
