import json


def infer_type(value_str: str):
    """Infer a Python type from a CLI string value (bool, null, int, float, json, str)."""
    lower = value_str.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    if lower in ("null", "none"):
        return None

    for converter in (int, float):
        try:
            return converter(value_str)
        except ValueError:
            pass

    if value_str.startswith(("{", "[")):
        try:
            return json.loads(value_str)
        except json.JSONDecodeError:
            pass

    return value_str
