import logging
import os
import subprocess

from .retroarch import RetroArchClient, resolve_ra_config

log = logging.getLogger("gauntlet.match")


class MatchError(Exception):
    pass


def play_match(game, active_items, settings):
    ra_config = "standard.cfg"
    for item in active_items:
        if item["action_type"] == "retroarch_config":
            ra_config = item["config_file"]
    config_path = resolve_ra_config(ra_config, settings.config_dir)

    meta = game["meta"]
    for label, path in (("core", meta["core"]), ("rom", meta["rom"])):
        if not os.path.exists(path):
            raise MatchError(f"{label} not found: {path}")

    cmd = [settings.retroarch_path, "-L", meta["core"], meta["rom"], "-c", config_path]
    log.info("Launching: %s", cmd)
    try:
        process = subprocess.Popen(cmd)
    except OSError as e:
        raise MatchError(f"cannot launch RetroArch ({settings.retroarch_path}): {e}")

    client = RetroArchClient(settings.retroarch_host, settings.retroarch_port)
    try:
        if not client.wait_until_ready(settings.boot_timeout, process=process):
            raise MatchError("RetroArch did not become ready (is network_cmd_enable on?)")
        for item in active_items:
            if item["action_type"] == "memory_write":
                for _ in range(3):
                    client.write_memory(item["address"], item["value"])
        # TODO(phase 3): referee loop
        process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
