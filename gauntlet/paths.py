"""Filesystem locations: app root (repo or PyInstaller bundle) and per-user state dir."""
import os
import shutil
import sys


def app_root():
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def is_frozen():
    return bool(getattr(sys, "frozen", False))


def data_root():
    """Base for relative data paths: the checkout, or the writable per-user dir in a frozen build."""
    return default_state_dir() if is_frozen() else app_root()


def default_state_dir():
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "Gauntlet")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/Gauntlet")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "gauntlet")


def resolve(path, base=None):
    """Expand ~ and make relative paths absolute against `base` (default: data_root())."""
    if not path:
        return path
    path = os.path.expanduser(path)
    if os.path.isabs(path):
        return path
    if os.path.exists(path):
        return os.path.abspath(path)
    return os.path.join(base or data_root(), path)


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def seed_data_dir(dest, src=None):
    """First run of a frozen build: copy the bundled game configs into the (new) user data dir.

    Does nothing once `dest` exists, so games the user deleted are not brought back."""
    src = src or os.path.join(app_root(), "gauntlet_data")
    if os.path.exists(dest) or not os.path.isdir(src):
        return []
    ensure_dir(dest)
    copied = []
    for name in sorted(os.listdir(src)):
        if name.endswith(".json"):
            shutil.copy2(os.path.join(src, name), os.path.join(dest, name))
            copied.append(name)
    return copied
