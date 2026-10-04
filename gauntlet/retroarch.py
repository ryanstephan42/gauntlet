import logging
import socket
import subprocess
import time

log = logging.getLogger("gauntlet.retroarch")


class RetroArchClient:
    """UDP network-command client for RetroArch."""

    def __init__(self, host="127.0.0.1", port=55355, timeout=0.5):
        self.addr = (host, port)
        self.timeout = timeout

    def send(self, command, expect_reply=True):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(self.timeout)
        try:
            sock.sendto(command.encode(), self.addr)
            if not expect_reply:
                return ""
            return sock.recvfrom(1024)[0].decode().strip()
        except (OSError, socket.timeout) as e:
            log.debug("UDP %r failed: %s", command, e)
            return None
        finally:
            sock.close()

    def write_memory(self, address_hex, value):
        addr = int(address_hex, 16)
        # WRITE_CORE_MEMORY has no reliable reply in all versions; treat as fire-and-forget
        self.send(f"WRITE_CORE_MEMORY {addr:x} {int(value):x}", expect_reply=False)
        log.info("Wrote %s=%s", address_hex, value)

    def read_memory(self, address_hex, length=1):
        """Return list of byte values, or None on failure."""
        addr = int(address_hex, 16)
        reply = self.send(f"READ_CORE_MEMORY {addr:x} {length}")
        if not reply:
            return None
        parts = reply.split()
        # Expected: READ_CORE_MEMORY <addr> <b0> <b1> ... or "... -1 <error>"
        if len(parts) < 3 or parts[2] == "-1":
            return None
        try:
            return [int(b, 16) for b in parts[2:]]
        except ValueError:
            return None

    def is_ready(self):
        return self.send("GET_STATUS") is not None

    def wait_until_ready(self, timeout=30.0, interval=0.5, process=None):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                return False
            if self.is_ready():
                return True
            time.sleep(interval)
        return False


def resolve_ra_config(config_file, config_dir):
    import os
    return os.path.join(config_dir, config_file)
