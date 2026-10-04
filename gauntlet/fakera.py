"""A tiny fake RetroArch speaking the network-command protocol (for tests and demo mode).

Run like RetroArch: python -m gauntlet.fakera -L core rom --appendconfig cfg
Environment:
  GAUNTLET_FAKE_SCRIPT  JSON file: {"ram_size", "boot_delay", "exit_at",
                        "events": [{"at": secs, "address": int, "bytes": [..]}]}
  GAUNTLET_FAKE_LOG     file that receives every command received (one per line)
"""
import argparse
import json
import os
import socket
import sys
import threading
import time


class FakeRetroArch:
    def __init__(self, port=55355, ram_size=0x20000, content="Fake Game", system="fake",
                 boot_delay=0.0, log_path=None):
        self.port = port
        self.ram = bytearray(ram_size)
        self.content, self.system = content, system
        self.boot_delay = boot_delay
        self.paused = False
        self.running = True
        self.messages = []
        self.commands = []
        self.log_path = log_path
        self.started = time.monotonic()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(("127.0.0.1", port))
        self.port = self.sock.getsockname()[1]
        self.sock.settimeout(0.1)
        self.lock = threading.Lock()

    def handle(self, text):
        self.commands.append(text)
        if self.log_path:
            with open(self.log_path, "a") as f:
                f.write(text + "\n")
        parts = text.split()
        if not parts:
            return None
        cmd = parts[0]
        booted = time.monotonic() - self.started >= self.boot_delay
        if cmd == "VERSION":
            return "1.22.2"
        if cmd == "GET_STATUS":
            if not booted:
                return "GET_STATUS CONTENTLESS"
            state = "PAUSED" if self.paused else "PLAYING"
            return f"GET_STATUS {state} {self.system},{self.content},crc32=deadbeef"
        if cmd == "READ_CORE_MEMORY" and len(parts) == 3:
            addr, n = int(parts[1], 16), int(parts[2])
            if addr + n > len(self.ram) or not booted:
                return f"READ_CORE_MEMORY {parts[1]} -1 no descriptor for address"
            with self.lock:
                data = self.ram[addr:addr + n]
            return f"READ_CORE_MEMORY {parts[1]} " + " ".join(f"{b:02X}" for b in data)
        if cmd == "WRITE_CORE_MEMORY" and len(parts) >= 3:
            addr = int(parts[1], 16)
            data = bytes(int(b, 16) for b in parts[2:])
            if addr + len(data) > len(self.ram) or not booted:
                return f"WRITE_CORE_MEMORY {parts[1]} -1 no descriptor for address"
            with self.lock:
                self.ram[addr:addr + len(data)] = data
            return f"WRITE_CORE_MEMORY {parts[1]} {len(data)}"
        if cmd == "SHOW_MSG":
            self.messages.append(text[9:])
        elif cmd == "PAUSE_TOGGLE":
            self.paused = not self.paused
        elif cmd == "QUIT":
            self.running = False
        return None

    def poke(self, address, data):
        with self.lock:
            self.ram[address:address + len(data)] = bytes(data)

    def serve(self, events=(), exit_at=None):
        events = sorted(events, key=lambda e: e["at"])
        while self.running:
            now = time.monotonic() - self.started
            while events and events[0]["at"] <= now:
                e = events.pop(0)
                self.poke(int(e["address"]), e["bytes"])
            if exit_at is not None and now >= exit_at:
                break
            try:
                data, addr = self.sock.recvfrom(65536)
            except socket.timeout:
                continue
            except OSError:
                break
            reply = self.handle(data.decode(errors="replace").strip())
            if reply is not None:
                self.sock.sendto(reply.encode(), addr)
        self.sock.close()

    def start_thread(self, **kw):
        t = threading.Thread(target=self.serve, kwargs=kw, daemon=True)
        t.start()
        return t


def _port_from_cfg(path):
    try:
        with open(path) as f:
            for line in f:
                if line.strip().startswith("network_cmd_port"):
                    return int(line.split("=", 1)[1].strip().strip('"'))
    except (OSError, ValueError):
        pass
    return 55355


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("-L", dest="core")
    p.add_argument("--appendconfig", default=None)
    p.add_argument("rom", nargs="?")
    args = p.parse_args(argv)
    script = {}
    if os.environ.get("GAUNTLET_FAKE_SCRIPT"):
        with open(os.environ["GAUNTLET_FAKE_SCRIPT"]) as f:
            script = json.load(f)
    port = _port_from_cfg(args.appendconfig) if args.appendconfig else 55355
    content = os.path.splitext(os.path.basename(args.rom or "Fake Game"))[0]
    fake = FakeRetroArch(port, script.get("ram_size", 0x800000), content,
                         boot_delay=script.get("boot_delay", 0.3),
                         log_path=os.environ.get("GAUNTLET_FAKE_LOG"))
    fake.serve(script.get("events", []), script.get("exit_at"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
