import logging

import pygame

from .games import load_games
from .log import setup_logging
from .match import MatchError, play_match
from .settings import load_settings
from .ui_shop import run_shop

log = logging.getLogger("gauntlet.app")


def main():
    setup_logging()
    settings = load_settings()
    games, problems = load_games(settings.data_dir)
    for name, errs in problems.items():
        print(f"Skipped {name}: " + "; ".join(errs))
    if not games:
        print("No valid games found!")
        return 1

    pygame.init()
    flags = pygame.FULLSCREEN if settings.fullscreen else 0
    screen = pygame.display.set_mode((settings.width, settings.height), flags)
    game = games[0]  # TODO(phase 2): game selection
    purchases, _remaining, start = run_shop(screen, game, settings.starting_points)
    if start:
        try:
            play_match(game, purchases, settings)
        except MatchError as e:
            log.error("Match failed: %s", e)
            print(f"Match failed: {e}")
            return 1
    pygame.quit()
    return 0
