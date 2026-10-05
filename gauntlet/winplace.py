"""Force race windows to float on their tile under tiling Wayland compositors (Hyprland, Sway).

Tiling compositors ignore RetroArch's `video_windowed_position_*` keys and stack or full-screen new
windows; a covered RetroArch window can stall (no frame callbacks). We find each instance's window
by PID (the launcher PID or a descendant, e.g. through flatpak/bwrap) and float + move + resize it.
Other desktops (X11, GNOME, KDE) honour RetroArch's own position keys, so detect() returns None.
"""
import json
import logging
import os
import shutil
import subprocess
import threading
import time

log = logging.getLogger(__name__)


def descendants(pid):
    """`pid` plus every process below it (reads /proc; just {pid} elsewhere)."""
    children = {}
    try:
        names = os.listdir("/proc")
    except OSError:
        return {pid}
    for name in names:
        if not name.isdigit():
            continue
        try:
            with open(f"/proc/{name}/stat") as f:
                ppid = int(f.read().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            continue
        children.setdefault(ppid, []).append(int(name))
    out, todo = set(), [pid]
    while todo:
        p = todo.pop()
        if p not in out:
            out.add(p)
            todo.extend(children.get(p, ()))
    return out


def _run(cmd, timeout=2.0):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        log.debug("%s failed: %s", cmd[0], e)
        return None
    if r.returncode != 0:
        log.debug("%s failed: %s", cmd, r.stderr.strip())
        return None
    return r.stdout


class Hyprland:
    name = "Hyprland"

    def __init__(self, run=_run):
        self.run = run
        self._fullscreen = set()

    def _json(self, what):
        out = self.run(["hyprctl", "-j", what])
        try:
            return json.loads(out) if out else None
        except ValueError:
            return None

    def area(self):
        """(x, y, w, h) of the focused monitor minus bars, in layout coordinates."""
        mons = self._json("monitors") or []
        m = next((m for m in mons if m.get("focused")), mons[0] if mons else None)
        if not m:
            return None
        scale = m.get("scale") or 1
        w, h = m["width"] / scale, m["height"] / scale
        if m.get("transform", 0) % 2:
            w, h = h, w
        left, top, right, bottom = (m.get("reserved") or [0, 0, 0, 0])[:4]
        return (int(m["x"] + left), int(m["y"] + top), int(w - left - right), int(h - top - bottom))

    def windows(self):
        """[(window id, pid)]"""
        clients = [c for c in self._json("clients") or [] if c.get("mapped", True)]
        self._fullscreen = {c["address"] for c in clients if c.get("fullscreen")}
        return [(c["address"], c.get("pid")) for c in clients]

    def place(self, wid, rect):
        x, y, w, h = rect
        sel = f"address:{wid}"
        cmds = []
        if wid in self._fullscreen:
            # Window rules (e.g. Omarchy's "fullscreen on" for RetroArch) can force fullscreen;
            # fullscreenstate only acts on the focused window.
            cmds += [f"dispatch focuswindow {sel}", "dispatch fullscreenstate 0 0"]
        cmds += [f"dispatch setfloating {sel}", f"dispatch resizewindowpixel exact {w} {h},{sel}",
                f"dispatch movewindowpixel exact {x} {y},{sel}"]
        return self.run(["hyprctl", "--batch", " ; ".join(cmds)]) is not None

    def focus(self, wid):
        return self.run(["hyprctl", "dispatch", "focuswindow", f"address:{wid}"]) is not None


class Sway:
    name = "Sway"

    def __init__(self, run=_run):
        self.run = run

    def _json(self, what):
        out = self.run(["swaymsg", "-r", "-t", what])
        try:
            return json.loads(out) if out else None
        except ValueError:
            return None

    def area(self):
        outs = self._json("get_outputs") or []
        o = next((o for o in outs if o.get("focused")), outs[0] if outs else None)
        if not o:
            return None
        r = o["rect"]
        return (r["x"], r["y"], r["width"], r["height"])

    def windows(self):
        found = []

        def walk(node):
            if node.get("pid") and node.get("type") in ("con", "floating_con"):
                found.append((node["id"], node["pid"]))
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                walk(child)
        tree = self._json("get_tree")
        if tree:
            walk(tree)
        return found

    def place(self, wid, rect):
        x, y, w, h = rect
        cmd = (f"[con_id={wid}] fullscreen disable, floating enable, resize set width {w} px height {h} px, "
               f"move absolute position {x} px {y} px")
        return self.run(["swaymsg", cmd]) is not None

    def focus(self, wid):
        return self.run(["swaymsg", f"[con_id={wid}] focus"]) is not None


def detect(env=None, which=shutil.which):
    """The compositor backend to place windows with, or None (positions left to RetroArch)."""
    env = os.environ if env is None else env
    if env.get("HYPRLAND_INSTANCE_SIGNATURE") and which("hyprctl"):
        return Hyprland()
    if env.get("SWAYSOCK") and which("swaymsg"):
        return Sway()
    return None


class Placer:
    """Places one window per launched process from a background thread.

    Keeps watching until stopped (or `timeout`), because RetroArch may recreate its window once the
    core loads; any new window of a process is placed again.
    """

    def __init__(self, backend, descendants=descendants):
        self.backend = backend
        self.descendants = descendants
        self.jobs = []      # [pid, rect, id of the window last placed]
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None

    def area(self):
        try:
            return self.backend.area()
        except (KeyError, TypeError, ValueError):
            return None

    def add(self, pid, rect):
        self.jobs.append([pid, tuple(int(v) for v in rect), None])

    @property
    def placed(self):
        return all(j[2] is not None for j in self.jobs)

    def poll(self):
        """One placement pass over every job; returns True when every process has a placed window."""
        with self._lock:
            windows = self.backend.windows()
            for job in self.jobs:
                pids = self.descendants(job[0])
                mine = [wid for wid, pid in windows if pid in pids]
                if mine and mine[-1] != job[2] and self.backend.place(mine[-1], job[1]):
                    job[2] = mine[-1]
                    log.info("Placed window of pid %s at %s (%s)", job[0], job[1], self.backend.name)
            return self.placed

    def refresh(self, pause=0.2):
        """Focus each placed window in turn, ending on player 1's.

        RetroArch keeps drawing at its old size after the compositor resizes it and only catches
        up when its focus changes (e.g. the mouse moving over it); call this once they are running.
        """
        try:
            with self._lock:
                for wid in reversed([j[2] for j in self.jobs if j[2] is not None]):
                    self.backend.focus(wid)
                    time.sleep(pause)
        except Exception:  # noqa: BLE001 - placement is best effort; never break the match
            log.exception("window refresh failed")

    def start(self, timeout=120.0, interval=0.5, settle=15.0):
        """Poll in the background; stops `settle` seconds after the last placement once all are placed."""
        def loop():
            end = time.monotonic() + timeout
            last = None
            while not self._stop.is_set() and time.monotonic() < end:
                try:
                    before = [j[2] for j in self.jobs]
                    self.poll()
                except Exception:  # noqa: BLE001 - placement is best effort; never break the match
                    log.exception("window placement failed")
                    return
                if [j[2] for j in self.jobs] != before:
                    last = time.monotonic()
                if self.placed and last is not None and time.monotonic() - last > settle:
                    return
                self._stop.wait(interval)
            if not self.placed:
                log.warning("Could not place every race window (%s)", self.backend.name)
        self._thread = threading.Thread(target=loop, name="gauntlet-placer", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
