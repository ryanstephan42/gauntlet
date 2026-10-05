"""Entry point: load settings, open the pygame UI on the main menu."""
import argparse
import logging
import os
import sys

from .log import setup_logging
from .paths import default_state_dir, ensure_dir, is_frozen, seed_data_dir
from .settings import SETTINGS_FILE, load_settings

log = logging.getLogger("gauntlet.app")


def settings_location(path=None):
    """Explicit path > ./settings.json (portable/dev checkout) > per-user state dir."""
    if path:
        return os.path.abspath(os.path.expanduser(path))
    if os.path.exists(SETTINGS_FILE):
        return os.path.abspath(SETTINGS_FILE)
    return os.path.join(default_state_dir(), SETTINGS_FILE)


def parse_args(argv):
    ap = argparse.ArgumentParser(prog="gauntlet", description="Couch-competitive retro gaming gauntlet")
    ap.add_argument("--settings", help="settings.json to use (created on first save)")
    ap.add_argument("--windowed", action="store_true", help="ignore the fullscreen setting")
    ap.add_argument("--no-sound", action="store_true", help="disable audio")
    ap.add_argument("--debug", action="store_true", help="verbose logging")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    path = settings_location(args.settings)
    settings = load_settings(path)
    log_file = os.path.join(ensure_dir(settings.state_path), "gauntlet.log")
    setup_logging(logging.DEBUG if args.debug else logging.INFO, log_file)
    ensure_dir(os.path.dirname(path))
    if args.windowed:
        settings.fullscreen = False
    if is_frozen():
        seeded = seed_data_dir(settings.data_path)
        if seeded:
            log.info("Installed bundled games into %s: %s", settings.data_path, ", ".join(seeded))
    log.info("Settings: %s, games: %s, state: %s", path, settings.data_path, settings.state_path)

    from .ui import flow
    from .ui.app import App
    app = App(settings, settings_path=path, audio=not args.no_sound)
    app.run(flow.MainMenu)
    return 0
