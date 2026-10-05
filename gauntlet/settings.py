import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field, fields

from .paths import default_state_dir, ensure_dir, resolve

log = logging.getLogger("gauntlet.settings")

SETTINGS_FILE = "settings.json"


@dataclass
class Settings:
    # RetroArch: `retroarch_command` is an argv prefix (e.g. ["flatpak", "run", ...]);
    # `retroarch_path` is a plain binary. Both empty = auto-detect.
    retroarch_path: str = ""
    preferred_install: str = ""  # label of a detected install to prefer ("" = first found)
    retroarch_command: list = field(default_factory=list)
    retroarch_host: str = "127.0.0.1"
    retroarch_port: int = 55355
    # Extra retroarch.cfg keys for every launch, e.g. {"input_joypad_driver": "null"}
    retroarch_overrides: dict = field(default_factory=dict)
    # Directories (empty rom/core dir = auto-detect)
    data_dir: str = "gauntlet_data"
    rom_dir: str = ""
    core_dir: str = ""
    config_dir: str = "config"
    assets_dir: str = "assets"
    start_states_dir: str = "start_states"
    state_dir: str = ""
    # Players / economy
    player_count: int = 2
    starting_points: int = 10
    win_points: int = 5
    loss_points: int = 1
    draw_points: int = 2
    catchup_step: int = 5
    catchup_max: int = 3
    streak_bonus: int = 1
    streak_max: int = 3
    max_items: int = 3
    wagers: bool = True
    # Display / audio / input
    fullscreen: bool = False
    width: int = 1024
    height: int = 768
    tv_mode: bool = False
    sound: bool = True
    volume: float = 0.6
    split_keyboard: bool = False
    key_bindings: dict = field(default_factory=dict)
    button_bindings: dict = field(default_factory=dict)
    # Match behaviour
    boot_timeout: float = 30.0
    poll_interval: float = 0.2
    close_delay: float = 3.0
    assign_ports: bool = True

    def validate(self):
        return list(_range_errors(self).values())

    # Resolved locations -------------------------------------------------
    @property
    def state_path(self):
        return ensure_dir(resolve(self.state_dir) if self.state_dir else default_state_dir())

    @property
    def data_path(self):
        return resolve(self.data_dir)

    @property
    def assets_path(self):
        return resolve(self.assets_dir)

    @property
    def start_states_path(self):
        return resolve(self.start_states_dir)

    @property
    def config_path(self):
        return resolve(self.config_dir)

    def sub_state(self, *parts):
        return ensure_dir(os.path.join(self.state_path, *parts))


_INT_MIN = {
    "starting_points": 0, "win_points": 0, "loss_points": 0, "draw_points": 0,
    "catchup_step": 1, "catchup_max": 0, "streak_bonus": 0, "streak_max": 0, "max_items": 0,
}


def _range_errors(settings):
    errors = {}
    if not _is_int(settings.player_count) or not 1 <= settings.player_count <= 4:
        errors["player_count"] = "player_count must be between 1 and 4"
    if not _is_int(settings.retroarch_port) or not 1 <= settings.retroarch_port <= 65535:
        errors["retroarch_port"] = "retroarch_port must be 1-65535"
    for name, lo in _INT_MIN.items():
        value = getattr(settings, name)
        if not _is_int(value) or value < lo:
            errors[name] = f"{name} must be >= {lo}"
    if not _is_int(settings.width) or settings.width < 320:
        errors["width"] = "width must be at least 320"
    if not _is_int(settings.height) or settings.height < 240:
        errors["height"] = "height must be at least 240"
    for name in ("boot_timeout", "poll_interval"):
        if not _is_positive_finite_number(getattr(settings, name)):
            errors[name] = f"{name} must be a positive finite number"
    if not _is_number(settings.close_delay) or not 0 <= settings.close_delay <= 60:
        errors["close_delay"] = "close_delay must be 0-60"
    if not _is_number(settings.volume) or not 0 <= settings.volume <= 1:
        errors["volume"] = "volume must be 0.0-1.0"
    if not all(isinstance(k, str) and isinstance(v, (str, int, float, bool))
               for k, v in settings.retroarch_overrides.items()):
        errors["retroarch_overrides"] = "retroarch_overrides must map names to strings/numbers/booleans"
    if not all(isinstance(p, str) for p in settings.retroarch_command):
        errors["retroarch_command"] = "retroarch_command must be a list of strings"
    return errors


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _is_positive_finite_number(value):
    return _is_number(value) and value > 0


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
            known = {f.name for f in fields(Settings)}
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
                    val = float(val)
                if not ok:
                    log.warning("Bad type for setting %s, using default", key)
                    continue
                setattr(s, key, val)
        except (OSError, ValueError) as e:
            log.error("Failed to read %s: %s (using defaults)", path, e)
    for name, err in _range_errors(s).items():
        log.error("Invalid settings: %s (using default)", err)
        setattr(s, name, getattr(defaults, name))
    return s


def save_settings(settings, path=SETTINGS_FILE):
    tmp = f"{path}.tmp"
    with open(tmp, "w") as f:
        json.dump(asdict(settings), f, indent=2)
    os.replace(tmp, path)
