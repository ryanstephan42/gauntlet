"use strict";

const status = document.querySelector("#status");
const device = document.querySelector("#device");
const held = document.querySelector("#held");
const connect = document.querySelector("#connect");
const disconnect = document.querySelector("#disconnect");
const invite = new URLSearchParams(location.hash.slice(1));
const room = invite.get("room");
const token = invite.get("token");
// Keep the invite out of history, referrers and accidental URL sharing after opening it.
history.replaceState(null, "", location.pathname);
const keys = new Set();
const bindings = {
  KeyZ: 0, KeyX: 1, KeyA: 2, KeyS: 3, KeyQ: 4, KeyW: 5, Digit1: 6, Digit2: 7,
  ShiftLeft: 8, ShiftRight: 8, Enter: 9, ArrowUp: 12, ArrowDown: 13, ArrowLeft: 14, ArrowRight: 15,
};
const names = ["A", "B", "X", "Y", "LB", "RB", "LT", "RT", "Select", "Start", "LS", "RS",
  "Up", "Down", "Left", "Right", "Guide"];
let socket = null;
let ready = false;
let timer = null;
let activePad = null;

function neutral() {
  return {type: "state", buttons: Array(17).fill(false), axes: Array(4).fill(0)};
}

function release() {
  keys.clear();
  if (ready && socket?.readyState === WebSocket.OPEN && socket.bufferedAmount < 2048) {
    socket.send(JSON.stringify(neutral()));
  }
  held.textContent = "No controls held.";
}

function stop(message) {
  release();
  ready = false;
  clearInterval(timer);
  timer = null;
  if (socket) {
    const old = socket;
    socket = null;
    old.close();
  }
  status.textContent = message;
  connect.disabled = !room || !token;
  disconnect.disabled = true;
}

function snapshot() {
  if (!ready || socket?.readyState !== WebSocket.OPEN) return;
  if (socket.bufferedAmount > 2048) {
    stop("Connection is too slow. Controls released; reconnect to try again.");
    return;
  }
  const state = neutral();
  if (document.hasFocus() && !document.hidden) {
    const pads = navigator.getGamepads
      ? Array.from(navigator.getGamepads()).filter(p => p && !p.id.includes("Gauntlet Remote Controller"))
      : [];
    let pad = pads.find(p => p && p.index === activePad);
    if (!pad) {
      // Prefer a standard-mapped pad; otherwise use any pad with best-effort button order.
      pad = pads.find(p => p.mapping === "standard") || pads[0];
      activePad = pad ? pad.index : null;
    }
    if (pad) {
      device.textContent = pad.mapping === "standard"
        ? pad.id
        : `${pad.id} (non-standard mapping: buttons may be in a different order)`;
      for (let i = 0; i < 16; i++) state.buttons[i] = Boolean(pad.buttons[i]?.pressed);
      for (let i = 0; i < 4; i++) {
        const value = pad.axes[i] ?? 0;
        state.axes[i] = Number.isFinite(value) ? Math.max(-1, Math.min(1, value)) : 0;
      }
    } else {
      device.textContent = navigator.getGamepads
        ? "No controller detected. Press a controller button. If it still isn't found, this browser "
          + "may not support controllers: use Chrome, Edge or Firefox, or the keyboard."
        : "This browser has no controller support. Use Chrome, Edge or Firefox, or the keyboard.";
    }
    for (const key of keys) state.buttons[bindings[key]] = true;
    const sticks = [["Left stick", 0], ["Right stick", 2]]
      .filter(([, i]) => Math.hypot(state.axes[i], state.axes[i + 1]) > 0.2)
      .map(([name, i]) => `${name} ${state.axes[i].toFixed(2)}, ${state.axes[i + 1].toFixed(2)}`);
    held.textContent = [...state.buttons.map((pressed, i) => pressed ? names[i] : "").filter(Boolean), ...sticks]
      .join(" / ") || "No controls held.";
    status.textContent = "Connected. Controls active while this page is focused.";
  } else {
    status.textContent = "Connected, controls released. Focus this page to play.";
  }
  socket.send(JSON.stringify(state));
}

connect.addEventListener("click", () => {
  if (!room || !token || socket) return;
  connect.disabled = true;
  disconnect.disabled = false;
  status.textContent = "Connecting...";
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/controller`);
  socket = ws;
  ws.addEventListener("open", () => ws.send(JSON.stringify({room, token})));
  ws.addEventListener("message", event => {
    if (socket !== ws) return;
    try {
      if (JSON.parse(event.data).type !== "ready") throw new Error("Unexpected relay message");
      ready = true;
      timer = setInterval(snapshot, 1000 / 30);
      snapshot();
    } catch {
      stop("Invalid relay response. Controls released.");
    }
  });
  ws.addEventListener("close", event => {
    if (socket === ws) stop(`Disconnected: ${event.reason || "connection lost"}. Reconnect or request a new invite.`);
  });
  ws.addEventListener("error", () => {
    if (socket === ws) stop("Connection failed. Check your network and invite.");
  });
});
disconnect.addEventListener("click", () => stop("Disconnected. Controls released."));
window.addEventListener("keydown", event => {
  if (!ready || !(event.code in bindings)) return;
  // Enter/Space on a focused button should not accidentally disconnect while playing.
  event.preventDefault();
  keys.add(event.code);
});
window.addEventListener("keyup", event => {
  if (!(event.code in bindings)) return;
  if (ready) event.preventDefault();
  keys.delete(event.code);
});
window.addEventListener("blur", release);
document.addEventListener("visibilitychange", () => { if (document.hidden) release(); });
window.addEventListener("gamepaddisconnected", () => { activePad = null; release(); });
window.addEventListener("pagehide", () => stop("Page closed."));
if (room && token) {
  connect.disabled = false;
  status.textContent = "Invite ready. Connect your controller, then click Connect controller.";
}
