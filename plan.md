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

## Phase 7: Match presentation (stage layout) — DONE
Make a match look like one screen: the games across the top and a live scoreboard below, so players can see their opponent's progress at a glance.
1. Stage layout — DONE (commit `4d429b8`). On Hyprland/Sway every match floats the game windows into the top of the monitor (one wide window for versus/turns, side by side for a race). Gauntlet's own window becomes a bottom strip (`stage_hud_percent`, 25%) showing each player's live metric as a number and bar, their power-ups (buffs green, debuffs red), and the challenge name, clock and description in the middle. Gauntlet's window is restored afterwards (tiled, floating or fullscreen). Setting: `stage_layout`. Live-tested: MK2 versus (windowed and fullscreen) and a 2-player SMW race.
2. Player-colour window borders — DONE (live-tested with a 2-player SMW race on Hyprland). Frame each player's game window in their colour so the windows are easy to tell apart. Hyprland only (`hyprctl dispatch setprop <win> border_size / active_border_color / inactive_border_color`, verified on 0.56.2); Sway has no per-window border colours. The window is shrunk by the border width so the border fills its tile. Shared windows (versus) get no player colour; in turns the window takes the current player's colour. Setting: `match_border` (px, default 6, 0 = off).
3. Start countdown — DONE (live-tested: MK2 versus and a 2-player SMW race on Hyprland). Before the clock starts, a 3-2-1 countdown runs over the game's paused first frame. Each RetroArch is paused (`PAUSE_TOGGLE`, checked against `GET_STATUS` because it only toggles) as soon as it answers, so an early-booting race window gets no head start. With a start state the match config pins `state_slot` to the entry slot and `LOAD_STATE` rewinds every paused window to the identical frame. A paused RetroArch draws nothing new, so each tick sends `FRAMEADVANCE` to paint the loaded state into the freshly placed window. 3, 2, 1, GO show big in the scoreboard strip (with a beep); without the strip they go to RetroArch's OSD instead, since paused OSD messages only appear on the advanced frame. Then every instance is unpaused back to back and the referee clock starts. Applies to versus, turns (each turn) and races (all instances together). Setting: `start_countdown` (seconds, default 3, 0 = off). The fake RetroArch freezes its scripted event clock while paused, and tests cover the command order, the clock starting after GO, race fairness, rewinding and cancelling mid-countdown. Cold boots without a start state (e.g. MK2) still pause on a black boot frame.
4. In-window emulation prototype — DONE (feasibility report; nothing in the app changed). `prototypes/inwindow/`: `libretro.py` is a ctypes libretro frontend (each instance gets a private copy of the core `.so`, because cores keep global state; it reads RetroArch `.state` files: RZIP chunks → RASTATE → `MEM` chunk), and `demo.py` has three modes, `bench`, `core` and `play`. `play` runs two SMW instances from `start_states/smw_yi1.state` plus a live strip in one pygame window, with mixed audio and pad/keyboard input; `--auto` replays two scripted runs found by a no-death backtracking search. Measured on an i7-7700 at 2560x1440:
   - SNES (snes9x 1.63): booting 2 instances plus the start state takes 70 ms. `retro_run` costs 0.8 ms per instance, frame→Surface 0.03 ms. Input reaches the game on the next emulated frame (RIGHT changes Mario's x speed after 1 frame; the frontend adds no buffering), and a RAM read costs 0.05 µs (no UDP round trip). Two instances given the same state and inputs stay byte-identical after 1200 frames, so a race is exactly fair.
   - Drawing: full-resolution software scaling costs ~10 ms per frame (draw+flip), with 13–26 late frames in 12 s. With `--scaled` (draw at 1280x720 and let SDL's GPU renderer scale) it drops to 2.8 ms with 0 late frames, for 4.9 ms total work per frame.
   - Audio: one SDL device fed from a ring buffer mixing both cores at half volume each. Latency is a ~27–40 ms median queue, with 3–5 underruns in 10–12 s (at start-up). A production version should resample to the device rate and use the audio clock for pacing.
   - Other systems, 2 instances per frame against a 16.7 ms budget: NES fceumm 0.8 ms, GBA mGBA 0.9 ms, PS1 SwanStation software renderer 1.4 ms (Tekken 3, BIOS from `~/retrodeck/bios`). None of these need GL, and every pair stayed identical.
   - N64 (9 of the 21 games in rotation) is the blocker:
     - With `mupen64plus-rdp-plugin=angrylion` (software RDP) the core does not ask for GL and outputs XRGB8888 at 640x240/480. But two instances cost 20–23 ms per frame on this CPU (mean, threaded or not; the RSP choice doesn't matter, the RDP dominates), so 60 fps for two players doesn't fit.
     - Hardware rendering (GLideN64/ParaLLEl) needs a GL or Vulkan context shared by two cores, each with its own FBO, plus the strip drawn through GL.
     - mupen runs the emulator on a libco coroutine stack. Python 3.14's stack-pointer recursion guard aborts ("Unrecoverable stack overflow") when a ctypes callback runs there, so N64 needs a small C callback shim; it worked only under Python 3.13 via uv.
   - **Lost compared to RetroArch:** shaders/overlays, hotkeys and the menu, RetroDECK's per-system settings and controller autoconfig, netplay, run-ahead, and RetroArch's audio resampling and sync.
   - **Recommendation:** keep the RetroArch stage layout (7.1–7.3) as the default; it already gives the one-screen look, live metrics and fair starts on every system. An in-window mode is realistic for SNES/NES/GBA/PS1 (12 of 21 games) as an opt-in later. N64 in-window would need the C shim plus a GL HW-render path (or RetroArch per N64 game).

## Delivery order
1. M1: Phase 0 + Phase 1 input/screen manager.
2. M2: Phase 2 + Phase 3 client and referee (playable 2-player loop).
3. M3: Phase 4 wizard.
4. M4: 3-4 player extras and Phase 5.
5. M5: Phase 6 simultaneous play.
6. M6: Phase 7 match presentation (stage layout, player borders, start countdown, in-window prototype).

## Risks / decisions
- RAM addresses per game are the hardest part; presets + watcher are key.
- Controller routing: recommend RetroArch owning input during matches.
- Platform (Windows vs Linux) affects paths.
- 4 players only for games that support it; 2 is the baseline.
