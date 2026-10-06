"""Versioned game-config schema: normalization (v1 -> v2 migration) and validation.

Schema v2:
  meta:       name, system, core (name or path), rom (filename or path), image, players, description
  memory:     layout (linear|swap16|swap32), endian (little|big)   [defaults from system]
  challenges: [{id, name, description, mode (versus|turns|coop|manual), metric{var},
                win{type, value, order}, time_limit, on_timeout, best_of, min_time, ready{cond}, setup[actions], start_state (name or [names], one picked per match)}]
  shop:       [{id, name, cost, description, category, target, limit, actions[...]}]
A "var" is {address (hex str or {"1": hex, "2": hex}), stride, size, signed, endian, mask, bit}.
A metric may also have add: [{var..., scale}]; its value is then its own value + sum(scale * term).
The metric and each add term may have count/step: the sum of `count` values `step` bytes apart (e.g. one
counter per level), and pointer {address, size=4, mask}: the address is then an offset from the (masked)
value stored at pointer.address, for objects that move between levels.
"""
import copy
import re

from .systems import SYSTEMS

SCHEMA_VERSION = 2
ACTION_TYPES = {"memory_write", "retroarch_config", "retroarch_command", "message"}
MODES = {"versus", "turns", "coop", "manual"}
WIN_TYPES = {"reach", "equals", "bit_set", "eliminate", "compare"}
TARGETS = {"self", "opponent", "others", "all"}
CATEGORIES = {"buff", "debuff", "chaos"}
WRITE_OPS = {"set", "add", "sub", "or", "and", "xor"}
COND_OPS = {"eq", "ne", "ge", "gt", "le", "lt"}
LAYOUTS = {"linear", "swap16", "swap32"}
_HEX = re.compile(r"^(0[xX]|\$)?[0-9a-fA-F]+$")


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def system_for_core(core):
    name = (core or "").rsplit("/", 1)[-1].split("_libretro")[0]
    for system in SYSTEMS.values():
        if name in system.cores:
            return system.id
    return None


# --------------------------------------------------------------------------- normalize
def _migrate_v1_item(item):
    if not isinstance(item, dict) or "actions" in item:
        return item
    action_type = item.get("action_type")
    action = {"type": action_type}
    for key in ("address", "value", "config_file", "size", "endian", "command", "text", "settings"):
        if key in item:
            action[key] = item.pop(key)
    item.pop("action_type", None)
    item["actions"] = [action]
    return item


def normalize_game(data):
    """Deep-copied game with v1 configs migrated and defaults filled in."""
    if not isinstance(data, dict):
        return data
    g = copy.deepcopy(data)
    version = g.get("schema_version", 1)
    meta = g.get("meta")
    if isinstance(meta, dict):
        if not meta.get("system"):
            from .systems import guess_system
            meta["system"] = system_for_core(meta.get("core")) or (
                guess_system(meta["rom"]) if isinstance(meta.get("rom"), str) else None) or ""
        system = SYSTEMS.get(meta.get("system"))
        meta.setdefault("players", 2 if not system else min(system.max_players, 2) or 1)
    else:
        system = None
    mem = g.setdefault("memory", {}) if isinstance(g.get("memory", {}), dict) else g.get("memory")
    if isinstance(mem, dict):
        mem.setdefault("layout", system.layout if system else "linear")
        mem.setdefault("endian", system.endian if system else "little")
    if version == 1:
        ref = g.pop("referee", None)
        if "challenges" not in g:
            if isinstance(ref, dict):
                g["challenges"] = [{
                    "id": "main", "name": "Match", "mode": "versus",
                    "description": ref.get("description", ""),
                    "metric": {"address": ref.get("address"), "size": ref.get("bytes", 1)},
                    "win": {"type": "reach", "value": ref.get("win_value")},
                }]
            elif ref is not None:
                g["challenges"] = ref  # invalid; reported by validation
            else:
                g["challenges"] = [{"id": "main", "name": "Match", "mode": "manual"}]
        if isinstance(g.get("shop"), list):
            g["shop"] = [_migrate_v1_item(i) for i in g["shop"]]
        g["schema_version"] = SCHEMA_VERSION
    g.setdefault("challenges", [{"id": "main", "name": "Match", "mode": "manual"}])
    for ch in g["challenges"] if isinstance(g["challenges"], list) else ():
        if isinstance(ch, dict):
            ch.setdefault("mode", "versus")
            ch.setdefault("best_of", 1)
            ch.setdefault("min_time", 2.0)
            ch.setdefault("time_limit", None)
            ch.setdefault("on_timeout", "compare" if ch.get("mode") != "coop" else "lose")
    for item in g.get("shop", []) if isinstance(g.get("shop", []), list) else ():
        if isinstance(item, dict):
            item.setdefault("category", "buff")
            item.setdefault("target", "self")
            item.setdefault("limit", 1)
            item.setdefault("description", "")
    return g


# --------------------------------------------------------------------------- validate
def _check_hex(value, where, errors, name="address"):
    if not isinstance(value, str) or not _HEX.match(value.strip()):
        errors.append(f"{where}: {name} must be a hex string like '0x00A5'")


def _check_var(var, where, errors, per_player_ok=True):
    if not isinstance(var, dict):
        errors.append(f"{where}: must be an object")
        return
    addr = var.get("address")
    if isinstance(addr, dict) and per_player_ok:
        if not addr:
            errors.append(f"{where}: per-player address map is empty")
        for port, a in addr.items():
            if not str(port).isdigit() or not 1 <= int(port) <= 8:
                errors.append(f"{where}: per-player key {port!r} must be a port number 1-8")
            _check_hex(a, where, errors)
    else:
        _check_hex(addr, where, errors)
    if "stride" in var:
        _check_hex(var["stride"], where, errors, "stride")
    size = var.get("size", 1)
    if not _is_int(size) or not 1 <= size <= 8:
        errors.append(f"{where}: size must be 1-8 bytes")
    if var.get("endian", "little") not in ("little", "big"):
        errors.append(f"{where}: endian must be 'little' or 'big'")
    if "mask" in var and not (_is_int(var["mask"]) or isinstance(var["mask"], str)):
        errors.append(f"{where}: mask must be an integer or hex string")
    if "bit" in var and (not _is_int(var["bit"]) or not 0 <= var["bit"] < 64):
        errors.append(f"{where}: bit must be 0-63")


def _check_count(var, where, errors):
    if not isinstance(var, dict):
        return
    if "pointer" in var:
        ptr = var["pointer"]
        if not isinstance(ptr, dict):
            errors.append(f"{where}: pointer must be an object like {{\"address\": \"0x1F05C0\", \"mask\": "
                          "\"0xFFFFFF\"}")
        else:
            _check_var(ptr, f"{where}.pointer", errors, per_player_ok=False)
            _check_count({k: v for k, v in ptr.items() if k == "pointer"}, f"{where}.pointer", errors)
    if "count" in var and (not _is_int(var["count"]) or not 1 <= var["count"] <= 256):
        errors.append(f"{where}: count must be 1-256")
    if "step" in var:
        _check_hex(var["step"], where, errors, "step")
        if "count" not in var:
            errors.append(f"{where}: step needs count")


def _check_condition(cond, where, errors):
    _check_var(cond, where, errors)
    if not isinstance(cond, dict):
        return
    if cond.get("op", "eq") not in COND_OPS:
        errors.append(f"{where}: op must be one of {sorted(COND_OPS)}")
    if not _is_int(cond.get("value")):
        errors.append(f"{where}: value must be an integer")


def validate_action(action, where):
    errors = []
    if not isinstance(action, dict):
        return [f"{where}: action must be an object"]
    t = action.get("type")
    if not isinstance(t, str) or t not in ACTION_TYPES:
        return [f"{where}: unknown action_type {t!r}"]
    for key in ("duration", "repeat", "delay"):
        if key in action and (not _is_num(action[key]) or action[key] < 0):
            errors.append(f"{where}: {key} must be a non-negative number")
    if t == "memory_write":
        _check_var(action, where, errors)
        if not _is_int(action.get("value")):
            errors.append(f"{where}: 'value' must be an integer")
        elif action.get("op", "set") == "set" and "bit" not in action and "mask" not in action:
            size = action.get("size", 1) if _is_int(action.get("size", 1)) else 1
            lo = -(1 << (8 * size - 1)) if action.get("signed") else 0
            hi = (1 << (8 * size)) - 1
            if not lo <= action["value"] <= hi:
                errors.append(f"{where}: 'value' must fit in {size} byte(s) ({lo}..{hi})")
        if action.get("op", "set") not in WRITE_OPS:
            errors.append(f"{where}: op must be one of {sorted(WRITE_OPS)}")
        if "when" in action:
            _check_condition(action["when"], f"{where}.when", errors)
    elif t == "retroarch_config":
        cfg, inline = action.get("config_file"), action.get("settings")
        if not (isinstance(cfg, str) and cfg) and not isinstance(inline, dict):
            errors.append(f"{where}: 'config_file' is required")
    elif t == "retroarch_command":
        from .retroarch import COMMANDS
        if action.get("command") not in COMMANDS:
            errors.append(f"{where}: unknown RetroArch command {action.get('command')!r}")
    elif t == "message":
        if not isinstance(action.get("text"), str) or not action["text"]:
            errors.append(f"{where}: 'text' is required")
    return errors


def _validate_challenge(ch, where, errors):
    if not isinstance(ch, dict):
        errors.append(f"{where}: must be an object")
        return
    if not isinstance(ch.get("id"), str) or not ch["id"]:
        errors.append(f"{where}: 'id' is required")
    if not isinstance(ch.get("name"), str) or not ch["name"]:
        errors.append(f"{where}: 'name' is required")
    mode = ch.get("mode")
    if mode not in MODES:
        errors.append(f"{where}: mode must be one of {sorted(MODES)}")
        return
    if not _is_int(ch.get("best_of")) or ch["best_of"] < 1 or ch["best_of"] % 2 == 0:
        errors.append(f"{where}: best_of must be an odd number >= 1")
    tl = ch.get("time_limit")
    if tl is not None and (not _is_num(tl) or tl <= 0):
        errors.append(f"{where}: time_limit must be a positive number or null")
    if ch.get("on_timeout") not in ("compare", "draw", "lose"):
        errors.append(f"{where}: on_timeout must be compare, draw or lose")
    if not _is_num(ch.get("min_time")) or ch["min_time"] < 0:
        errors.append(f"{where}: min_time must be >= 0")
    st = ch.get("start_state")
    names = st if isinstance(st, list) else [st]
    if st is not None and (not names or not all(isinstance(n, str) and n and "/" not in n and "\\" not in n
                                                and n not in (".", "..") for n in names)):
        errors.append(f"{where}: start_state must be a plain file name (e.g. mk2_versus.state) "
                      "or a list of them (one is picked per match)")
    if mode == "manual":
        return
    _check_var(ch.get("metric"), f"{where}.metric", errors)
    _check_count(ch.get("metric"), f"{where}.metric", errors)
    terms = (ch.get("metric") or {}).get("add") if isinstance(ch.get("metric"), dict) else None
    if terms is not None:
        if not isinstance(terms, list) or not terms:
            errors.append(f"{where}.metric.add must be a non-empty list")
        else:
            for i, term in enumerate(terms):
                _check_var(term, f"{where}.metric.add[{i}]", errors)
                _check_count(term, f"{where}.metric.add[{i}]", errors)
                if isinstance(term, dict) and not _is_int(term.get("scale", 1)):
                    errors.append(f"{where}.metric.add[{i}]: scale must be an integer")
    win = ch.get("win")
    if not isinstance(win, dict) or win.get("type") not in WIN_TYPES:
        errors.append(f"{where}: win.type must be one of {sorted(WIN_TYPES)}")
    else:
        if win["type"] in ("reach", "equals") and not _is_int(win.get("value")):
            errors.append(f"{where}: win.value must be an integer")
        if win["type"] == "eliminate" and not _is_int(win.get("value", 0)):
            errors.append(f"{where}: win.value must be an integer")
        if win.get("order", "high") not in ("high", "low"):
            errors.append(f"{where}: win.order must be 'high' or 'low'")
        if win["type"] == "compare" and tl is None:
            errors.append(f"{where}: 'compare' challenges need a time_limit")
        if win["type"] == "bit_set" and "bit" not in (ch.get("metric") or {}):
            errors.append(f"{where}: bit_set needs metric.bit")
    if "ready" in ch:
        _check_condition(ch["ready"], f"{where}.ready", errors)
    for i, action in enumerate(ch.get("setup", []) or []):
        errors.extend(validate_action(action, f"{where}.setup[{i}]"))


def validate_game(data):
    """Return a list of human-readable errors (empty if valid). Accepts v1 or v2."""
    if not isinstance(data, dict):
        return ["config must be a JSON object"]
    version = data.get("schema_version", 1)
    if version not in (1, SCHEMA_VERSION):
        return [f"unsupported schema_version {version!r}"]
    errors = []
    try:
        g = normalize_game(data)
    except (TypeError, AttributeError, ValueError) as e:
        return [f"malformed config: {e}"]
    meta = g.get("meta")
    if not isinstance(meta, dict):
        errors.append("missing 'meta' object")
    else:
        for key in ("name", "core", "rom"):
            if not isinstance(meta.get(key), str) or not meta[key].strip():
                errors.append(f"meta.{key} is required")
        if meta.get("system") and meta["system"] not in SYSTEMS:
            errors.append(f"meta.system {meta['system']!r} is not a known system")
        if not _is_int(meta.get("players")) or not 1 <= meta["players"] <= 8:
            errors.append("meta.players must be 1-8")
    mem = g.get("memory")
    if not isinstance(mem, dict) or mem.get("layout") not in LAYOUTS or mem.get("endian") not in ("little", "big"):
        errors.append("memory.layout/endian invalid")
    if version == 1 and data.get("referee") is not None and not isinstance(data.get("referee"), dict):
        errors.append("'referee' must be an object or null")
    elif version == 1 and isinstance(data.get("referee"), dict):
        ref = data["referee"]
        _check_hex(ref.get("address"), "referee", errors)
        if not _is_int(ref.get("bytes", 1)) or ref.get("bytes", 1) < 1:
            errors.append("referee.bytes must be a positive integer")
        if not _is_int(ref.get("win_value")):
            errors.append("referee.win_value must be an integer")
    else:
        challenges = g.get("challenges")
        if not isinstance(challenges, list) or not challenges:
            errors.append("'challenges' must be a non-empty list")
        else:
            seen = set()
            for i, ch in enumerate(challenges):
                _validate_challenge(ch, f"challenges[{i}]", errors)
                cid = ch.get("id") if isinstance(ch, dict) else None
                if isinstance(cid, str) and cid in seen:
                    errors.append(f"challenges[{i}]: duplicate id {cid!r}")
                seen.add(cid if isinstance(cid, str) else None)

    shop = g.get("shop", [])
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
        if item.get("target") not in TARGETS:
            errors.append(f"{where}: target must be one of {sorted(TARGETS)}")
        if item.get("category") not in CATEGORIES:
            errors.append(f"{where}: category must be one of {sorted(CATEGORIES)}")
        if not _is_int(item.get("limit")) or item["limit"] < 1:
            errors.append(f"{where}: limit must be >= 1")
        actions = item.get("actions")
        if not isinstance(actions, list) or not actions:
            errors.append(f"{where}: needs at least one action")
            continue
        for j, action in enumerate(actions):
            errors.extend(validate_action(action, f"{where}.actions[{j}]"))
    return errors
