import json
import logging
import math
import os
import shutil
from dataclasses import dataclass, asdict, fields

log = logging.getLogger("gauntlet.settings")

SETTINGS_FILE = "settings.json"


def _detect_retroarch():
    return shutil.which("retroarch") or "/bin/retroarch"


@dataclass
class Settings:
    retroarch_path: str = ""
    retroarch_host: str = "127.0.0.1"
    retroarch_port: int = 55355
    data_dir: str = "gauntlet_data"
    rom_dir: str = "roms"
    core_dir: str = "/lib/libretro"
    config_dir: str = "config"
    assets_dir: str = "assets"
    player_count: int = 2
    starting_points: int = 10
    fullscreen: bool = False
    width: int = 1024
    height: int = 768
    boot_timeout: float = 30.0

    def validate(self):
        return list(_range_errors(self).values())


def _range_errors(settings):
    errors = {}
    if not _is_int(settings.player_count) or not 1 <= settings.player_count <= 4:
        errors["player_count"] = "player_count must be between 1 and 4"
    if not _is_int(settings.retroarch_port) or not 1 <= settings.retroarch_port <= 65535:
        errors["retroarch_port"] = "retroarch_port must be 1-65535"
    if not _is_int(settings.starting_points) or settings.starting_points < 0:
        errors["starting_points"] = "starting_points must be >= 0"
    if not _is_int(settings.width) or settings.width < 320:
        errors["width"] = "width must be at least 320"
    if not _is_int(settings.height) or settings.height < 240:
        errors["height"] = "height must be at least 240"
    if not _is_positive_finite_number(settings.boot_timeout):
        errors["boot_timeout"] = "boot_timeout must be a positive finite number"
    return errors


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_positive_finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value) and value > 0
    except OverflowError:
        return False


def load_settings(path=SETTINGS_FILE):
    """Load settings, falling back to defaults for missing/invalid values."""
    s = Settings()
    defaults = Settings()
    if os.path.exists(path):
        try:
            with open(path, "r") as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                raise ValueError("top level must be an object")
            known = {f.name: f.type for f in fields(Settings)}
            for key, val in raw.items():
                if key not in known:
                    log.warning("Unknown setting ignored: %s", key)
                    continue
                current = getattr(s, key)
                ok = isinstance(val, type(current)) and (
                    isinstance(val, bool) == isinstance(current, bool)
                )
                if isinstance(current, float) and isinstance(val, int) and not isinstance(val, bool):
                    ok = True
                if not ok:
                    log.warning("Bad type for setting %s, using default", key)
                    continue
                setattr(s, key, val)
        except (OSError, ValueError) as e:
            log.error("Failed to read %s: %s (using defaults)", path, e)
    if not s.retroarch_path:
        s.retroarch_path = _detect_retroarch()
    for field, err in _range_errors(s).items():
        log.error("Invalid settings: %s (using default)", err)
        setattr(s, field, getattr(defaults, field))
    return s


def save_settings(settings, path=SETTINGS_FILE):
    with open(path, "w") as f:
        json.dump(asdict(settings), f, indent=2)
