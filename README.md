# Gauntlet

Retro game challenges with a points shop, run through RetroArch. See `plan.md` for the roadmap.

## Run
```
pip install -r requirements.txt
python gauntlet.py
```
RetroArch must have `network_cmd_enable = true` (UDP port 55355 by default).

## Settings (`settings.json`, optional)
`retroarch_path`, `retroarch_host`, `retroarch_port`, `data_dir`, `rom_dir`, `core_dir`,
`config_dir`, `assets_dir`, `player_count` (1-4), `starting_points`, `fullscreen`, `width`,
`height`, `boot_timeout`. Missing keys use defaults; invalid values are logged and ignored.

## Game config (`gauntlet_data/*.json`, schema_version 1)
- `meta`: `name`, `core`, `rom` (required), `image`.
- `referee` (optional/null): `address` (hex string), `bytes`, `win_value`, `description`.
- `shop[]`: `id` (unique), `name`, `cost`, `description`, `action_type`:
  - `memory_write`: `address` (hex string), `value` (0-255)
  - `retroarch_config`: `config_file` (relative to `config_dir`)

Invalid files are skipped and the reasons are logged to `gauntlet.log`.

## Tests
```
pip install pytest
pytest
```
