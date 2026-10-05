# Gauntlet

A gamepad-first couch-competitive front end for RetroArch. 2–4 players take on retro game
challenges, earn points, and spend them in a shop on buffs for themselves and debuffs for their
opponents. Gauntlet watches the emulator's memory to decide who won.

## Install and run
```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt      # pygame-ce
.venv/bin/python gauntlet.py [--settings FILE] [--windowed] [--no-sound] [--debug]
```
Or install it as a package with `pip install .`, then run `gauntlet`. To build a standalone folder,
run `pip install pyinstaller && pyinstaller gauntlet.spec` (output in `dist/gauntlet`).

On first run Gauntlet finds RetroArch by itself. It checks RetroDECK and the libretro Flatpak,
`retroarch` on the PATH, and the usual install folders. If several installs exist, pick one under
**Settings → RetroArch install**, or set `retroarch_command` or `retroarch_path`. Gauntlet also
finds cores and ROMs next to the detected install. Each match starts RetroArch with an
`--appendconfig` file that turns on network commands, so your own `retroarch.cfg` is never changed.

Logs, settings saves, sessions, stats and generated RetroArch configs go in the state folder:
- Linux: `~/.local/share/gauntlet`
- macOS: `~/Library/Application Support/Gauntlet`
- Windows: `%APPDATA%\Gauntlet`

## Playing
- **Join:** press A or Enter to join. With `split_keyboard` on, a second keyboard player
  joins with U. Each controller becomes one player.
- **Menus:** the d-pad or stick moves, A confirms, B goes back. The mouse works too.
- **Flow:** Main menu → players → game/playlist → options (rounds, wagers) → shop → pre-match
  summary → match → results → standings.
- **Playlists:** single game, N rounds, or a 4-player bracket. You can resume a saved session.
- **During a match:** RetroArch owns the controllers. Gauntlet shows each player's live metric.
  - Hold Select+Start to forfeit.
  - The match menu (B or Esc in Gauntlet) can end the match and report the result by hand,
    forfeit a player, or cancel the match (purchases are refunded).

### Races: single-player challenges played at the same time
Challenges with `mode: "turns"` (for example "most coins in SM64") normally run once per player.
When every player has their own controller, Gauntlet runs them as a **race** instead:
- One RetroArch window per player, all at once.
- Each window gets its own network port (`retroarch_port + n`), config, log
  (`logs/retroarch_pN.log`) and window.
- Every window loads the same start state.
- The first player to meet the win condition wins, and all windows close.
- If time runs out, the players' metrics decide the winner.
- If a player's window crashes or is closed, that player forfeits and the race continues for
  everyone else.

Notes on races:
- **Input isolation.** Each window listens only to its own player's gamepad
  (`input_player1_joypad_index`). Gamepads work in every window without focus.
  - A keyboard player's window needs focus, unless RetroArch can use the `udev` input driver. On
    Linux that means your user is in the `input` group.
  - Two keyboard players race only with `udev`. Otherwise the challenge runs as turns, and
    Gauntlet says why on the pre-match screen.
- **Sound.** Only player 1's window plays sound (`race_mute_others`).
- **Window layout.** Windows are tiled side by side for 2 players and in a 2×2 grid for 3–4,
  across the screen Gauntlet is on. Gauntlet drops to a window during the race and goes back to
  fullscreen, on the same monitor, when the race ends.
- **Hyprland / Sway** (`race_place_windows`).
  - Tiling compositors ignore the window positions an app asks for. Gauntlet uses
    `hyprctl`/`swaymsg` to float each player's window onto its tile.
  - Window rules that make RetroArch fullscreen are switched off for these windows. Omarchy ships
    such a rule.
  - It then focuses each window once. RetroArch only adopts its new size after a focus change, so
    the cursor may jump.
- **Turning races off.** Set `simultaneous_play` to `false` to always take turns.

## Settings
Edit them in **Settings** in the app, or in `settings.json` (or the file given with `--settings`).
Missing keys use defaults; invalid values are logged and ignored.

| Group | Keys |
|---|---|
| RetroArch | `retroarch_command` (argv prefix, e.g. `["flatpak","run","org.libretro.RetroArch"]`), `retroarch_path`, `preferred_install`, `retroarch_host`, `retroarch_port` (55355), `retroarch_overrides` (extra `retroarch.cfg` keys for every launch) |
| Folders | `data_dir` (game configs), `rom_dir`, `core_dir` (empty = auto), `config_dir`, `assets_dir`, `start_states_dir`, `state_dir` |
| Economy | `player_count`, `starting_points`, `win_points`, `loss_points`, `draw_points`, `catchup_step`, `catchup_max`, `streak_bonus`, `streak_max`, `max_items`, `wagers` |
| Display/input | `fullscreen`, `width`, `height`, `tv_mode`, `sound`, `volume`, `split_keyboard`, `key_bindings`, `button_bindings` (Settings → Remap menu controls) |
| Matches | `boot_timeout`, `poll_interval`, `close_delay`, `assign_ports` |
| Races | `simultaneous_play`, `race_input_driver` (`""` = auto: `udev` when readable), `race_mute_others`, `race_place_windows` |

Tip: `retroarch_overrides` is the escape hatch for RetroArch quirks on your machine. For example,
if a device that isn't a gamepad shows up as joystick 0 and steals player 1's port, try
`{"input_joypad_driver": "sdl2"}` or `{"input_joypad_driver": "null"}`.

## Games and challenges
Game configs are JSON files in `data_dir` (`gauntlet_data/`, schema v2; v1 files are migrated
automatically). You don't need to write them by hand:
- **Add Game** on the main menu opens the wizard. It walks you through system, core, ROM, name/art,
  challenges and shop items, and starts from the presets in `gauntlet/presets/`.
- **Memory Lab** reads RAM live, searches by value, changed or unchanged, and lets you test a
  write.
- **Manage Games** edits, duplicates, deletes, imports and exports configs as zip packs, and
  validates them.

Bundled games: Super Mario 64, Mortal Kombat II, Super Bomberman and Super Mario Kart. Their
addresses were verified live on RetroDECK.

Outline of a game config:
- `meta`: `name`, `system`, `core`, `rom` (required); `image`, `players`, `description`.
- `memory`: `layout` (`linear`/`swap16`/`swap32`) and `endian`. The defaults come from the system.
- `challenges[]`, each with:
  - `id`, `name`
  - `mode` (`versus`, `turns`, `coop` or `manual`)
  - `metric.var`
  - `win` (`reach`, `equals`, `bit_set`, `eliminate` or `compare`, plus `value` and `order`)
  - `time_limit`, `on_timeout`, `best_of`, `min_time`
  - `ready` (a condition to wait for before the clock starts)
  - `setup[]` (actions)
  - `start_state`: a RetroArch save state, looked up in `start_states_dir` first and then in the
    bundled `start_states/`. Capture one from the challenge editor.
- `shop[]`, each item with:
  - `id`, `name`, `cost`, `category` (`buff`, `debuff` or `chaos`)
  - `target` (`self`, `opponent`, `others` or `all`), `limit`
  - `actions[]`. Action types:
    - `memory_write`: `op` (set/add/sub/or/and/xor), `repeat`/freeze and `duration`
    - `retroarch_config`: also covers shaders and input remaps
    - `retroarch_command`
    - `message`
- A `var` is `{address, size, signed, endian, mask, bit, stride}`.
  - `address` is a hex string, or a per-player map such as `{"1": "0x2EFC", "2": "0x30AA"}`.

## Development
```
.venv/bin/pip install -r requirements-dev.txt
SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy .venv/bin/python -m pytest -q
.venv/bin/ruff check gauntlet tests
```
The tests drive the whole UI headlessly against `gauntlet.fakera`, a fake RetroArch that answers
network commands and can run as several instances for races. CI runs lint and tests on Python
3.11–3.13 and builds PyInstaller packages for Linux and Windows.
