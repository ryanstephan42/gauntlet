import json
import logging
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
        errors = []
        if not 1 <= self.player_count <= 4:
            errors.append("player_count must be between 1 and 4")
        if not 1 <= self.retroarch_port <= 65535:
            errors.append("retroarch_port must be 1-65535")
        if self.starting_points < 0:
            errors.append("starting_points must be >= 0")
        if self.width < 320 or self.height < 240:
            errors.append("window size too small")
        return errors


def load_settings(path=SETTINGS_FILE):
    """Load settings, falling back to defaults for missing/invalid values."""
    s = Settings()
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
    for err in s.validate():
        log.error("Invalid settings: %s", err)
    return s


def save_settings(settings, path=SETTINGS_FILE):
    with open(path, "w") as f:
        json.dump(asdict(settings), f, indent=2)
