"""Phase 7.4 prototype: two SNES games and the live scoreboard drawn in ONE window by Gauntlet itself.

    python prototypes/inwindow/demo.py bench            # headless numbers: frame time, input latency, sync
    python prototypes/inwindow/demo.py core CORE ROM [-o key=value] [--system-dir DIR]   # any core, 2 instances
    python prototypes/inwindow/demo.py play [--auto] [--seconds N] [--shot out.png] [--fullscreen] [--scaled]

play: player 1 and 2 use the first two gamepads (arrow keys + Z/X/A/S/Enter also drive player 1);
--auto feeds scripted inputs instead so it can run unattended. Esc quits.
"""
import argparse
import array
import os
import subprocess
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import libretro as lr  # noqa: E402

ROM = "/home/r/Downloads/SNES - TOP 100/snes/Super Mario World (USA).sfc"
STATE = os.path.join(os.path.dirname(__file__), "..", "..", "start_states", "smw_yi1.state")
COINS, SPEED_X, LEVEL, X_POS = 0x0DBF, 0x007B, 0x13BF, 0x0094
COLORS = [(230, 70, 80), (70, 130, 240)]
NAMES = ["Ryan", "Alex"]


def core_path(name="snes9x"):
    if os.environ.get("GAUNTLET_CORE"):
        return os.environ["GAUNTLET_CORE"]
    loc = subprocess.run(["flatpak", "info", "--show-location", "net.retrodeck.retrodeck"],
                         capture_output=True, text=True).stdout.strip()
    return os.path.join(loc, "files/retrodeck/components/retroarch/rd_extras/cores", f"{name}_libretro.so")


def start(n):
    blob = lr.read_state(STATE)
    cores = []
    for _ in range(n):
        c = lr.Core(core_path())
        c.load(ROM)
        c.load_state(blob)
        cores.append(c)
    return cores


def bench(args):
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    t = time.perf_counter()
    cores = start(2)
    print(f"boot 2x {cores[0].name} {cores[0].version} + start state: {(time.perf_counter() - t) * 1000:.0f} ms")
    print(f"timing {cores[0].fps:.4f} fps, audio {cores[0].sample_rate:.0f} Hz, geometry {cores[0].geometry}")
    run, conv, scale = lr.Stopwatch(), lr.Stopwatch(), lr.Stopwatch()
    for _ in range(args.frames):
        for c in cores:
            with run:
                c.run()
            with conv:
                surf = lr.to_surface(pygame, c.frame, c.pixel_format)
            with scale:
                pygame.transform.scale(surf, (1170, 1024))
            c.take_audio()
    print(f"retro_run per instance:         {run.summary()}")
    print(f"frame -> pygame Surface:        {conv.summary()}")
    print(f"scale 256x224 -> 1170x1024:     {scale.summary()}")

    # Same start state + same inputs = same game, frame for frame (what a fair race needs).
    a, b = (bytes(c.ram()) for c in cores)
    print("instances identical after", args.frames, "frames:", a == b)

    # Input latency inside the game: press RIGHT just before frame k, count frames until Mario moves.
    c = cores[0]
    c.load_state(lr.read_state(STATE))
    for _ in range(30):
        c.run()
    ram = c.ram()
    c.buttons = 1 << lr.RIGHT
    frames = 0
    while ram[SPEED_X] == 0 and frames < 30:
        c.run()
        frames += 1
    c.buttons = 0
    print(f"RIGHT -> Mario's x speed changes in RAM after {frames} frame(s) of emulation "
          "(frontend adds none: input is read right before retro_run)")

    # The referee's side: reading the coin counter straight from WRAM vs RetroArch's UDP round trip.
    t = time.perf_counter()
    for _ in range(10000):
        ram[COINS]
    print(f"RAM read: {(time.perf_counter() - t) / 10000 * 1e6:.2f} us (no network, no polling lag)")
    for c in cores:
        c.close()


def core_bench(args):
    """Two instances of any core side by side, e.g. N64 with the software RDP:
    demo.py core mupen64plus_next "Super Mario 64 (USA).z64" -o mupen64plus-rdp-plugin=angrylion"""
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import pygame
    pygame.init()
    opts = dict(o.split("=", 1) for o in args.option)
    t = time.perf_counter()
    cores = []
    for _ in range(2):
        c = lr.Core(core_path(args.core), system_dir=args.system_dir, options=opts)
        c.load(args.rom)
        cores.append(c)
    print(f"{cores[0].name} {cores[0].version}: boot 2x {(time.perf_counter() - t) * 1000:.0f} ms, "
          f"wants GL/Vulkan: {cores[0].hw_render_requested}, {cores[0].fps:.2f} fps")
    for _ in range(args.frames // 2):  # get past the boot screens
        for c in cores:
            c.run()
    both = lr.Stopwatch()
    for _ in range(args.frames // 2):
        with both:
            for c in cores:
                c.run()
    print(f"both instances per frame (budget {1000 / cores[0].fps:.1f} ms): {both.summary()}")
    print("picture", cores[0].frame and cores[0].frame[1:3], "| RAM", len(cores[0].ram() or ()), "bytes",
          "| instances identical:", bytes(cores[0].ram() or b"") == bytes(cores[1].ram() or b""))
    if args.shot and cores[0].frame:
        pygame.image.save(lr.to_surface(pygame, cores[0].frame, cores[0].pixel_format), args.shot)
    for c in cores:
        c.close()


class Audio:
    """Ring buffer feeding one SDL audio device; the cores' samples are mixed at half volume each."""

    def __init__(self, pygame, rate):
        from pygame._sdl2 import audio as sdl_audio
        self.buf = bytearray()
        self.lock = threading.Lock()
        self.underruns = 0
        self.dropped = 0
        self.rate = rate
        self.dev = sdl_audio.AudioDevice(None, False, int(rate), sdl_audio.AUDIO_S16, 2, 512, 0, self._callback)
        self.dev.pause(0)

    def _callback(self, dev, mem):
        n = len(mem)
        with self.lock:
            take = bytes(self.buf[:n])
            del self.buf[:n]
        if len(take) < n:
            self.underruns += 1
            take += bytes(n - len(take))
        mem[:] = take

    def push(self, chunks):
        mixed = array.array("h", chunks[0])
        for other in chunks[1:]:
            o = array.array("h", other)
            for i in range(min(len(mixed), len(o))):
                mixed[i] = (mixed[i] + o[i]) >> 1
        with self.lock:
            self.buf += mixed.tobytes()
            limit = int(self.rate * 4 * 0.12)  # keep at most ~120 ms queued
            if len(self.buf) > limit:
                self.dropped += len(self.buf) - limit
                del self.buf[:len(self.buf) - limit]

    def queued_ms(self):
        with self.lock:
            return len(self.buf) / 4 / self.rate * 1000

    def close(self):
        self.dev.close()


PAD_MAP = {0: lr.B, 1: lr.A, 2: lr.Y, 3: lr.X, 4: lr.L, 5: lr.R, 6: lr.SELECT, 7: lr.START}
KEY_MAP = {"up": lr.UP, "down": lr.DOWN, "left": lr.LEFT, "right": lr.RIGHT, "z": lr.B, "x": lr.A,
           "a": lr.Y, "s": lr.X, "return": lr.START}


def pad_buttons(js):
    bits = 0
    for btn, bit in PAD_MAP.items():
        if btn < js.get_numbuttons() and js.get_button(btn):
            bits |= 1 << bit
    if js.get_numhats():
        hx, hy = js.get_hat(0)
        bits |= (hx < 0) << lr.LEFT | (hx > 0) << lr.RIGHT | (hy > 0) << lr.UP | (hy < 0) << lr.DOWN
    if js.get_numaxes() >= 2:
        ax, ay = js.get_axis(0), js.get_axis(1)
        bits |= (ax < -0.5) << lr.LEFT | (ax > 0.5) << lr.RIGHT | (ay < -0.5) << lr.UP | (ay > 0.5) << lr.DOWN
    return bits


# Unattended play from the YI1 start state, 10-frame steps found by a backtracking search that
# never lets Mario die: r=run, j=run+jump, J=walk+jump, w=walk, n=nothing. P1 runs, P2 walks.
SCRIPTS = ["rrrrrjrrrrrrrrrrrrrrrLjrrrrrrrrjrrrwnnnrnnJrrrrrrrrrrrrrjrrrrrrrrrrrrrr",
           "wwwwwwJwwwwwwwwwwwwwwwwwwwwwwwwwwwwwJwwwwwwwwwwwwwwwwwJwwwwwwwwwwwnnnJw"]
def auto_buttons(player, frame):
    script = SCRIPTS[player]
    step = script[frame // 10] if frame // 10 < len(script) else "n"
    right, run, jump, left = 1 << lr.RIGHT, 1 << lr.Y, 1 << lr.B, 1 << lr.LEFT
    return {"r": right | run, "j": right | run | jump, "J": right | jump, "w": right, "n": 0, "L": left}[step]


def play(args):
    import pygame
    pygame.init()
    pygame.joystick.init()
    pads = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
    flags = pygame.FULLSCREEN if args.fullscreen else 0
    if args.scaled:  # draw at 1280x720 and let SDL's renderer (GPU) scale it to the display
        screen = pygame.display.set_mode((1280, 720), flags | pygame.SCALED, vsync=0)
    else:
        screen = pygame.display.set_mode((0, 0) if args.fullscreen else (args.width, args.height), flags)
    pygame.display.set_caption("Gauntlet in-window prototype")
    W, H = screen.get_size()
    cores = start(2)
    audio = None if args.mute else Audio(pygame, cores[0].sample_rate)
    font = pygame.font.SysFont("sans", max(18, H // 30), bold=True)
    big = pygame.font.SysFont("sans", max(30, H // 14), bold=True)
    strip_h = int(H * 0.25)
    tile_w, tile_h = W // 2, H - strip_h
    gw = min(tile_w - 24, int((tile_h - 24) * 4 / 3))
    gh = int(gw * 3 / 4)
    period = 1 / cores[0].fps
    frame_t, run_t, draw_t, late = lr.Stopwatch(), lr.Stopwatch(), lr.Stopwatch(), 0
    queued = []
    best = [0, 0]
    t_end = time.perf_counter() + args.seconds if args.seconds else None
    next_t = time.perf_counter()
    frame = 0
    shot_at = int(args.seconds * cores[0].fps * 0.8) if args.shot and args.seconds else None
    running = True
    while running:
        t0 = time.perf_counter()
        for e in pygame.event.get():
            if e.type == pygame.QUIT or (e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE):
                running = False
        keys = pygame.key.get_pressed()
        for i, c in enumerate(cores):
            if args.auto:
                c.buttons = auto_buttons(i, frame)
            else:
                c.buttons = pad_buttons(pads[i]) if i < len(pads) else 0
                if i == 0:
                    c.buttons |= sum(1 << bit for k, bit in KEY_MAP.items() if keys[pygame.key.key_code(k)])
        with run_t:
            for c in cores:
                c.run()
        if audio:
            audio.push([c.take_audio() for c in cores])
            queued.append(audio.queued_ms())
        with draw_t:
            screen.fill((14, 14, 22))
            for i, c in enumerate(cores):
                x = i * tile_w + (tile_w - gw) // 2
                y = (tile_h - gh) // 2
                pygame.draw.rect(screen, COLORS[i], (x - 6, y - 6, gw + 12, gh + 12), 6)
                screen.blit(pygame.transform.scale(lr.to_surface(pygame, c.frame, c.pixel_format), (gw, gh)), (x, y))
            # the strip: live RAM values, no RetroArch round trip
            sy = tile_h
            pygame.draw.rect(screen, (24, 24, 36), (0, sy, W, strip_h))
            for i, c in enumerate(cores):
                ram = c.ram()
                coins, dist = ram[COINS], (ram[X_POS] | ram[X_POS + 1] << 8) // 16
                best[i] = max(best[i], dist)
                px = 16 if i == 0 else W - W // 3 + 16
                pw = W // 3 - 32
                pygame.draw.rect(screen, COLORS[i], (px, sy + 14, pw, strip_h - 28), 4, border_radius=10)
                screen.blit(font.render(NAMES[i], True, (240, 240, 240)), (px + 20, sy + 26))
                screen.blit(font.render(f"coins {coins}", True, (190, 190, 200)), (px + 20, sy + 26 + font.get_height()))
                val = big.render(f"{dist} m", True, (240, 240, 240))
                screen.blit(val, (px + pw - val.get_width() - 20, sy + 20))
                pygame.draw.rect(screen, (50, 50, 66), (px + 20, sy + strip_h // 2 + 10, pw - 40, 18))
                pygame.draw.rect(screen, COLORS[i], (px + 20, sy + strip_h // 2 + 10, (pw - 40) * min(dist, 100) // 100, 18))
            left = max(0, (t_end - time.perf_counter())) if t_end else frame / cores[0].fps
            mid = big.render(f"{int(left) // 60}:{int(left) % 60:02d}", True, (255, 220, 60))
            screen.blit(mid, ((W - mid.get_width()) // 2, sy + 30))
            title = font.render("Distance - in-window prototype", True, (200, 200, 210))
            screen.blit(title, ((W - title.get_width()) // 2, sy + 30 + mid.get_height()))
            pygame.display.flip()
        if shot_at is not None and frame == shot_at:
            pygame.image.save(screen, args.shot)
        frame += 1
        frame_t.samples.append((time.perf_counter() - t0) * 1000)
        next_t += period
        delay = next_t - time.perf_counter()
        if delay > 0:
            time.sleep(delay)
        else:
            late += 1
            if delay < -period * 3:
                next_t = time.perf_counter()  # fell far behind; don't try to catch up
        if t_end and time.perf_counter() >= t_end:
            running = False
    print(f"{frame} frames in {W}x{H}; work per frame {frame_t.summary()}")
    print(f"  cores {run_t.summary()}")
    print(f"  draw+flip {draw_t.summary()}")
    print(f"  frames late: {late}")
    if audio:
        q = sorted(queued[60:]) or [0]
        print(f"  audio queued: median {q[len(q) // 2]:.0f} ms, p95 {q[int(len(q) * 0.95)]:.0f} ms, "
              f"underruns {audio.underruns}, dropped {audio.dropped // 4} samples")
        audio.close()
    print(f"  distance: {NAMES[0]} {best[0]} m, {NAMES[1]} {best[1]} m")
    for c in cores:
        c.close()
    pygame.quit()


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["bench", "play", "core"])
    p.add_argument("core", nargs="?", help="core mode: core name, e.g. swanstation")
    p.add_argument("rom", nargs="?", help="core mode: ROM path")
    p.add_argument("-o", "--option", action="append", default=[], help="core mode: core option key=value")
    p.add_argument("--system-dir", help="core mode: BIOS directory")
    p.add_argument("--frames", type=int, default=1200)
    p.add_argument("--auto", action="store_true")
    p.add_argument("--seconds", type=float, default=0)
    p.add_argument("--shot")
    p.add_argument("--mute", action="store_true")
    p.add_argument("--fullscreen", action="store_true")
    p.add_argument("--scaled", action="store_true", help="draw at 1280x720, GPU-scale to the display")
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    args = p.parse_args(argv)
    {"bench": bench, "play": play, "core": core_bench}[args.mode](args)


if __name__ == "__main__":
    main()
