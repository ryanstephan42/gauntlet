# Gauntlet Improvement Plan

## Targets
- Desktop, gamepad-first; 2 players baseline, up to 4 supported.
- pygame UI + RetroArch emulation.
- Adding a game/challenge should need no hand-edited JSON.

## Phase 0: Foundation and cleanup — DONE
1. [x] Package split: `gauntlet.py` is a thin entry point; engine modules (`settings`, `schema`, `games`, `retroarch`, `memory`, `actions`, `referee`, `match`, `session`, `playlist`, `economy`, `stats`, ...) plus the `ui/` package.
2. [x] Settings file with defaults and validation; RetroArch/core/ROM auto-detection (RetroDECK and libretro Flatpak, PATH, common folders) with a preferred-install choice.
3. [x] Versioned config schema (v2, v1 migrated automatically); bad files are skipped with logged reasons and shown in the games health list.
4. [x] Data: SM64 config rebuilt from live-verified addresses; SNES configs (MK2, Super Bomberman, Super Mario Kart) added.
5. [x] Logging to a log file; errors shown on screen (toasts, match/launch errors, skipped games).
6. [x] Tests (pytest, headless UI with a fake RetroArch) and README.

## Phase 1: Input and UI framework (gamepad first) — DONE
1. Input abstraction: keyboard/mouse/gamepad mapped to up/down/left/right/confirm/back/start; joystick hot-plug; "press A to join" controller-to-player-slot assignment (2-4 players).
2. Screen/state manager (stack, transitions) and a central theme.
3. Widgets: scrolling focusable lists, game card grid with cover art, buttons, modals, toasts, text wrapping, progress bar.
4. On-screen keyboard for gamepad text entry.
5. Resolution-independent layout; control-hint footer per device.

## Phase 2: Core gameplay loop — DONE
1. Session model: players (name, colour, controller, points, inventory, score), playlist, rounds, history.
2. Screens: Main menu -> Player setup -> Game/playlist select -> Shop -> Pre-match summary -> Match -> Results -> Standings -> Next round / Final.
3. Playlist modes: single game, N-round gauntlet (random/fixed), 4-player tournament bracket.
4. Per-player shop: independent buying per controller, buffs for self / debuffs for opponents (target picker), categories, limits, refunds, item cap per match.
5. Economy: configurable start points and payouts, catch-up bonuses, streaks, wagers, persistence, save/resume.
6. Flow fixes: quitting the shop must not launch the game; window close exits cleanly and kills RetroArch.

## Phase 3: Real emulator integration and referee — DONE
Verified live on RetroDECK RetroArch 1.22.2. Cores without a memory map (snes9x) fall back to READ/WRITE_CORE_RAM. Input remaps and shaders go through `retroarch_config` actions.
1. RetroArch client: READ/WRITE_CORE_MEMORY, GET_STATUS, PAUSE_TOGGLE, QUIT; poll readiness instead of sleeping; ensure `network_cmd_enable`; per-match config.
2. Action-type handler registry: multi-byte/endian/bitmask memory writes, freeze/repeat/conditional, timed effects, retroarch_config, input_remap, shaders.
3. Referee thread: equals/greater/bit-set/compare-between-players/first-to-X, best-of-N, draws, timeouts, manual override, forfeit hotkey.
4. Multi-player matches: per-player addresses, 3-4 player support, controller port assignment.
5. Controller pass-through: RetroArch owns controllers during matches; Gauntlet pauses polling.
6. Robustness: crash handling, missing ROM/core, injection retries, UI error reporting.

## Phase 4: Setup wizard — DONE
Challenges can also start from a RetroArch save state (`start_state`), captured in the challenge editor.
1. Add Game wizard: system -> core detection -> ROM browser -> name/art -> referee template (+test) -> shop items from presets/custom (+live test) -> review/validate/save.
2. Live memory tooling: connection indicator, "test this write", RAM watcher with search-by-value / changed / unchanged.
3. Edit/duplicate/delete/import/export (zip packs); startup validator and games health list.
4. Preset library of known addresses for popular games.
5. Challenge builder: time trials, high-score races, co-op goals.

## Phase 5: Polish — DONE
Audio, animations, results/stats screen, persistent leaderboards, achievements, TV-friendly view, settings screens (input remap/audio/display), PyInstaller packaging, CI for lint+tests.

## Phase 6: Simultaneous play (one emulator instance per player) — DONE
Implemented as a setting (`simultaneous_play`, default on) rather than a new mode: `turns` challenges become races when every player has their own controller, and fall back to turns (with the reason shown) otherwise. On Hyprland/Sway the race windows are floated onto their tiles. Live-tested with 2× SM64 on RetroDECK under Hyprland.
Single-player challenges currently run as turns. Instead, every player plays the same challenge at the same time, each in their own RetroArch instance, and the first to clear it ends the race for everyone.
1. Multi-instance launcher: one RetroArch process per player, each with its own network command port, config (only that player's controller/keys bound to port 1), savestate/SRAM folders and window. Optionally tile the windows (e.g. side by side for 2, a 2x2 grid for 3-4).
2. Input isolation: each instance reads only its own player's input. Gamepads map one device per instance (`input_player1_joypad_index`). Keyboard players use split keyboard maps, which need a focus-independent input driver (e.g. `udev`/`raw` on Linux) or a single keyboard player. Document the limits for each platform.
3. Parallel referee: one memory client per instance polls each player's metric. The first player to meet the win condition wins. All instances close together, or pause and then close after `close_delay`. Ready gates, time limits and `on_timeout` scoring apply per instance; on a timeout, compare players' metrics.
4. Start states load into every instance, so all players start in the same place. Shop effects target the right instance (self vs opponents).
5. Challenge/setting: add `mode: "race"` (simultaneous) next to `turns`. Default single-player challenges to race when enough controllers or instances are available, and fall back to turns otherwise. Add a setting to force turns.
6. UI: a match screen showing each player's live status, then results. Crash or close handling for one instance (forfeit that player and keep the race going for the rest).
7. Tests: the fake RetroArch running N instances on separate ports, race win and timeout cases, and a live run of 2× SM64 on RetroDECK.

## Delivery order
1. M1: Phase 0 + Phase 1 input/screen manager.
2. M2: Phase 2 + Phase 3 client and referee (playable 2-player loop).
3. M3: Phase 4 wizard.
4. M4: 3-4 player extras and Phase 5.
5. M5: Phase 6 simultaneous play.

## Risks / decisions
- RAM addresses per game are the hardest part; presets + watcher are key.
- Controller routing: recommend RetroArch owning input during matches.
- Platform (Windows vs Linux) affects paths.
- 4 players only for games that support it; 2 is the baseline.
