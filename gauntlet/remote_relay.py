"""Ephemeral, single-guest controller rooms. The relay never receives video or ROMs."""
import argparse
import asyncio
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import time
from urllib.parse import urlsplit

from aiohttp import WSMsgType, web

from .remote_input import validate_state


@dataclass
class Room:
    host: web.WebSocketResponse
    token: str
    guest: web.WebSocketResponse | None = None


async def send(ws, value):
    await asyncio.wait_for(ws.send_json(value), timeout=0.5)


def create_app(key, max_rooms=8):
    if len(key) < 32 or not key.isascii():
        raise ValueError("GAUNTLET_RELAY_KEY must contain at least 32 ASCII characters")
    if max_rooms < 1:
        raise ValueError("max_rooms must be positive")
    rooms = {}
    pending_guests = 0
    assets = Path(__file__).with_name("remote_web")

    @web.middleware
    async def headers(request, handler):
        response = await handler(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
                                       "connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
            "Permissions-Policy": "gamepad=(self)",
        })
        return response

    async def index(request):
        return web.FileResponse(assets / "index.html")

    async def script(request):
        return web.FileResponse(assets / "controller.js")

    async def style(request):
        return web.FileResponse(assets / "style.css")

    async def host(request):
        supplied = request.headers.get("Authorization", "").encode()
        if not secrets.compare_digest(supplied, f"Bearer {key}".encode()):
            raise web.HTTPUnauthorized(text="Host authentication required")
        if len(rooms) >= max_rooms:
            raise web.HTTPServiceUnavailable(text="Relay full")
        ws = web.WebSocketResponse(heartbeat=10, max_msg_size=4096)
        room_id, token = secrets.token_urlsafe(12), secrets.token_urlsafe(32)
        room = Room(ws, token)
        rooms[room_id] = room
        try:
            await ws.prepare(request)
            await send(ws, {"type": "session", "room": room_id, "token": token})
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    await ws.close(code=1008, message=b"Host accepts input only")
                    break
        finally:
            rooms.pop(room_id, None)
            if room.guest is not None:
                await room.guest.close(code=1001, message=b"Host left; invite revoked")
        return ws

    async def controller(request):
        nonlocal pending_guests
        try:
            origin = urlsplit(request.headers.get("Origin", ""))
        except ValueError:
            raise web.HTTPForbidden(text="Invalid browser origin") from None
        if origin.scheme not in ("http", "https") or origin.netloc != request.host:
            raise web.HTTPForbidden(text="Same-origin browser connection required")
        if pending_guests >= 32:
            raise web.HTTPServiceUnavailable(text="Too many pending connections")
        pending_guests += 1
        ws = web.WebSocketResponse(heartbeat=10, max_msg_size=4096)
        room = None
        try:
            await ws.prepare(request)
            auth = await ws.receive_json(timeout=5)
            if not isinstance(auth, dict) or not isinstance(auth.get("room"), str):
                raise ValueError("Invalid invite")
            room = rooms.get(auth["room"])
            token = auth.get("token")
            if (room is None or not isinstance(token, str)
                    or not secrets.compare_digest(token.encode(), room.token.encode())):
                raise ValueError("Invalid or expired invite")
            if room.guest is not None:
                raise ValueError("Controller already connected")
            if room.host.closed:
                raise ValueError("Host disconnected")
            room.guest = ws
            await send(room.host, {"type": "connected"})
            await send(ws, {"type": "ready"})
            window, count = time.monotonic(), 0
            async for message in ws:
                if message.type != WSMsgType.TEXT:
                    break
                now = time.monotonic()
                if now - window >= 1:
                    window, count = now, 0
                count += 1
                if count > 120:
                    raise ValueError("Controller rate limit exceeded")
                await send(room.host, validate_state(json.loads(message.data)))
        except (ValueError, TypeError, asyncio.TimeoutError) as exc:
            await ws.close(code=1008, message=str(exc).encode()[:120])
        except (ConnectionError, RuntimeError):
            await ws.close(code=1011, message=b"Relay connection lost")
        finally:
            pending_guests -= 1
            if room is not None and room.guest is ws:
                room.guest = None
                if not room.host.closed:
                    try:
                        await send(room.host, {"type": "disconnected"})
                    except (ConnectionError, RuntimeError, asyncio.TimeoutError):
                        await room.host.close(code=1011, message=b"Host not receiving")
        return ws

    async def shutdown(app):
        for room in list(rooms.values()):
            await room.host.close(code=1001, message=b"Relay shutting down")
            if room.guest is not None:
                await room.guest.close(code=1001, message=b"Relay shutting down")

    app = web.Application(middlewares=[headers], client_max_size=4096)
    app.router.add_get("/", index)
    app.router.add_get("/controller.js", script)
    app.router.add_get("/style.css", style)
    app.router.add_get("/host", host)
    app.router.add_get("/controller", controller)
    app.on_shutdown.append(shutdown)
    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="Host Gauntlet controller rooms behind an HTTPS reverse proxy.")
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--max-rooms", type=int, default=8)
    args = parser.parse_args(argv)
    try:
        app = create_app(os.environ.get("GAUNTLET_RELAY_KEY", ""), args.max_rooms)
    except ValueError as exc:
        parser.error(str(exc))
    # No request logging: controller invites and host credentials must not enter access logs.
    web.run_app(app, host=args.bind, port=args.port, access_log=None)


if __name__ == "__main__":
    main()
