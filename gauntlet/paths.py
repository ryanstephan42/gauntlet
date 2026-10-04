"""Filesystem locations: app root (repo or PyInstaller bundle) and per-user state dir."""
import os
import sys


def app_root():
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_state_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Gauntlet")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Gauntlet")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "gauntlet")


def resolve(path, base=None):
    """Expand ~ and make relative paths absolute against `base` (default: app root)."""
    if not path:
        return path
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)
    return os.path.join(base or app_root(), path)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path
