"""Browser controller protocol and Linux virtual-gamepad bridge (optional dependencies)."""
import argparse
import asyncio
import json
import math
import os
from pathlib import Path
import queue
import sys
import threading
import time
from urllib.parse import urlencode, urlsplit


PAD_NAME = "Gauntlet Remote Controller"
STATE_TIMEOUT = 0.5
NEUTRAL = {"type": "state", "buttons": [False] * 17, "axes": [0.0] * 4}

# SDL joystick indices of our Linux uinput device, not browser Gamepad button indices.
RA_BUTTONS = {
    "b": "0", "a": "1", "y": "2", "x": "3", "l": "4", "r": "5",
    "select": "6", "start": "7", "l3": "9", "r3": "10",
    "up": "h0up", "down": "h0down", "left": "h0left", "right": "h0right",
}
RA_AXES = {"up": "-1", "down": "+1", "left": "-0", "right": "+0",
           "l2": "+2", "r2": "+5", "l_x_plus": "+0", "l_x_minus": "-0",
           "l_y_plus": "+1", "l_y_minus": "-1", "r_x_plus": "+3", "r_x_minus": "-3",
           "r_y_plus": "+4", "r_y_minus": "-4"}


def validate_state(value):
    """Accept only bounded full snapshots; no arbitrary keys, keycodes or commands."""
    if not isinstance(value, dict) or set(value) != {"type", "buttons", "axes"} or value["type"] != "state":
        raise ValueError("expected a controller state")
    buttons, axes = value["buttons"], value["axes"]
    if not isinstance(buttons, list) or len(buttons) != 17 or any(type(b) is not bool for b in buttons):
        raise ValueError("expected 17 boolean buttons")
    if not isinstance(axes, list) or len(axes) != 4:
        raise ValueError("expected four axes")
    if any(type(a) not in (int, float) or not -1 <= a <= 1 or not math.isfinite(a) for a in axes):
        raise ValueError("axes must be finite numbers between -1 and 1")
    return value


class VirtualPad:
    """One persistent pad per bridge; guest disconnects release it without changing its index."""

    def __init__(self):
        from evdev import AbsInfo, UInput, ecodes as e

        self.e = e
        self.buttons = (e.BTN_SOUTH, e.BTN_EAST, e.BTN_NORTH, e.BTN_WEST, e.BTN_TL, e.BTN_TR,
                        None, None, e.BTN_SELECT, e.BTN_START, e.BTN_THUMBL, e.BTN_THUMBR)
        self.axes = (e.ABS_X, e.ABS_Y, e.ABS_RX, e.ABS_RY)
        sticks = [(axis, AbsInfo(0, -32767, 32767, 16, 128, 0)) for axis in self.axes]
        triggers = [(axis, AbsInfo(0, 0, 255, 0, 0, 0)) for axis in (e.ABS_Z, e.ABS_RZ)]
        hats = [(axis, AbsInfo(0, -1, 1, 0, 0, 0)) for axis in (e.ABS_HAT0X, e.ABS_HAT0Y)]
        self.device = UInput(
            {e.EV_KEY: [b for b in self.buttons if b is not None] + [e.BTN_MODE],
             e.EV_ABS: sticks + triggers + hats},
            name=PAD_NAME, vendor=0, product=0, version=1, bustype=e.BUS_VIRTUAL,
        )
        self.apply(NEUTRAL)

    def apply(self, state):
        validate_state(state)
        e, buttons = self.e, state["buttons"]
        for index, code in enumerate(self.buttons):
            if code is not None:
                self.device.write(e.EV_KEY, code, int(buttons[index]))
        # The browser's Guide button is deliberately ignored: no system/menu hotkey injection.
        self.device.write(e.EV_KEY, e.BTN_MODE, 0)
        for code, value in zip(self.axes, state["axes"]):
            self.device.write(e.EV_ABS, code, round(value * 32767))
        self.device.write(e.EV_ABS, e.ABS_Z, 255 if buttons[6] else 0)
        self.device.write(e.EV_ABS, e.ABS_RZ, 255 if buttons[7] else 0)
        self.device.write(e.EV_ABS, e.ABS_HAT0X, int(buttons[15]) - int(buttons[14]))
        self.device.write(e.EV_ABS, e.ABS_HAT0Y, int(buttons[13]) - int(buttons[12]))
        self.device.syn()

    def close(self):
        try:
            self.apply(NEUTRAL)
        finally:
            self.device.close()


async def receive_inputs(ws, pad, on_session, on_event=None):
    """Release held controls on missing snapshots, malformed input, cancellation or socket loss."""
    from aiohttp import WSMsgType

    last_state = None
    try:
        while True:
            try:
                message = await asyncio.wait_for(ws.receive(), timeout=0.1)
            except asyncio.TimeoutError:
                if last_state is not None and time.monotonic() - last_state >= STATE_TIMEOUT:
                    pad.apply(NEUTRAL)
                    last_state = None
                    print("Remote input timed out; controls released.", flush=True)
                continue
            if message.type == WSMsgType.TEXT:
                value = json.loads(message.data)
                if not isinstance(value, dict):
                    raise ValueError("invalid relay message")
                kind = value.get("type")
                if kind == "session":
                    on_session(value)
                elif kind == "state":
                    pad.apply(validate_state(value))
                    last_state = time.monotonic()
                elif kind in ("connected", "disconnected"):
                    pad.apply(NEUTRAL)
                    last_state = None
                    if on_event:
                        on_event(value)
                    print(f"Remote controller {kind}.", flush=True)
                else:
                    raise ValueError("unknown relay message")
            elif message.type == WSMsgType.ERROR:
                raise ConnectionError("relay connection failed") from ws.exception()
            elif message.type in (WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.CLOSING):
                raise ConnectionError("relay disconnected; restart the bridge for a new invite")
    finally:
        pad.apply(NEUTRAL)


def relay_url(value):
    parsed = urlsplit(value)
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password
            or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("--relay must be an http(s) origin, e.g. https://controls.example.com")
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("internet relays require HTTPS; plain HTTP is only allowed on localhost")
    return value.rstrip("/")


async def run_bridge(url, key, on_event=None):
    from aiohttp import ClientError, ClientSession, ClientTimeout, ClientWSTimeout

    pad = VirtualPad()
    try:
        async with ClientSession(timeout=ClientTimeout(total=None, sock_connect=10)) as client:
            async with client.ws_connect(url + "/host", headers={"Authorization": f"Bearer {key}"},
                                         heartbeat=10, max_msg_size=4096,
                                         timeout=ClientWSTimeout(ws_close=2)) as ws:
                def invite(value):
                    if on_event:
                        on_event(value)
                        return
                    fragment = urlencode({"room": value["room"], "token": value["token"]})
                    print(f"Friend's invite (private): {url}/#{fragment}", flush=True)
                    print("Keep this bridge running. Join in Gauntlet with A; Ctrl+C revokes the invite.", flush=True)

                await receive_inputs(ws, pad, invite, on_event)
    except ClientError as exc:
        raise ConnectionError(f"cannot connect to relay: {exc}") from exc
    finally:
        pad.close()


class RemoteController:
    """App-owned bridge; only the UI thread consumes events and changes displayed state."""

    def __init__(self):
        self.invite = ""
        self.status = "Not hosting"
        self.error = ""
        self._events = queue.Queue()
        self._stop = threading.Event()
        self._thread = None

    @property
    def active(self):
        return self._thread is not None and self._thread.is_alive()

    def start(self, url, key_file):
        if self.active:
            raise ValueError("Revoke the current invite before creating another")
        if sys.platform != "linux":
            raise ValueError("Remote controller hosting currently requires Linux")
        url = relay_url(url)
        key = os.environ.get("GAUNTLET_RELAY_KEY")
        if key is None:
            try:
                key = Path(key_file).read_text().strip()
            except FileNotFoundError:
                raise ValueError(f"Save the private relay key in {key_file}, or set GAUNTLET_RELAY_KEY") from None
        if len(key) < 32 or not key.isascii():
            raise ValueError("The private relay key must contain at least 32 ASCII characters")
        self.poll()
        self._url = url
        self.invite, self.error, self.status = "", "", "Connecting..."
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(url, key), daemon=True,
                                        name="gauntlet-remote")
        self._thread.start()

    def _run(self, url, key):
        async def serve():
            task = asyncio.create_task(run_bridge(url, key, self._events.put))
            try:
                while not self._stop.is_set():
                    done, _ = await asyncio.wait({task}, timeout=0.1)
                    if done:
                        await task
                        return
            finally:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        try:
            asyncio.run(serve())
        except ImportError:
            self._events.put({"type": "error", "message": 'Install remote dependencies: pip install ".[remote]"'})
        except PermissionError:
            self._events.put({"type": "error", "message": "Cannot access /dev/uinput. See docs/remote-controller.md."})
        except (OSError, ValueError, ConnectionError, RuntimeError) as exc:
            self._events.put({"type": "error", "message": f"Remote controller stopped: {exc}"})
        finally:
            self._events.put({"type": "stopped"})

    def poll(self):
        while True:
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            kind = event["type"]
            if kind == "session":
                fragment = urlencode({"room": event["room"], "token": event["token"]})
                self.invite = f"{self._url}/#{fragment}"
                self.status = "Waiting for friend"
            elif kind == "connected":
                self.status = "Friend connected"
            elif kind == "disconnected":
                self.status = "Friend disconnected; invite still valid"
            elif kind == "error":
                self.error = event["message"]
                self.status = "Hosting failed"
                self.invite = ""
            elif kind == "stopped":
                self.invite = ""
                if not self.error:
                    self.status = "Not hosting"

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self.active:
            raise RuntimeError("Remote bridge is still stopping; wait before creating another invite")
        self.poll()
        self.invite = ""

def main(argv=None):
    parser = argparse.ArgumentParser(description="Receive one remote controller as a Linux virtual gamepad.")
    parser.add_argument("--relay", required=True, help="public HTTPS relay origin (HTTP localhost for testing)")
    args = parser.parse_args(argv)
    if sys.platform != "linux":
        parser.error("the virtual controller bridge currently supports Linux only")
    key = os.environ.get("GAUNTLET_RELAY_KEY", "")
    if len(key) < 32:
        parser.error("set GAUNTLET_RELAY_KEY to the relay's private key (at least 32 characters)")
    try:
        url = relay_url(args.relay)
        asyncio.run(run_bridge(url, key))
    except KeyboardInterrupt:
        return 0
    except ImportError:
        parser.exit(1, 'Remote dependencies missing. Install with: pip install ".[remote]"\n')
    except PermissionError:
        parser.exit(1, "Cannot access /dev/uinput. See docs/remote-controller.md; do not run Gauntlet as root.\n")
    except (OSError, ValueError, ConnectionError) as exc:
        parser.exit(1, f"Remote controller stopped: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
