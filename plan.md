# Gauntlet Improvement Plan

## Targets
- Desktop, gamepad-first; 2 players baseline, up to 4 supported.
- pygame UI + RetroArch emulation.
- Adding a game/challenge should need no hand-edited JSON.

## Phase 0: Foundation and cleanup — MOSTLY DONE
1. [~] Package split: done for `settings`, `schema`, `games`, `retroarch`, `economy`, `match`, `app`, `log`, `ui_shop`; `gauntlet.py` is a thin entry point. Remaining modules (`referee`, `ui/`, `wizard/`, `state`) belong to later phases.
2. [x] Settings file (`settings.json`) with defaults and validation. [ ] Remaining: first-run RetroArch/core auto-detection beyond PATH lookup; actually use `core_dir`, `rom_dir`, `assets_dir`, `player_count`.
3. [x] Versioned config schema + validation; bad files are skipped with logged reasons.
4. [~] Fix data: [x] `configs/` path bug fixed; [x] `m64.json` no longer an SF2 copy. [ ] Remaining: real, verified Mario 64 referee/shop addresses and its own cover art.
5. [~] Logging and error handling: [x] `logging` module + log file, bare `except` removed. [ ] Remaining: show config/match errors on screen (needs Phase 1 UI framework); surface skipped games to the user.
6. [x] Tests (pytest: schema, shop, loader, settings, UDP client) and README. [ ] Remaining: referee tests (once the referee exists).

Note: UDP command formats (`WRITE_CORE_MEMORY` hex values, `READ_CORE_MEMORY` reply parsing) and readiness polling are untested against a real RetroArch; verify on first real run.

## Phase 1: Input and UI framework (gamepad first) — IN PROGRESS (mouse input and cover-art/card/button rendering remain)
1. Input abstraction: keyboard/mouse/gamepad mapped to up/down/left/right/confirm/back/start; joystick hot-plug; "press A to join" controller-to-player-slot assignment (2-4 players).
2. Screen/state manager (stack, transitions) and a central theme.
3. Widgets: scrolling focusable lists, game card grid with cover art, buttons, modals, toasts, text wrapping, progress bar.
4. On-screen keyboard for gamepad text entry.
5. Resolution-independent layout; control-hint footer per device.

## Phase 2: Core gameplay loop
1. Session model: players (name, colour, controller, points, inventory, score), playlist, rounds, history.
2. Screens: Main menu -> Player setup -> Game/playlist select -> Shop -> Pre-match summary -> Match -> Results -> Standings -> Next round / Final.
3. Playlist modes: single game, N-round gauntlet (random/fixed), 4-player tournament bracket.
4. Per-player shop: independent buying per controller, buffs for self / debuffs for opponents (target picker), categories, limits, refunds, item cap per match.
5. Economy: configurable start points and payouts, catch-up bonuses, streaks, wagers, persistence, save/resume.
6. Flow fixes: quitting the shop must not launch the game; window close exits cleanly and kills RetroArch.

## Phase 3: Real emulator integration and referee
1. RetroArch client: READ/WRITE_CORE_MEMORY, GET_STATUS, PAUSE_TOGGLE, QUIT; poll readiness instead of sleeping; ensure `network_cmd_enable`; per-match config.
2. Action-type handler registry: multi-byte/endian/bitmask memory writes, freeze/repeat/conditional, timed effects, retroarch_config, input_remap, shaders.
3. Referee thread: equals/greater/bit-set/compare-between-players/first-to-X, best-of-N, draws, timeouts, manual override, forfeit hotkey.
4. Multi-player matches: per-player addresses, 3-4 player support, controller port assignment.
5. Controller pass-through: RetroArch owns controllers during matches; Gauntlet pauses polling.
6. Robustness: crash handling, missing ROM/core, injection retries, UI error reporting.

## Phase 4: Setup wizard
1. Add Game wizard: system -> core detection -> ROM browser -> name/art -> referee template (+test) -> shop items from presets/custom (+live test) -> review/validate/save.
2. Live memory tooling: connection indicator, "test this write", RAM watcher with search-by-value / changed / unchanged.
3. Edit/duplicate/delete/import/export (zip packs); startup validator and games health list.
4. Preset library of known addresses for popular games.
5. Challenge builder: time trials, high-score races, co-op goals.

## Phase 5: Polish
Audio, animations, results/stats screen, persistent leaderboards, achievements, TV-friendly view, settings screens (input remap/audio/display), PyInstaller packaging, CI for lint+tests.

## Delivery order
1. M1: Phase 0 + Phase 1 input/screen manager.
2. M2: Phase 2 + Phase 3 client and referee (playable 2-player loop).
3. M3: Phase 4 wizard.
4. M4: 3-4 player extras and Phase 5.

## Risks / decisions
- RAM addresses per game are the hardest part; presets + watcher are key.
- Controller routing: recommend RetroArch owning input during matches.
- Platform (Windows vs Linux) affects paths.
- 4 players only for games that support it; 2 is the baseline.
