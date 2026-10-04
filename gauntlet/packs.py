"""Zip game packs: export games (+ art + RetroArch config files) and import them safely."""
import json
import os
import zipfile

from .games import strip_private, unique_filename
from .schema import normalize_game, validate_game


def _referenced_configs(game):
    files = set()
    for item in game.get("shop", []):
        for a in item.get("actions", []):
            if a.get("type") == "retroarch_config" and a.get("config_file"):
                files.add(a["config_file"])
    return files


def export_pack(games, out_path, assets_dir, config_dir):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for g in games:
            data = strip_private(g)
            name = g.get("_file") or unique_filename("/nonexistent", data["meta"]["name"])
            z.writestr(f"games/{name}", json.dumps(data, indent=2))
            image = data["meta"].get("image")
            if image and os.path.isfile(os.path.join(assets_dir, image)):
                z.write(os.path.join(assets_dir, image), f"assets/{image}")
            for cfg in _referenced_configs(data):
                if os.path.isfile(os.path.join(config_dir, cfg)):
                    z.write(os.path.join(config_dir, cfg), f"config/{cfg}")
    return out_path


def _safe_name(name):
    base = os.path.basename(name)
    if not base or base in (".", "..") or base != name.split("/")[-1]:
        return None
    return base


def import_pack(zip_path, data_dir, assets_dir, config_dir):
    """Returns (imported game names, errors). Never overwrites existing files."""
    imported, errors = [], []
    with zipfile.ZipFile(zip_path) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            parts = info.filename.split("/")
            if len(parts) != 2 or parts[0] not in ("games", "assets", "config") or ".." in parts:
                errors.append(f"skipped {info.filename}")
                continue
            name = _safe_name(parts[1])
            if not name:
                errors.append(f"skipped {info.filename}")
                continue
            if parts[0] == "games":
                try:
                    data = json.loads(z.read(info))
                except ValueError as e:
                    errors.append(f"{name}: invalid JSON ({e})")
                    continue
                problems = validate_game(data)
                if problems:
                    errors.append(f"{name}: " + "; ".join(problems[:3]))
                    continue
                data = normalize_game(data)
                os.makedirs(data_dir, exist_ok=True)
                target = name if not os.path.exists(os.path.join(data_dir, name)) else \
                    unique_filename(data_dir, data["meta"]["name"])
                with open(os.path.join(data_dir, target), "w") as f:
                    json.dump(data, f, indent=2)
                imported.append(data["meta"]["name"])
            else:
                folder = assets_dir if parts[0] == "assets" else config_dir
                os.makedirs(folder, exist_ok=True)
                dest = os.path.join(folder, name)
                if not os.path.exists(dest):
                    with open(dest, "wb") as f:
                        f.write(z.read(info))
    return imported, errors
