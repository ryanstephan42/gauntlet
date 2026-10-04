"""Versioned game-config schema validation."""
import re

SCHEMA_VERSION = 1
ACTION_TYPES = {"memory_write", "retroarch_config"}
_HEX = re.compile(r"^0[xX][0-9a-fA-F]+$")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _check_address(value, where, errors):
    if not isinstance(value, str) or not _HEX.match(value):
        errors.append(f"{where}: address must be a hex string like '0x00A5'")


def validate_game(data):
    """Return a list of human-readable errors (empty if valid)."""
    errors = []
    if not isinstance(data, dict):
        return ["config must be a JSON object"]
    version = data.get("schema_version", SCHEMA_VERSION)
    if version != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version {version!r}")

    meta = data.get("meta")
    if not isinstance(meta, dict):
        errors.append("missing 'meta' object")
    else:
        for key in ("name", "core", "rom"):
            if not isinstance(meta.get(key), str) or not meta[key].strip():
                errors.append(f"meta.{key} is required")

    ref = data.get("referee")
    if ref is not None:
        if not isinstance(ref, dict):
            errors.append("'referee' must be an object or null")
        else:
            _check_address(ref.get("address"), "referee", errors)
            if not _is_int(ref.get("bytes", 1)) or ref.get("bytes", 1) < 1:
                errors.append("referee.bytes must be a positive integer")
            if not _is_int(ref.get("win_value")):
                errors.append("referee.win_value must be an integer")

    shop = data.get("shop", [])
    if not isinstance(shop, list):
        errors.append("'shop' must be a list")
        shop = []
    seen = set()
    for i, item in enumerate(shop):
        where = f"shop[{i}]"
        if not isinstance(item, dict):
            errors.append(f"{where}: must be an object")
            continue
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            errors.append(f"{where}: 'id' is required")
        elif item_id in seen:
            errors.append(f"{where}: duplicate id {item_id!r}")
        else:
            seen.add(item_id)
        if not isinstance(item.get("name"), str) or not item["name"]:
            errors.append(f"{where}: 'name' is required")
        if not _is_int(item.get("cost")) or item["cost"] < 0:
            errors.append(f"{where}: 'cost' must be a non-negative integer")
        action = item.get("action_type")
        if action not in ACTION_TYPES:
            errors.append(f"{where}: unknown action_type {action!r}")
        elif action == "memory_write":
            _check_address(item.get("address"), where, errors)
            v = item.get("value")
            if not _is_int(v) or not 0 <= v <= 255:
                errors.append(f"{where}: 'value' must be an integer 0-255")
        elif action == "retroarch_config":
            if not isinstance(item.get("config_file"), str) or not item["config_file"]:
                errors.append(f"{where}: 'config_file' is required")
    return errors
