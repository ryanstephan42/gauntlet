import asyncio
from contextlib import suppress
import copy
import json
import os

from aiohttp import ClientSession, WSServerHandshakeError, WSMsgType
from aiohttp.test_utils import TestServer
import pytest

from gauntlet.match import Participant, build_config, race_config
from gauntlet.remote_input import (NEUTRAL, PAD_NAME, RemoteController, VirtualPad, receive_inputs,
                                   relay_url, validate_state)
from gauntlet.remote_relay import create_app
from gauntlet.settings import Settings


KEY = "test-relay-key-with-at-least-32-characters"


def state():
    value = copy.deepcopy(NEUTRAL)
    value["buttons"][0] = True
    value["buttons"][7] = True
    value["buttons"][14] = True
    value["axes"] = [0.5, -1, 0, 1]
    return value


class RecordingPad:
    def __init__(self):
        self.states = []
        self.event = asyncio.Event()

    def apply(self, value):
        self.states.append(copy.deepcopy(value))
        self.event.set()

    async def wait_for(self, expected):
        async with asyncio.timeout(2):
            while not self.states or self.states[-1] != expected:
                self.event.clear()
                await self.event.wait()


@pytest.mark.parametrize("bad", [
    None, [], {}, {"type": "command", "buttons": [False] * 17, "axes": [0] * 4},
    {**NEUTRAL, "buttons": [False] * 16}, {**NEUTRAL, "buttons": [0] * 17},
    {**NEUTRAL, "axes": [0] * 3}, {**NEUTRAL, "axes": [True, 0, 0, 0]},
    {**NEUTRAL, "axes": [float("nan"), 0, 0, 0]},
    {**NEUTRAL, "axes": [float("inf"), 0, 0, 0]},
    {**NEUTRAL, "axes": [10 ** 400, 0, 0, 0]},
    {**NEUTRAL, "axes": [1.01, 0, 0, 0]}, {**NEUTRAL, "command": "QUIT"},
])
def test_invalid_snapshots(bad):
    with pytest.raises(ValueError):
        validate_state(bad)


def test_valid_snapshots():
    assert validate_state(NEUTRAL) == NEUTRAL
    assert validate_state(state()) == state()


@pytest.mark.parametrize("url", [
    "ws://localhost:8765", "http://example.com", "https://user:pass@example.com",
    "https://example.com/path", "https://example.com/?token=secret", "https://example.com/#fragment",
])
def test_unsafe_relay_url(url):
    with pytest.raises(ValueError):
        relay_url(url)


def test_relay_urls():
    assert relay_url("https://controls.example.com/") == "https://controls.example.com"
    assert relay_url("http://127.0.0.1:8765") == "http://127.0.0.1:8765"


def test_remote_retroarch_ports():
    local = Participant(1, "Local", 1, 0)
    remote = Participant(2, "Friend", 2, 1, remote=True)
    settings = Settings()
    cfg = build_config([local, remote], [], settings)
    assert cfg["input_joypad_driver"] == "sdl2"
    assert cfg["input_player2_joypad_index"] == 1
    assert cfg["input_player2_b_btn"] == "0"
    assert cfg["input_player2_up_btn"] == "h0up"
    assert cfg["input_player2_up_axis"] == "-1"
    assert cfg["input_player2_l2_btn"] == "nul"
    assert cfg["input_player2_l2_axis"] == "+2"
    assert cfg["input_player2_r_x_plus_axis"] == "+3"
    assert "input_player1_b_btn" not in cfg
    turn = build_config([local, remote], [], settings, turn_player=2)
    assert turn["input_player1_joypad_index"] == 1
    assert turn["input_player1_start_btn"] == "7"
    assert "input_player2_start_btn" not in turn
    race = race_config([local, remote], [], settings, 1)
    assert race["input_player1_b"] == "nul"  # no host keyboard leakage
    assert race["input_player1_joypad_index"] == 1
    assert race["input_player1_start_btn"] == "7"
    assert "input_joypad_driver" not in build_config([local], [], settings)


def test_remote_menu_and_participant_assignment():
    from types import SimpleNamespace

    import pygame

    from gauntlet.inputmap import Action
    from gauntlet.pg_input import PygameInput
    from gauntlet.session import Player
    from gauntlet.ui.flow import make_participants

    inp = PygameInput.__new__(PygameInput)
    inp.pads = {12: SimpleNamespace(get_name=lambda: PAD_NAME),
                13: SimpleNamespace(get_name=lambda: PAD_NAME)}
    inp.pad_index = {12: 2, 13: 3}
    for button, action in ((0, Action.CONFIRM), (6, Action.SELECT), (7, Action.START)):
        assert inp.translate(SimpleNamespace(type=pygame.JOYBUTTONDOWN, instance_id=12, button=button)).action == action
    assert inp.translate(SimpleNamespace(type=pygame.JOYBUTTONDOWN, instance_id=12, button=9)) is None
    assert inp.is_held("pad:12", Action.SELECT, Action.START)
    app = SimpleNamespace(input=inp)
    parts = make_participants(app, [(1, Player(1, "Host", device="keyboard")),
                                    (2, Player(2, "Friend", device="pad:12")),
                                    (3, Player(3, "Friend 2", device="pad:13"))])
    assert parts[1].remote
    assert parts[1].pad_index == 2
    assert parts[2].remote
    assert parts[2].pad_index == 3
    assert not parts[0].remote


def test_virtual_pad_mapping():
    from types import SimpleNamespace

    names = ("EV_KEY EV_ABS BTN_SOUTH BTN_EAST BTN_NORTH BTN_WEST BTN_TL BTN_TR BTN_SELECT BTN_START "
             "BTN_THUMBL BTN_THUMBR BTN_MODE ABS_X ABS_Y ABS_RX ABS_RY ABS_Z ABS_RZ ABS_HAT0X ABS_HAT0Y").split()
    codes = SimpleNamespace(**{name: i for i, name in enumerate(names)})

    class Device:
        def __init__(self):
            self.values = {}
            self.syns = 0

        def write(self, kind, code, value):
            self.values[kind, code] = value

        def syn(self):
            self.syns += 1

    pad = VirtualPad.__new__(VirtualPad)
    pad.e = codes
    pad.device = Device()
    pad.buttons = (codes.BTN_SOUTH, codes.BTN_EAST, codes.BTN_NORTH, codes.BTN_WEST,
                   codes.BTN_TL, codes.BTN_TR, None, None, codes.BTN_SELECT, codes.BTN_START,
                   codes.BTN_THUMBL, codes.BTN_THUMBR)
    pad.axes = (codes.ABS_X, codes.ABS_Y, codes.ABS_RX, codes.ABS_RY)
    pad.apply(state())
    assert pad.device.values[codes.EV_KEY, codes.BTN_SOUTH] == 1
    assert pad.device.values[codes.EV_ABS, codes.ABS_RZ] == 255
    assert pad.device.values[codes.EV_ABS, codes.ABS_X] == 16384
    assert pad.device.values[codes.EV_ABS, codes.ABS_HAT0X] == -1
    pad.apply(NEUTRAL)
    assert set(pad.device.values.values()) == {0}
    assert pad.device.syns == 2


def test_relay_browser_bridge_roundtrip():
    """Real HTTP/WebSocket transport, bridge watchdog, guest reconnect and invite revocation."""
    async def run():
        pad = RecordingPad()
        async with TestServer(create_app(KEY)) as server, ClientSession() as client:
            origin = str(server.make_url("")).rstrip("/")
            async with client.get(server.make_url("/")) as response:
                assert response.status == 200
                assert "Gauntlet remote controller" in await response.text()
                assert response.headers["Referrer-Policy"] == "no-referrer"
                assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
            async with client.ws_connect(server.make_url("/host"),
                                         headers={"Authorization": f"Bearer {KEY}"}) as host:
                invite = asyncio.get_running_loop().create_future()
                task = asyncio.create_task(receive_inputs(host, pad, invite.set_result))
                try:
                    session = await asyncio.wait_for(invite, 2)
                    async with client.ws_connect(server.make_url("/controller"), origin=origin) as guest:
                        await guest.send_json({"room": session["room"], "token": session["token"]})
                        assert await guest.receive_json(timeout=2) == {"type": "ready"}
                        await guest.send_json(state())
                        await pad.wait_for(state())
                        await pad.wait_for(NEUTRAL)  # 0.5s watchdog while guest/socket stay open
                        await guest.send_json(state())
                        await pad.wait_for(state())
                    await pad.wait_for(NEUTRAL)  # guest close releases immediately
                    async with client.ws_connect(server.make_url("/controller"), origin=origin) as guest:
                        await guest.send_json({"room": session["room"], "token": session["token"]})
                        assert await guest.receive_json(timeout=2) == {"type": "ready"}
                        await guest.send_json(state())
                        await pad.wait_for(state())
                        await host.close()
                        async with asyncio.timeout(2):
                            while (await guest.receive()).type not in (WSMsgType.CLOSE, WSMsgType.CLOSED):
                                pass
                    with pytest.raises(ConnectionError):
                        await asyncio.wait_for(task, 2)
                    assert pad.states[-1] == NEUTRAL
                    async with client.ws_connect(server.make_url("/controller"), origin=origin) as stale:
                        await stale.send_json({"room": session["room"], "token": session["token"]})
                        assert (await stale.receive(timeout=2)).type == WSMsgType.CLOSE
                finally:
                    task.cancel()
                    with suppress(asyncio.CancelledError, ConnectionError):
                        await task

    asyncio.run(run())


def test_relay_auth_occupancy_and_validation():
    async def run():
        async with TestServer(create_app(KEY, max_rooms=1)) as server, ClientSession() as client:
            origin = str(server.make_url("")).rstrip("/")
            for headers in ({}, {"Authorization": "Bearer wrong"}):
                with pytest.raises(WSServerHandshakeError) as exc:
                    await client.ws_connect(server.make_url("/host"), headers=headers)
                assert exc.value.status == 401
            with pytest.raises(WSServerHandshakeError) as exc:
                await client.ws_connect(server.make_url("/controller"), origin="https://evil.example")
            assert exc.value.status == 403
            auth = {"Authorization": f"Bearer {KEY}"}
            async with client.ws_connect(server.make_url("/host"), headers=auth) as host:
                session = await host.receive_json(timeout=2)
                with pytest.raises(WSServerHandshakeError) as exc:
                    await client.ws_connect(server.make_url("/host"), headers=auth)
                assert exc.value.status == 503
                credentials = {"room": session["room"], "token": session["token"]}
                async with client.ws_connect(server.make_url("/controller"), origin=origin) as wrong:
                    await wrong.send_json({**credentials, "token": "wrong"})
                    assert (await wrong.receive(timeout=2)).type == WSMsgType.CLOSE
                async with client.ws_connect(server.make_url("/controller"), origin=origin) as guest:
                    await guest.send_json(credentials)
                    assert await guest.receive_json(timeout=2) == {"type": "ready"}
                    assert await host.receive_json(timeout=2) == {"type": "connected"}
                    async with client.ws_connect(server.make_url("/controller"), origin=origin) as duplicate:
                        await duplicate.send_json(credentials)
                        assert (await duplicate.receive(timeout=2)).type == WSMsgType.CLOSE
                    await guest.send_str(json.dumps({**NEUTRAL, "axes": ["bad", 0, 0, 0]}))
                    assert (await guest.receive(timeout=2)).type == WSMsgType.CLOSE
                    assert await host.receive_json(timeout=2) == {"type": "disconnected"}

    asyncio.run(run())


def test_app_owned_bridge_lifecycle(monkeypatch, tmp_path):
    """App controller owns real WebSockets, preserves reconnects and revokes on stop."""
    from urllib.parse import parse_qs, urlsplit

    import gauntlet.remote_input as remote_input

    pads = []

    class Pad:
        def __init__(self):
            self.states = []
            self.closed = False
            pads.append(self)

        def apply(self, value):
            self.states.append(copy.deepcopy(value))

        def close(self):
            self.closed = True

    monkeypatch.setattr(remote_input, "VirtualPad", Pad)
    monkeypatch.delenv("GAUNTLET_RELAY_KEY", raising=False)
    key_file = tmp_path / "relay.key"
    key_file.write_text(KEY)
    controller = RemoteController()

    async def until(predicate):
        async with asyncio.timeout(4):
            while True:
                controller.poll()
                if predicate():
                    return
                await asyncio.sleep(0.01)

    async def run():
        async with TestServer(create_app(KEY)) as server, ClientSession() as client:
            origin = str(server.make_url("")).rstrip("/")
            controller.start(origin, key_file)
            try:
                await until(lambda: controller.invite)
                invite = controller.invite
                credentials = {k: v[0] for k, v in parse_qs(urlsplit(invite).fragment).items()}
                with pytest.raises(ValueError, match="Revoke"):
                    controller.start(origin, key_file)
                async with client.ws_connect(server.make_url("/controller"), origin=origin) as guest:
                    await guest.send_json(credentials)
                    assert await guest.receive_json(timeout=2) == {"type": "ready"}
                    await until(lambda: controller.status == "Friend connected")
                    await guest.send_json(state())
                    await until(lambda: pads[0].states[-1] == state())
                await until(lambda: "disconnected" in controller.status)
                assert controller.invite == invite
                assert pads[0].states[-1] == NEUTRAL
                # Stop in another thread so the in-process relay can finish its close handshake.
                await asyncio.to_thread(controller.stop)
                assert not controller.active and not controller.invite
                assert pads[0].closed
                async with client.ws_connect(server.make_url("/controller"), origin=origin) as stale:
                    await stale.send_json(credentials)
                    assert (await stale.receive(timeout=2)).type == WSMsgType.CLOSE
                controller.start(origin, key_file)
                await until(lambda: controller.invite)
                assert controller.invite != invite
            finally:
                await asyncio.to_thread(controller.stop)
            # Auth failures are shown, never left looking like a valid invite.
            key_file.write_text("wrong-" + KEY)
            controller.start(origin, key_file)
            await until(lambda: not controller.active)
            assert controller.error and controller.invite == ""
            assert pads[-1].closed

    asyncio.run(run())


def test_two_app_bridges_have_independent_guests(monkeypatch, tmp_path):
    """Two friends can join separate rooms and releasing one never affects the other."""
    from urllib.parse import parse_qs, urlsplit

    import gauntlet.remote_input as remote_input

    pads = []

    class Pad:
        def __init__(self):
            self.states = []
            self.closed = False
            pads.append(self)

        def apply(self, value):
            self.states.append(copy.deepcopy(value))

        def close(self):
            self.closed = True

    monkeypatch.setattr(remote_input, "VirtualPad", Pad)
    key_file = tmp_path / "relay.key"
    key_file.write_text(KEY)
    controllers = [RemoteController(), RemoteController()]

    async def until(predicate):
        async with asyncio.timeout(4):
            while True:
                for controller in controllers:
                    controller.poll()
                if predicate():
                    return
                await asyncio.sleep(0.01)

    async def run():
        async with TestServer(create_app(KEY)) as server, ClientSession() as client:
            origin = str(server.make_url("")).rstrip("/")
            try:
                controllers[0].start(origin, key_file)
                await until(lambda: controllers[0].invite and len(pads) == 1)
                controllers[1].start(origin, key_file)
                await until(lambda: controllers[1].invite and len(pads) == 2)
                assert controllers[0].invite != controllers[1].invite
                credentials = [
                    {k: v[0] for k, v in parse_qs(urlsplit(c.invite).fragment).items()}
                    for c in controllers
                ]
                async with client.ws_connect(server.make_url("/controller"), origin=origin) as first, \
                        client.ws_connect(server.make_url("/controller"), origin=origin) as second:
                    await first.send_json(credentials[0])
                    await second.send_json(credentials[1])
                    assert await first.receive_json(timeout=2) == {"type": "ready"}
                    assert await second.receive_json(timeout=2) == {"type": "ready"}
                    await until(lambda: all(c.status == "Friend connected" for c in controllers))
                    await first.send_json(state())
                    await second.send_json(NEUTRAL | {"buttons": [True] + [False] * 16})
                    await until(lambda: pads[0].states[-1] == state()
                                and pads[1].states[-1]["buttons"][0])
                    assert pads[0].states[-1] != pads[1].states[-1]
                await until(lambda: all("disconnected" in c.status for c in controllers))
                assert pads[0].states[-1] == pads[1].states[-1] == NEUTRAL
                await asyncio.to_thread(controllers[0].stop)
                assert pads[0].closed and not pads[1].closed
                async with client.ws_connect(server.make_url("/controller"), origin=origin) as active:
                    await active.send_json(credentials[1])
                    assert await active.receive_json(timeout=2) == {"type": "ready"}
                    await active.send_json(state())
                    await until(lambda: pads[1].states[-1] == state())
                await until(lambda: "disconnected" in controllers[1].status)
            finally:
                for controller in controllers:
                    await asyncio.to_thread(controller.stop)

    asyncio.run(run())


def test_app_bridge_configuration_errors(monkeypatch, tmp_path):
    monkeypatch.delenv("GAUNTLET_RELAY_KEY", raising=False)
    controller = RemoteController()
    with pytest.raises(ValueError, match="Save the private relay key"):
        controller.start("https://controls.example.com", tmp_path / "missing.key")
    monkeypatch.setenv("GAUNTLET_RELAY_KEY", "short")
    with pytest.raises(ValueError, match="32 ASCII"):
        controller.start("https://controls.example.com", tmp_path / "missing.key")
    assert not controller.active


@pytest.mark.skipif(os.environ.get("GAUNTLET_TEST_UINPUT") != "1", reason="requires opt-in and /dev/uinput access")
def test_real_uinput_relay_roundtrip():
    """Opt-in hardware check: actual relay -> desktop bridge -> kernel gamepad events."""
    evdev = pytest.importorskip("evdev")

    async def run():
        pad = VirtualPad()
        assert pad.device.device.name == PAD_NAME
        try:
            async with TestServer(create_app(KEY)) as server, ClientSession() as client:
                origin = str(server.make_url("")).rstrip("/")
                async with client.ws_connect(server.make_url("/host"),
                                             headers={"Authorization": f"Bearer {KEY}"}) as host:
                    invite = asyncio.get_running_loop().create_future()
                    task = asyncio.create_task(receive_inputs(host, pad, invite.set_result))
                    try:
                        session = await asyncio.wait_for(invite, 2)
                        async with client.ws_connect(server.make_url("/controller"), origin=origin) as guest:
                            await guest.send_json({"room": session["room"], "token": session["token"]})
                            assert await guest.receive_json(timeout=2) == {"type": "ready"}
                            await guest.send_json(state())
                            async with asyncio.timeout(2):
                                async for event in pad.device.device.async_read_loop():
                                    if event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_SOUTH:
                                        assert event.value == 1
                                        break
                            await guest.close()
                            async with asyncio.timeout(2):
                                async for event in pad.device.device.async_read_loop():
                                    if event.type == evdev.ecodes.EV_KEY and event.code == evdev.ecodes.BTN_SOUTH:
                                        assert event.value == 0
                                        break
                    finally:
                        task.cancel()
                        with suppress(asyncio.CancelledError):
                            await task
        finally:
            pad.close()

    asyncio.run(run())
