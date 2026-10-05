"""Challenge start states: RetroArch save states that skip intros (e.g. straight to character select).

A challenge names a file in `start_state`. It is looked up in the user's start-states folder first
(captures and imported packs land there), then in the folder bundled with the app. Before launch
the file is copied to `<content>.state<ENTRY_SLOT>` in RetroArch's savestate directory and
RetroArch is started with `--entryslot`.
"""
import glob
import logging
import os
import shutil

from .games import slugify
from .paths import app_root

log = logging.getLogger("gauntlet.startstate")

ENTRY_SLOT = 1
BUNDLED_DIR = "start_states"


def valid_name(name):
    return (isinstance(name, str) and bool(name.strip()) and name == os.path.basename(name)
            and "/" not in name and "\\" not in name and name not in (".", ".."))


def search_dirs(settings):
    dirs = []
    for d in (settings.start_states_path, os.path.join(app_root(), BUNDLED_DIR)):
        if d and os.path.abspath(d) not in [os.path.abspath(x) for x in dirs]:
            dirs.append(d)
    return dirs


def find_start_state(settings, challenge):
    """-> (path or None, name or None). name is set when the challenge asks for a state."""
    name = (challenge or {}).get("start_state")
    if not name or not valid_name(name):
        return None, None
    for d in search_dirs(settings):
        path = os.path.join(d, name)
        if os.path.isfile(path):
            return path, name
    return None, name


def content_stem(rom):
    """RetroArch names states after the content file without its extension."""
    return os.path.splitext(os.path.basename(rom))[0]


def stage(src, savestate_dir, rom, slot=ENTRY_SLOT):
    """Copy `src` to where RetroArch's --entryslot looks for it. Returns the staged path."""
    os.makedirs(savestate_dir, exist_ok=True)
    dest = os.path.join(savestate_dir, f"{content_stem(rom)}.state{slot}")
    shutil.copyfile(src, dest)
    return dest


def state_filename(game, challenge):
    return f"{slugify(game['meta'].get('name') or 'game')}_{slugify(challenge.get('id') or 'main')}.state"


def newest_state(folder, after=0.0):
    """Newest save state file (any slot) in `folder` modified at/after `after`, or None."""
    files = [f for f in glob.glob(os.path.join(folder, "**", "*.state*"), recursive=True)
             if not f.endswith((".png", ".tmp")) and os.path.isfile(f) and os.path.getmtime(f) >= after]
    return max(files, key=os.path.getmtime) if files else None


def clear_folder(folder):
    os.makedirs(folder, exist_ok=True)
    for f in glob.glob(os.path.join(folder, "**", "*.state*"), recursive=True):
        try:
            os.remove(f)
        except OSError:
            log.debug("could not remove %s", f)


def save_capture(src, settings, name):
    """Copy a captured state into the user's start-states folder. Returns the destination."""
    dest_dir = settings.start_states_path
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, name)
    shutil.copyfile(src, dest)
    log.info("Saved start state %s", dest)
    return dest
