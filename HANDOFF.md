# Handoff: plan.md implementation (WIP)

Branch: `ryanstephan42-plan-phases-implementation`. Pick up from here on a new machine.

## Goal

Finish every phase in `plan.md` for Gauntlet, a gamepad-first pygame front-end where 2–4 players compete in RetroArch challenges and spend points in a shop.

- Phase 0 and Phase 1 needed a review and fixes.
- Phases 2–5 need a full implementation.
- Everything must be tested with unit tests and with real runs against a local RetroArch (RetroDECK flatpak).

## Status

| Area | State |
|---|---|
| Core engine (detect, memory codec, UDP client, schema v2, effects, referee, match runner, session, playlists) | Done, tested, committed (`d5fbd28`) |
| stats, memlab (RamSearch/Watch), packs (zip import/export), presets, SM64 config | Done, tested, committed (`16e2d94`) |
| `controls.py` rewrite, `preferred_install` setting + launcher install sort | Done, committed in the WIP commit |
| New UI package `gauntlet/ui/` (app, base, render, audio, fx, flow, tools) | Written but never run. Committed as WIP |
| Headless UI tests | Not started |
| SNES games and presets | Research only (addresses below). Not verified live |
| Phase 5 (PyInstaller, CI, packaging) | Not started |
| Real end-to-end runs of the pygame app | Not started (the engine was probed live earlier) |
| README / plan.md updates | Not started |

**Tests:** `.venv/bin/python -m pytest -q` gives 79 pass and 1 fail. The failure is `tests/test_core.py::test_repo_games_valid`, which expects 2 games. Only `gauntlet_data/m64.json` exists now because `sf2.json` was removed on purpose. Update the expected count once the SNES configs are added.

**Lint:** `.venv/bin/ruff check gauntlet --select E,F,W --ignore E501` reports 3 small issues:
- `ui/base.py:91`: unused `label`
- `ui/flow.py:772`: unused `a`
- `ui/tools.py:22`: unused import `normalize_title`

## Setup on a new machine

```bash
python3 -m venv .venv
.venv/bin/pip install pygame-ce pytest ruff   # Python 3.14 + pygame-ce 2.5.8 used so far
.venv/bin/python -m pytest -q
```

`requirements.txt` still says `pygame`. Change it to `pygame-ce`.

## Next steps (in order)

1. **Make the UI import and run.**
   - Check that everything imports: `.venv/bin/python -c "import gauntlet.ui.tools, gauntlet.ui.flow"`.
   - Fix the 3 lint issues.
   - In `ui/flow.py`, clean up two messy lines:
     - PlayerSetup: `name = next(...) if False else f"Player {n}"`
     - RoundIntro: the "Sitting out" `players_ids` hasattr expression
2. **Rewrite `gauntlet/app.py` as `main()`.** It should do: logging, then `load_settings`, then `ui.app.App(settings, settings_path=...)`, then `.run(flow.MainMenu)`.
   - Delete the old UI: `ui_shop.py`, and probably `screens.py`, `widgets.py`, `theme.py` and the old `tests/test_ui.py`. Check usages first and keep any helpers the new UI still imports.
3. **Write headless UI tests in `tests/test_flow.py`.**
   - Use `SDL_VIDEODRIVER=dummy` and `SDL_AUDIODRIVER=dummy`.
   - Create the app with `App(settings, launcher=fake, size=(1280,720), audio=False)`.
   - Drive it with `app.inject(InputEvent)` and `app.step(0.016)`.
   - Cover these scenarios:
     - a full session: join 2 players → select → options → shop buy/ready → prematch → match scripted to a win → results → standings → final
     - entering a result manually
     - cancel with refund
     - resume
     - saving settings
     - the OSK
     - creating and saving a game in the wizard
     - the stats screen
     - the games manager
   - Fix the bugs you find, then commit.
4. **Verify the SNES addresses live, then add presets.**
   - Use snes9x in RetroDECK. Use the Memory Lab or a RamSearch script to verify each address.
   - Also check the maximum READ_CORE_MEMORY chunk (the client uses 1024) and that SNES address 0 maps to WRAM `$7E0000`.
   - Then add the presets in `gauntlet/presets/` and the configs in `gauntlet_data/`:
     - **MK2:** versus, eliminate on health. Per-player map `{"1":"0x2EFC","2":"0x30AA"}`, 1 byte, `0xA1` = full.
     - **Super Bomberman:** versus, eliminate on lives at `0x0D7D`, stride `0x40`.
     - **Super Mario Kart:** coins at `0x0E00`, or laps at `0x10C1`.
   - Update `test_repo_games_valid`.
5. **Phase 5.**
   - PyInstaller `gauntlet.spec`.
   - `.github/workflows/ci.yml` running ruff and pytest with dummy SDL.
   - `pyproject.toml` and/or `requirements-dev.txt`.
6. **Real end-to-end runs of the pygame app** with RetroDECK:
   - SM64 in turns mode
   - one SNES versus game

   Drive input with the probe helper below and check results with `grim` screenshots.
7. **Docs and wrap-up.**
   - Update `README.md`.
   - Tick the checkboxes and set the phase status in `plan.md`.
   - Delete this file once the work is done.

## Known issues in the WIP UI to double-check

- `ui/tools.py` (~1100 lines) has never run. Classes:
  - FileBrowser
  - SettingsScreen
  - InputRemap
  - StatsScreen
  - GamesManager
  - WizardScreen
  - `_SubEditor`, with ChallengeEditor and ItemEditor
  - MemoryLabSetup and MemoryLab
- MemoryLab runs a worker thread that owns all UDP traffic.
  - The worker sets `self.dirty`. The UI thread then rebuilds the fields in `update()`, so the worker never rebuilds them directly.
  - Live values are kept in `self.live`. Don't use the name `values`, because that would clash with `FormScreen.values()`.
- `FormScreen.index` is the focused field. ChallengeEditor and ItemEditor store their list slot in `self.slot`.
- `App.process` sends raw KEYDOWN/JOYBUTTONDOWN events to `screen.capture` whenever `screen.capture_raw` is truthy and no overlay is open. InputRemap relies on this.
- The on-screen keyboard only offers `A-Z 0-9 _ . -`. That is why per-player addresses are typed as `0xA-0xB`; `parse_address` handles this.
- Flow transitions use `manager.reset(screen)`, so the stack is always MainMenu plus the current flow screen. View-only screens are pushed on top.

## Environment facts (RetroDECK RetroArch 1.22.2)

- **Launch command:**
  `flatpak run --command=/app/retrodeck/components/retroarch/bin/retroarch net.retrodeck.retrodeck -L <core> <rom> --appendconfig <cfg>`
- **Config files:** the flatpak has a private `/tmp`, so cfg files must live under `$HOME`. The state dir `~/.local/share/gauntlet` works.
- **Cores:**
  - On the host: `~/.local/share/flatpak/app/net.retrodeck.retrodeck/x86_64/stable/active/files/retrodeck/components/retroarch/rd_extras/cores`
  - Inside the sandbox: `/app/retrodeck/...`
- **ROMs:**
  - `~/retrodeck/roms/n64/Super Mario 64 (USA).z64`
  - `~/retrodeck/roms/snes/{Mortal Kombat II (USA) (Rev 1).sfc, Super Bomberman (USA).sfc, Super Mario Kart (USA).sfc}`
  - If they are missing, the user allowed downloading them from their RoMM server. The API token is in the user's `ultimate-emulation` folder (`~/.local/share/ultimate-emulation/romm.token`). **Never print or commit it.**
- **UDP command behaviour:**
  - GET_STATUS replies PLAYING, PAUSED or CONTENTLESS.
  - A bad read replies `-1 no descriptor`.
  - SHOW_MSG, PAUSE_TOGGLE and QUIT send no reply.
  - RetroArch takes 5–15 s after launch before it answers.
  - Not yet checked: whether FAST_FORWARD and SLOWMOTION toggle, and which folder screenshots go to (MemoryLab searches recursively).
- **SM64 addresses (verified live):**
  - Memory layout is swap32, big-endian.
  - coins s16 `0x33B218`, stars `0x33B21A`, lives `0x33B21D`, health `0x33B21E`, level `0x32DDF8` (16 = castle grounds).
- **SNES addresses (research only, from PAR codes; offsets from `$7E0000`):**
  - **MK2:**
    - health P1 `0x2EFC`, P2 `0x30AA` (difference `0x1AE`)
    - character ID P1 `0x2EF8`, P2 `0x30A6`
    - no round timer or round-wins address found
  - **Super Bomberman:**
    - lives P1 `0x0D7D`, P2 `0x0DBD` (stride `0x40`); P3 `0x0DFD` and P4 `0x0E3D` are inferred
    - player struct at `0x0D70+0x40*n`: +0 bombs, +1 fire, +2 speed, +3 remote, +8 red bomb
  - **Super Mario Kart:**
    - coins `0x0E00`
    - lap `0x10C1` (127 = lap 1 … 133 = finished)
    - max lap `0x10F9`
    - item `0x0D70` (valid only when `0x0D71`=`0xC0`)
    - retries `0x0154`
    - no race-position address found
- **Fake RetroArch for tests:**
  - Start it with `gauntlet.fakera.FakeRetroArch(port=0).start_thread()`, or use `Install("Fake", [sys.executable, "-m", "gauntlet.fakera"])`.
  - Script it with `GAUNTLET_FAKE_SCRIPT` and get a command log with `GAUNTLET_FAKE_LOG`.
  - It needs `PYTHONPATH=<repo>` and a dummy `fake_libretro.so` in `core_dir`.
- **Verdict rules:**
  - A draw lists every player in `winners`, with `draw=True`.
  - A player quitting goes through `forfeit_verdict(players, quitter)`.

## Live input probe (Hyprland)

`~/.cache/gauntlet-probe/key.sh` existed on the old machine. Usage: `key.sh KEY[:holdsec] ... sleepN shot`. It finds the window with class `com.libretro.RetroArch` and sends key presses to it:

```bash
hyprctl dispatch "hl.dsp.send_key_state({mods = \"\", key = \"$KEY\", state = \"down\", window = \"address:$ADDR\"})"
grim -g "<x>,<y> <w>x<h>" shot.png
```

## Notes for the user

- `sf2.json` was replaced by the new configs.
- The RoMM token was used, with the user's permission, to download the three SNES ROMs.

Commits must end with the trailer `Co-authored-by: Copilot App <223556219+Copilot@users.noreply.github.com>`.
