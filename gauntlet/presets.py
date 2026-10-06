"""Preset library: known-good RAM maps/shops per game, generic items and challenge templates."""
import copy
import glob
import json
import os
import re

from .paths import app_root

TEMPLATES = [
    ("manual", "Manual (players report the winner)", {"mode": "manual"}),
    ("first_to", "First to N (versus)", {"mode": "versus", "win": {"type": "reach", "value": 3}}),
    ("last_standing", "Last one standing (versus)", {"mode": "versus", "win": {"type": "eliminate", "value": 0}}),
    ("high_score", "High-score race (versus, timed)",
     {"mode": "versus", "win": {"type": "compare", "order": "high"}, "time_limit": 120}),
    ("time_trial", "Time trial (turns: fastest to N)",
     {"mode": "turns", "win": {"type": "reach", "value": 1}, "time_limit": 300}),
    ("turn_score", "High score (turns, timed)",
     {"mode": "turns", "win": {"type": "compare", "order": "high"}, "time_limit": 120}),
    ("survival", "Survival (turns: last longest)",
     {"mode": "turns", "win": {"type": "eliminate", "value": 0}, "time_limit": 300}),
    ("coop_goal", "Co-op goal (team reaches N)", {"mode": "coop", "win": {"type": "reach", "value": 1},
                                                   "time_limit": 300, "on_timeout": "lose"}),
]


def preset_dir():
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)), "presets")
    return here if os.path.isdir(here) else os.path.join(app_root(), "gauntlet", "presets")


def normalize_title(text):
    text = os.path.splitext(os.path.basename(text or ""))[0]
    text = re.sub(r"[\(\[].*?[\)\]]", " ", text)
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def load_presets():
    out = []
    for path in sorted(glob.glob(os.path.join(preset_dir(), "*.json"))):
        if os.path.basename(path) == "generic.json":
            continue
        try:
            with open(path) as f:
                data = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "game" in data:
            out.append(data)
    return out


def match_presets(system, rom):
    title = normalize_title(rom)
    hits = []
    for p in load_presets():
        if system and p.get("system") != system:
            continue
        if any(m in title or title in m for m in p.get("match", []) if title):
            hits.append(p)
    return hits


def generic_items():
    try:
        with open(os.path.join(preset_dir(), "generic.json")) as f:
            return json.load(f).get("items", [])
    except (OSError, ValueError):
        return []


def template(template_id):
    for tid, _label, data in TEMPLATES:
        if tid == template_id:
            return copy.deepcopy(data)
    raise KeyError(template_id)


def game_from_preset(preset, core=None, rom=None, name=None, image=None):
    game = copy.deepcopy(preset["game"])
    game["schema_version"] = 2
    meta = game.setdefault("meta", {})
    if core:
        meta["core"] = core
    if rom:
        meta["rom"] = rom
    if name:
        meta["name"] = name
    if image:
        meta["image"] = image
    return game
