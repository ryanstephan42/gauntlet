import json
import logging
import os

from .schema import validate_game

log = logging.getLogger("gauntlet.games")


def load_games(data_dir):
    """Load and validate every *.json game config; invalid ones are skipped.

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
        data["_file"] = filename
        games.append(data)
    return games, problems
