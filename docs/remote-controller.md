# Remote controller + Discord

Up to three remote players can each send a controller from a browser while you stream your
desktop with Discord. Only your desktop runs Gauntlet, RetroArch, cores and ROMs. This is
controller forwarding, not rollback netplay; Discord's video delay may make precise or fast
games frustrating.

The first version supports a **Linux host**, one remote controller per bridge (Gauntlet can run
three bridges at once), and a self-hosted internet relay. Your friends can use a recent desktop
Chrome, Edge or Firefox with a standard
Gamepad API controller, or the page's keyboard fallback. Neither player needs port forwarding or
Tailscale. Video and audio are entirely separate, through Discord.

## 1. Run the relay on a server

Use an internet-accessible Linux server with Python 3.11+, a domain and HTTPS. From a checkout:

```sh
python3 -m venv .venv
.venv/bin/pip install ".[relay]"
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Save that random key privately. Set it on the server and later on the desktop. Do not send it to
your friend or commit it. You can enter it without putting it in shell history:

```sh
read -rs -p "Relay key: " GAUNTLET_RELAY_KEY; echo
export GAUNTLET_RELAY_KEY
.venv/bin/gauntlet-relay --bind 127.0.0.1 --port 8765
```

Put an HTTPS reverse proxy in front of port 8765. For example, a Caddy site:

```caddyfile
controls.example.com {
    reverse_proxy 127.0.0.1:8765
}
```

Caddy handles certificates and WebSocket upgrades. Preserve the public `Host` header (Caddy does
this by default); the relay checks browser origins. Expose only the proxy's HTTPS port, not
8765. Use your normal service manager to keep the relay running, with the key in a protected
environment file. This feature does not provision a server, domain or TLS certificate.

The relay requires the private key to create a room. It allows eight rooms by default
(`--max-rooms`), caps pending/active browser connections at 32 and limits each controller to
120 snapshots/second. Rooms are in memory: restarting the relay or closing the host bridge
revokes their invites. Serve it at the domain root, not a URL subpath.

## 2. Allow virtual controllers on your Linux desktop

The bridge needs the `uinput` kernel module and write permission on `/dev/uinput`.
**Do not run the bridge or Gauntlet as root.** If your account already has access, skip this.

An administrator can load the module with `sudo modprobe uinput` and arrange for it to load on
boot, then grant access through a dedicated group and udev rule, for example:

```sh
sudo groupadd -f gauntlet-input
sudo usermod -aG gauntlet-input "$USER"
echo 'KERNEL=="uinput", SUBSYSTEM=="misc", GROUP="gauntlet-input", MODE="0660"' \
  | sudo tee /etc/udev/rules.d/70-gauntlet-uinput.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=misc --sysname-match=uinput
```

Log out and back in for group membership to apply. Membership grants the ability to create
virtual input devices, so grant it only to trusted local users; do not make `/dev/uinput`
world-writable. Desktop input-device permissions must also let pygame and RetroArch read the
new gamepad, just as they would a physical controller. Sandboxed/Flatpak RetroArch needs access
to gamepad devices too.

## 3. Create invites in Gauntlet

Install the optional desktop dependencies with `.venv/bin/pip install ".[remote]"`.
Save the server's private relay key in `remote-relay.key` inside your Gauntlet state folder
(normally `~/.local/share/gauntlet` on Linux), readable only by your account (`chmod 600`).
Alternatively, launch Gauntlet with `GAUNTLET_RELAY_KEY` set; the environment takes precedence.
Never put this key in game files or settings, commit it, or send it to a friend.

Open **Remote Controller** on the main menu, set **Relay URL** to your public HTTPS origin,
then select **Create Invite** under a remote player slot. Repeat for up to three friends.
Each slot creates its own invite and virtual gamepad. Once a slot reads **Waiting for friend**,
select its **Copy Invite Link** and send that link privately. The screen displays each
connection status and any hosting errors. Keep the invite screen off your Discord stream.

Return to the main menu and start or resume your session. Each virtual gamepad is hot-plugged;
you do not need to restart Gauntlet. Join yourself first, then have each friend open their own
link, click **Connect controller** and press A to join on the Players screen.
Leaving the invite screen keeps all bridges running. A guest disconnect releases only their
controls but keeps that pad and invite available for reconnection. **Revoke Invite** stops that
bridge, removes its pad and invalidates its invite; quitting Gauntlet revokes all invites.
Create a replacement invite before reassigning players if a bridge was revoked. Do not also run
the standalone bridge for a friend who already has an in-game invite.

### Standalone bridge (optional)

From your desktop checkout, install the optional dependencies and enter the same private relay key:

```sh
.venv/bin/pip install ".[remote]"
read -rs -p "Relay key: " GAUNTLET_RELAY_KEY; echo
export GAUNTLET_RELAY_KEY
.venv/bin/gauntlet-remote --relay https://controls.example.com
```

The bridge creates **Gauntlet Remote Controller** and prints a private browser invite. Send
**only the invite** to your friend. It grants gamepad access to this room, not keyboard, mouse,
shell or desktop control. Anyone with the invite can claim the controller when it is free;
only one guest can occupy it. Ctrl+C on the bridge destroys the pad and revokes the invite.

Start the standalone bridge **before joining players**, so the device has settled in
the controller list. In Gauntlet, join yourself first. Your friend then opens the invite,
clicks **Connect controller** and presses A (or Z on the keyboard fallback) to join.
Gauntlet recognizes the virtual pad and writes explicit RetroArch bindings, selecting the
SDL2 joypad driver to match pygame's device indices. Leave `assign_ports` enabled and do not
override `input_joypad_driver` to a different driver in `retroarch_overrides`.
The layout maps browser A/B/X/Y to the corresponding physical positions of a standard
controller (RetroArch B/A/Y/X). D-pad, both sticks, shoulders, digital triggers, Select and
Start are forwarded; Guide is ignored. Analog trigger pressure, rumble and touch controls are
not implemented.

Versus matches route the pad to the joined player's port; turns and races route it to port 1
of that player's game. No ROMs or cores are needed on your friend's machine.

## 4. Stream through Discord

Share the game or your desktop, with audio, using Discord as you normally would. If Gauntlet
opens multiple RetroArch windows for a race, share the desktop so they are all visible.
Your friend should watch Discord while keeping the controller page focused (for example,
Discord's desktop app/video pop-out next to the browser).

The browser sends full button/stick snapshots 30 times per second, including neutral snapshots.
Switching focus, hiding the page, unplugging the controller or disconnecting releases controls.
The bridge also releases everything after 0.5 seconds without a state, or immediately on
socket loss. It keeps the virtual pad alive during a guest disconnect so its player/device
assignment stays stable; reconnect using the page's button. Reopening an invite works too,
but refreshing the page requires reopening the original invite because the page removes its
credentials from the address bar. Host/relay restarts require a new invite and player setup.
The remote player does not automatically forfeit on network loss; the host can use the match
menu to forfeit or cancel.

## Local check and troubleshooting

For a local-only smoke test, run the relay on `127.0.0.1` and the bridge with
`--relay http://127.0.0.1:8765`, then open its invite on that desktop. The bridge rejects plain
HTTP internet addresses; Gamepad API support also generally requires HTTPS or localhost.

- **No invite / 401:** the relay and desktop need the same `GAUNTLET_RELAY_KEY`.
- **Permission denied:** check `/dev/uinput`, module loading and group membership.
- **Page connects but no pad detected:** press a physical controller button. Use desktop Chrome,
  Edge or Firefox; embedded/app browser panels (e.g. WebKitGTK) often expose no gamepads and
  never report focus, so they send only released controls. Pads without a standard browser
  mapping are used best-effort; the keyboard fallback always works. Some browsers block gamepad
  access in private mode.
- **Pad does not appear in Gauntlet/RetroArch:** check read access to its `/dev/input/event*`
  device, sandbox device access and SDL2 joypad support. Restart Gauntlet after starting the bridge.
- **Invite rejected:** the room expired, is occupied, or the reverse proxy changed `Host`.
- **Controls stop when watching Discord:** the controller page must stay focused.
- **High delay:** use a geographically nearby relay, wired connections and lower-latency stream
  settings. Input forwarding cannot remove Discord's video buffering.

The relay operator can observe controller traffic. Use a trusted server, HTTPS and private
invites. This prototype has no account system or automatic server deployment, and the standalone
remote commands are installed from Python source, not bundled in the desktop executable.
