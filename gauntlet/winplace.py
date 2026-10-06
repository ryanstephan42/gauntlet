"""Float match windows onto their tiles under tiling Wayland compositors (Hyprland, Sway).

Tiling compositors ignore RetroArch's `video_windowed_position_*` keys and stack or full-screen new
windows; a covered RetroArch window can stall (no frame callbacks). We find each instance's window
by PID (the launcher PID or a descendant, e.g. through flatpak/bwrap) and float + move + resize it.
Gauntlet's own window can be placed too (the scoreboard strip) and is put back when the match ends.
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
    borders = True  # per-window border colours (Sway only has global ones)

    def __init__(self, run=_run):
        self.run = run
        self._fullscreen = set()
        self._info = {}

    def _json(self, what):
        out = self.run(["hyprctl", "-j", what])
        try:
            return json.loads(out) if out else None
        except ValueError:
            return None

    def area(self, pid=None):
        """(x, y, w, h) minus bars, in layout coordinates, of the monitor showing `pid`'s window
        (Gauntlet's own, so games never jump to whichever monitor has focus), else the focused one."""
        mons = self._json("monitors") or []
        home = None
        if pid is not None:
            home = next((c.get("monitor") for c in self._json("clients") or [] if c.get("pid") == pid), None)
        m = next((m for m in mons if home is not None and m.get("id") == home), None)
        m = m or next((m for m in mons if m.get("focused")), mons[0] if mons else None)
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
        self._info = {c["address"]: c for c in clients}
        return [(c["address"], c.get("pid")) for c in clients]

    def geometry(self, wid):
        """{"floating": bool, "rect": (x, y, w, h)} as of the last windows() call, or None."""
        c = self._info.get(wid)
        if not c or "at" not in c or "size" not in c:
            return None
        return {"floating": bool(c.get("floating")), "rect": (*c["at"], *c["size"])}

    def restore(self, wid, geometry):
        """Put a window back the way geometry() saw it (tiled, or floating at its old place)."""
        sel = f"address:{wid}"
        if geometry and geometry["floating"]:
            return self.place(wid, geometry["rect"])
        return self.run(["hyprctl", "dispatch", "settiled", sel]) is not None

    def _workspace_at(self, x, y):
        """Active workspace id of the monitor containing layout point (x, y), or None."""
        for m in self._json("monitors") or []:
            if not isinstance(m, dict) or not {"x", "y", "width", "height"} <= m.keys():
                continue
            scale = m.get("scale") or 1
            w, h = m["width"] / scale, m["height"] / scale
            if m.get("transform", 0) % 2:
                w, h = h, w
            if m["x"] <= x < m["x"] + w and m["y"] <= y < m["y"] + h:
                return (m.get("activeWorkspace") or {}).get("id")
        return None

    def place(self, wid, rect):
        x, y, w, h = rect
        sel = f"address:{wid}"
        cmds = []
        if wid in self._fullscreen:
            # Window rules (e.g. Omarchy's "fullscreen on" for RetroArch) can force fullscreen;
            # fullscreenstate only acts on the focused window.
            cmds += [f"dispatch focuswindow {sel}", "dispatch fullscreenstate 0 0"]
        # A window opens on the focused monitor; moving it by pixels alone leaves it owned by that
        # monitor's workspace (drawn on the wrong screen), so send it to the target monitor's workspace.
        ws = self._workspace_at(x + w // 2, y + h // 2)
        current = (self._info.get(wid) or {}).get("workspace", {}).get("id")
        if ws is not None and ws != current:
            cmds.append(f"dispatch movetoworkspacesilent {ws},{sel}")
        cmds += [f"dispatch setfloating {sel}", f"dispatch resizewindowpixel exact {w} {h},{sel}",
                f"dispatch movewindowpixel exact {x} {y},{sel}"]
        return self.run(["hyprctl", "--batch", " ; ".join(cmds)]) is not None

    def focus(self, wid):
        return self.run(["hyprctl", "dispatch", "focuswindow", f"address:{wid}"]) is not None

    def decorate(self, wid, rgb, width):
        """Give a window a solid border of colour `rgb`, focused or not."""
        sel = f"address:{wid}"
        color = "rgb({:02x}{:02x}{:02x})".format(*rgb[:3])
        cmds = [f"dispatch setprop {sel} border_size {int(width)}",
                f"dispatch setprop {sel} active_border_color {color}",
                f"dispatch setprop {sel} inactive_border_color {color}"]
        return self.run(["hyprctl", "--batch", " ; ".join(cmds)]) is not None


class Sway:
    name = "Sway"

    def __init__(self, run=_run):
        self.run = run
        self._info = {}

    def _json(self, what):
        out = self.run(["swaymsg", "-r", "-t", what])
        try:
            return json.loads(out) if out else None
        except ValueError:
            return None

    def area(self, pid=None):
        outs = self._json("get_outputs") or []
        home = self._output_of(pid) if pid is not None else None
        o = next((o for o in outs if home and o.get("name") == home), None)
        o = o or next((o for o in outs if o.get("focused")), outs[0] if outs else None)
        if not o:
            return None
        r = o["rect"]
        return (r["x"], r["y"], r["width"], r["height"])

    def _output_of(self, pid):
        def walk(node, output):
            if node.get("type") == "output":
                output = node.get("name")
            if node.get("pid") == pid:
                return output
            for child in node.get("nodes", []) + node.get("floating_nodes", []):
                found = walk(child, output)
                if found:
                    return found
            return None
        tree = self._json("get_tree")
        return walk(tree, None) if tree else None

    def windows(self):
        found = []
        self._info = {}

        def walk(node):
            if node.get("pid") and node.get("type") in ("con", "floating_con"):
                found.append((node["id"], node["pid"]))
                self._info[node["id"]] = node
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

    def geometry(self, wid):
        node = self._info.get(wid)
        if not node or "rect" not in node:
            return None
        r = node["rect"]
        return {"floating": node.get("type") == "floating_con",
                "rect": (r["x"], r["y"], r["width"], r["height"])}

    def restore(self, wid, geometry):
        if geometry and geometry["floating"]:
            return self.place(wid, geometry["rect"])
        return self.run(["swaymsg", f"[con_id={wid}] floating disable"]) is not None


def detect(env=None, which=shutil.which):
    """The compositor backend to place windows with, or None (positions left to RetroArch)."""
    env = os.environ if env is None else env
    if env.get("HYPRLAND_INSTANCE_SIGNATURE") and which("hyprctl"):
        return Hyprland()
    if env.get("SWAYSOCK") and which("swaymsg"):
        return Sway()
    return None


class _Job:
    def __init__(self, pid, rect, own, border=None):
        self.pid = pid
        self.rect = tuple(int(v) for v in rect)
        self.own = own      # Gauntlet's own window: exact PID, never focused, restored on stop()
        self.border = border  # (rgb, width): a coloured border drawn inside `rect`
        self.wid = None     # window last placed
        self.saved = None   # its geometry before we first moved it (own windows only)


class Placer:
    """Places one window per launched process from a background thread.

    Keeps watching until stopped (or `timeout`), because RetroArch may recreate its window once the
    core loads; any new window of a process is placed again.
    """

    def __init__(self, backend, descendants=descendants):
        self.backend = backend
        self.descendants = descendants
        self.jobs = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None

    def area(self):
        """The usable area of the monitor Gauntlet's window is on."""
        try:
            return self.backend.area(os.getpid())
        except (KeyError, TypeError, ValueError):
            return None

    def add(self, pid, rect, own=False, border=None):
        """Place `pid`'s window at `rect`; `own`: this process's window (exact PID, restored on stop).
        `border`: (rgb, width) to frame the window in a colour, where the backend supports it."""
        with self._lock:
            self.jobs.append(_Job(pid, rect, own, border))

    def _frame(self, job):
        """(rect to place at, border or None): a border is drawn outside the window, so shrink it."""
        rgb, width = job.border or (None, 0)
        if not rgb or width <= 0 or not getattr(self.backend, "borders", False):
            return job.rect, None
        x, y, w, h = job.rect
        return (x + width, y + width, w - 2 * width, h - 2 * width), (rgb, width)

    def forget(self, pid):
        """Stop tracking a process (e.g. a RetroArch that closed between turns)."""
        with self._lock:
            self.jobs = [j for j in self.jobs if j.pid != pid or j.own]

    @property
    def placed(self):
        return all(j.wid is not None for j in self.jobs)

    def poll(self):
        """One placement pass over every job; returns True when every process has a placed window."""
        with self._lock:
            windows = self.backend.windows()
            for job in self.jobs:
                pids = {job.pid} if job.own else self.descendants(job.pid)
                mine = [wid for wid, pid in windows if pid in pids]
                if not mine or mine[-1] == job.wid:
                    continue
                if job.own and job.saved is None and hasattr(self.backend, "geometry"):
                    job.saved = self.backend.geometry(mine[-1]) or {}
                rect, border = self._frame(job)
                if self.backend.place(mine[-1], rect):
                    job.wid = mine[-1]
                    if border:
                        self.backend.decorate(mine[-1], *border)
                    log.info("Placed window of pid %s at %s (%s)", job.pid, rect, self.backend.name)
            return self.placed

    def refresh(self, pause=0.2):
        """Focus each placed game window in turn, ending on player 1's.

        RetroArch keeps drawing at its old size after the compositor resizes it and only catches
        up when its focus changes (e.g. the mouse moving over it); call this once they are running.
        """
        try:
            with self._lock:
                for wid in reversed([j.wid for j in self.jobs if j.wid is not None and not j.own]):
                    self.backend.focus(wid)
                    time.sleep(pause)
        except Exception:  # noqa: BLE001 - placement is best effort; never break the match
            log.exception("window refresh failed")

    def start(self, timeout=120.0, interval=0.5, settle=15.0):
        """Poll in the background; stops `settle` seconds after the last placement once all are placed.
        Calling it again while the thread is alive does nothing (new jobs are picked up)."""
        if self._thread and self._thread.is_alive():
            return

        def loop():
            end = time.monotonic() + timeout
            last = None
            while not self._stop.is_set() and time.monotonic() < end:
                try:
                    before = [j.wid for j in self.jobs]
                    self.poll()
                except Exception:  # noqa: BLE001 - placement is best effort; never break the match
                    log.exception("window placement failed")
                    return
                if [j.wid for j in self.jobs] != before:
                    last = time.monotonic()
                if self.placed and last is not None and time.monotonic() - last > settle:
                    return
                self._stop.wait(interval)
            if not self.placed:
                log.warning("Could not place every match window (%s)", self.backend.name)
        self._thread = threading.Thread(target=loop, name="gauntlet-placer", daemon=True)
        self._thread.start()

    def stop(self):
        """Stop placing and put Gauntlet's own window back where it was."""
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        with self._lock:
            for job in self.jobs:
                if job.own and job.wid is not None and hasattr(self.backend, "restore"):
                    try:
                        self.backend.restore(job.wid, job.saved)
                    except Exception:  # noqa: BLE001 - best effort
                        log.exception("could not restore the Gauntlet window")
                    job.wid = None
