import json
import logging
import os
import re

from .schema import SCHEMA_VERSION, normalize_game, validate_game

log = logging.getLogger("gauntlet.games")


def load_games(data_dir):
    """Load, migrate and validate every *.json game config; invalid ones are skipped.

    Returns (games, problems) where problems maps filename -> list of errors.
    """
    games, problems = [], {}
    if not os.path.isdir(data_dir):
        os.makedirs(data_dir, exist_ok=True)
        log.warning("Created %s. Please add game JSON files.", data_dir)
        return games, problems

    for filename in sorted(os.listdir(data_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(data_dir, filename)
        try:
            with open(path, "r") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            problems[filename] = [f"cannot read: {e}"]
            log.error("Failed to load %s: %s", filename, e)
            continue
        errors = validate_game(data)
        if errors:
            problems[filename] = errors
            for err in errors:
                log.error("%s: %s", filename, err)
            continue
        game = normalize_game(data)
        game["_file"] = filename
        game["_path"] = path
        games.append(game)
    return games, problems


def strip_private(game):
    return {k: v for k, v in game.items() if not k.startswith("_")}


def slugify(name):
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    return slug or "game"


def unique_filename(data_dir, name):
    base = slugify(name)
    candidate, n = f"{base}.json", 2
    while os.path.exists(os.path.join(data_dir, candidate)):
        candidate, n = f"{base}_{n}.json", n + 1
    return candidate


def save_game(game, data_dir, filename=None):
    """Validate and atomically write a game. Returns (filename, errors)."""
    data = strip_private(game)
    data["schema_version"] = SCHEMA_VERSION
    errors = validate_game(data)
    if errors:
        return None, errors
    os.makedirs(data_dir, exist_ok=True)
    filename = filename or game.get("_file") or unique_filename(data_dir, data["meta"]["name"])
    path = os.path.join(data_dir, filename)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, path)
    log.info("Saved game %s", path)
    return filename, []


def duplicate_game(game, data_dir):
    data = strip_private(game)
    data["meta"] = dict(data["meta"], name=data["meta"]["name"] + " (copy)")
    return save_game(data, data_dir, unique_filename(data_dir, data["meta"]["name"]))


def delete_game(game, data_dir):
    path = os.path.join(data_dir, game["_file"])
    if os.path.exists(path):
        os.remove(path)
        log.info("Deleted game %s", path)
        return True
    return False


def game_health(game, launcher):
    """Human-readable problems that would stop this game from launching."""
    _core, _rom, errors = launcher.resolve(game)
    return errors


def get_challenge(game, challenge_id=None):
    challenges = game.get("challenges") or []
    for ch in challenges:
        if ch.get("id") == challenge_id:
            return ch
    return challenges[0] if challenges else {"id": "main", "name": "Match", "mode": "manual"}
