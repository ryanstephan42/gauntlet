# RAM research for `games+challenges.txt`

Per-game memory addresses for the challenges in [`games+challenges.txt`](../games+challenges.txt).

**Address space.** Every address is written the way Gauntlet's memory layer reads it, so the numbers can be pasted
straight into a preset's `memory` block. For cores without a libretro memory map (snes9x), that is the
`READ_CORE_RAM` space. For all other cores, it is the core's memory map, used by `READ_CORE_MEMORY`. Most systems
match the RetroAchievements (RA) space. Where they differ, the RA address is given as well.

| System | Space | Byte order | vs. RA notes |
|---|---|---|---|
| NES | `0x0000-0x07FF` = CPU RAM | little-endian | same |
| SNES | `0x00000-0x1FFFF` = WRAM `$7E0000` | little-endian | same |
| N64 | `0x000000-0x7FFFFF` = RDRAM, logical big-endian addresses (Gauntlet applies the `swap32` layout) | big-endian | RA lists *host* addresses: logical = RA ^ 3 for 8-bit, RA ^ 2 for 16-bit, same for aligned 32-bit |
| PSX | `0x000000-0x1FFFFF` = main RAM | little-endian | same |
| GBA (mgba) | native bus addresses: `0x03000000` IWRAM, `0x02000000` EWRAM | little-endian | RA `0x00000-0x07FFF` → `0x03000000 + a`; RA `0x08000-0x47FFF` → `0x02000000 + (a - 0x8000)` |
| GameCube (dolphin) | `0x0000000-0x17FFFFF` = MEM1 (`0x80000000`); address 0 reads the game ID (`GLME01`) | big-endian | same |
| Arcade (FBNeo) | driver-specific main RAM | driver-specific | same |

GBA note: `gauntlet/systems.py` gives GBA `ram_size = 0x48000` from address 0. With mgba, that range is the BIOS rather
than RAM. The Memory Lab therefore can't scan GBA RAM until it supports a base address. Presets that use the native
addresses below work fine.

**Sources.**

- **RA** – code notes published by RetroAchievements (`dorequest.php?r=codenotes2&g=<id>`); the RA game ID is given
  for each game.
- **✅ verified** – read or written live in RetroArch (RetroDECK cores) through Gauntlet's network-command client,
  using the research harness. The value behaved as described (screenshot and value checked).
- **📝 RA only** – taken from the RA notes but not checked live. Usually this is because the ROM isn't in RoMM or the
  content is too deep into the game to reach without a save state.

Size notes: `u8` / `u16` / `u32` are unsigned; `bcd` means binary-coded decimal; `bit N` is a single flag.

---

## Arcade

None of the arcade ROMs are in RoMM (`~/retrodeck/roms/arcade` is empty), so everything here is from RA notes.
RA's arcade addresses are for FBNeo, the core Gauntlet uses for `arcade`.

### Street Fighter III: 3rd Strike – win match  (RA 11795, 📝 RA only)

| Address | Size | Meaning |
|---|---|---|
| `0x011380` | u16 | P1 rounds won in the current match ("good" note) |
| `0x068D08` | u16 | P1 HP |
| `0x0691A0` | u16 | P2 HP |
| `0x011374` | u8 | Round timer |
| `0x011384` / `0x01138B` | u8 | P1 / P2 character ID (0 = Gill …) |
| `0x0113B6` | u8 | Versus-mode flag |
| `0x015438` | u32 | Game state (1 = title) |
| `0x0156E0` / `0x0156E1` | bit 0 | P2 / P1 human-controlled |
| `0x06AC07` | u8 | Max rounds setting (0x11 = 3 rounds for each player) |
| `0x016B4B` | u8 | Perfects (arcade) |
| `0x0695BC` | u8 | P1 super gauge level |

Win detection: the P1 rounds-won counter reaches the round target (2 by default) while P2 HP = 0. RA has no P2
rounds-won note; it is probably the next counter after `0x011380`, which would need confirming with the Memory Lab.

### Galaga – beat 5 stages  (RA 12138, 📝 RA only)

| Address | Size | Meaning |
|---|---|---|
| `0x001021` | u8 | Stage number (hex) |
| `0x001020` | u8 | Lives (0 = 1 left, 0xFF = 0 left) |
| `0x000C12` | u8 | 0 = demo, 1 = in game |
| `0x001044` | u16 | Hits |
| `0x001046` | u16 | Shots fired |
| `0x0003F8-0x0003FD` | 6 × nibble | Score digits (ones → hundred-thousands, low nibble) |
| `0x001027` | u8 | Dual fighter (captured ship rescued) = 1 |
| `0x000210` | u8 | 0x0F = end of bonus (challenging) stage |

Goal: stage ≥ starting stage + 5 while the in-game flag (`0x000C12`) = 1.

### Breakout – beat a stage  (not possible as-is; substitute: Arkanoid NES, RA 1545, ✅ partly verified)

Atari's 1976 *Breakout* is built from discrete logic, with no CPU or RAM, so there is nothing to read. MAME emulates
it as a netlist, which no achievement or RAM tool can inspect. RoMM does have **Arkanoid (USA) (NES)**, ROM 507.

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x000F` | u8 | Bricks left to clear the round (0 = round cleared) | ✅ decrements per brick (attract demo) |
| `0x0010` | u8 | 1 = demo | ✅ |
| `0x0021` | u8 | Current round | 📝 |
| `0x000D` | u8 | Lives (starts at 3) | 📝 |
| `0x0370-0x0375` | 6 × u8 | Score digits (most significant first) | 📝 |
| `0x000A` | u8 | Mode (1 = main menu, 3 = story, 8/0x10 = round play) | ✅ seen |

The arcade Arkanoid (RA 11980) has `0x001603` (bricks remaining) and `0x0015F2` (round) if an arcade ROM is added later.
NES Arkanoid expects the Vaus paddle controller, which fceumm emulates on port 2 with the mouse.

---

## NES

### Mega Man – defeat "RockMan"  (RA 1448, ✅ verified, ROM 562)

*Rockman* is Mega Man's Japanese name, and the only "Mega Man" enemy in MM1 is the **Copy Robot**, the boss of Dr.
Wily stage 2, so the challenge is read as "beat the Copy Robot". It needs a save state at the Wily 2 boss door.
Any of the Robot Masters can be used the same way (stage ID 0-5).

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0031` | u8 | Stage: 0 Cut, 1 Ice, 2 Bomb, 3 Fire, 4 Elec, 5 Guts, 6 Yellow Devil (Wily 1), **7 Copy Robot (Wily 2)**, 8 CWU-01P, 9 Wily, 0xA game over, 0xB credits | ✅ (0 in Cut Man stage) |
| `0x0042` | u8 | 5 = gameplay, 6 = weapon menu | ✅ |
| `0x0054` | u8 | 0x20 = in a stage | ✅ |
| `0x006A` | u8 | Health (0x1C = max) | ✅ (28 at start) |
| `0x00A6` | u8 | Lives (0xFF = game over) | ✅ (2 → 3 shown) |
| `0x06C1` | u8 | Boss HP (0x1C full, 0 = defeated) | 📝 |
| `0x00BB` | u8 | Stage-clear flag | 📝 |
| `0x005D` | bits | Weapons owned: b1 Bomb, b2 Elec, b3 Guts, b4 Ice, b5 Cut, b6 Fire, b7 Magnet | 📝 |
| `0x0072-0x0078` | 7 × u8 | Score digits (ones → millions) | 📝 |

Win: `0x0031 == 7` and `0x06C1` reaches 0 (or `0x00BB` gets set) while `0x006A > 0`.

### Tetris (NES) – 30 line clears  (RA 2022, 📝 RA only – ROM not in RoMM)

| Address | Size | Meaning |
|---|---|---|
| `0x0050` | u16 bcd | Lines cleared (read-only copy; `0x0070` is the writable copy) |
| `0x0044` | u8 | Current level |
| `0x0053-0x0055` | 3 × bcd | Score (little-endian BCD) |
| `0x00C0` | u8 | Screen: 4 = in game, 5 = demo |
| `0x00BD` | u8 | Game state: 3 = in game, 0 = paused |
| `0x0067` | u8 | Starting level (menu) |
| `0x00C1` | u8 | 0 = A-type, 1 = B-type |
| `0x03F0-0x03FD` | 7 × u16 | Piece statistics (T, J, Z, O, S, L, I) |
| `0x0400-0x04C7` | 200 B | Playfield (10 × 20) |

Goal: lines (`0x0050`, BCD) ≥ 0x30. Lines are BCD, so 30 lines reads as 0x30, not decimal 30. Add a decode step or
compare against 0x30.

**Substitute available: Tetris & Dr. Mario (SNES), RA 1259, ROM 88.**

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0328` / `0x0329` | u8 / u8 | Lines (low / high) | ✅ zero at start (the HUD only redraws after a clear) |
| `0x0341` | u8 | Lines left until the next level | ✅ 10 at level 0 |
| `0x0342` / `0x0343` | u8 | Level (solo / any) | ✅ 0 |
| `0x1E0E` | u8 | Game select: 0 Tetris, 1 Dr. Mario, 2 Mixed | ✅ 0 |
| `0x1E1B` | u8 | Tetris mode: 0 1P, 1 2P, 2 vs CPU | ✅ 0 |
| `0x0309` / `0x0809` | u8 | P1 / P2-CPU wins in versus | 📝 |
| `0x03E7` | u8 | Dr. Mario viruses remaining | 📝 |

### Mike Tyson's Punch-Out!! – beat Bald Bull  (RA 1489, ✅ verified, ROM 571)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0001` | u8 | Opponent: 0 Glass Joe … **6 Bald Bull**, 9 Bald Bull 2 … 0xD Tyson | ✅ |
| `0x0006` | u8 | Round 1-3 (4 = decision) | ✅ |
| `0x0391` | u8 | Mac health (0x60 = full) | ✅ 96 |
| `0x0398` | u8 | Opponent health (0x60 = full) | ✅ 96, writable |
| `0x0323` / `0x0324` | u8 / u8 | Hearts tens / ones | ✅ |
| `0x0342` | u8 | Stars (0-3); a written star is spent by Start (star uppercut), lost when Mac is hit | ✅ writable |
| `0x0325` / `0x0349` | u8 | 0x80 pulse = redraw hearts HUD (HUD does not redraw for RAM writes) | 📝 |
| `0x048E` | u8 | Mac tired timer: 20 with hearts 0 → Mac turns pink and cannot punch | ✅ |
| `0x0170` / `0x0171` | u8 / u8 | Mac wins tens / ones | ✅ 0 → 1 on a TKO of Bald Bull |
| `0x0172` / `0x0173` | u8 / u8 | Mac losses tens / ones | ✅ 0 → 1 after a loss |
| `0x0174` / `0x0175` | u8 / u8 | Mac KOs tens / ones | ✅ 0 → 1 on the same TKO |
| `0x00C1` | u8 | Decision: 0xAA Mac wins, 0xAB opponent wins | 📝 |
| `0x03CA` | u8 | Opponent knock-downs this round | ✅ 0 → 3 (TKO) |
| `0x0302-0x0305` | u8 | Clock: minutes, tens of seconds, seconds | ✅ |
| `0x03E8-0x03ED` | 6 × u8 | Points | 📝 |

**Start state:** writing `0x0001 = 6` on the pre-fight "PUSH START!" screen loads the Major Circuit title bout against
Bald Bull straight away (verified). This makes it easy to build a challenge state without playing through the Minor
Circuit. Win = Mac wins counter (`0x0170*10 + 0x0171`) increases while `0x0001 == 6`.

**Timing for writes:** the game resets health (both to 96), hearts (15) and the clock when the fight is set up, and
re-fills the opponent's health once more during the ring intro. Writes made before the bell are lost. Gate them on the
clock's seconds digit: `when 0x0305 == 1` fires one second after the bell (the pre-fight state holds 8 there).
Verified: `0x0398 = 72` (Bald Bull at ¾), `0x0342 = 1` (star) and hearts `0x0323/0x0324 = 0` + `0x048E = 20`
(tired Mac) all stick when written then. Hearts = 0 on its own does **not** make Mac tired.

### Battletoads – the sewer race  (RA 1509, ✅ partly verified, ROM 511)

The sewer race is **Level 10, "Rat Race"**. Rash and Zitz race a rat down the sewer to defuse a bomb at the bottom of
each section. Lose the race three times and the level is over.

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0010` | u8 | Current level, 1-based (1 Ragnarok's Canyon … **10 Rat Race** … 13 Revolution) | ✅ 1 at start |
| `0x0011` | u8 | P1 lives | ✅ 3 |
| `0x0012` | u8 | P2 lives | 📝 |
| `0x000E` | u8 | Continues | 📝 |
| `0x051A` / `0x051B` | u8 / u8 | P1 / P2 health bars | 📝 |
| `0x051D` | u8 | Boss health (Rat Race: the rat) | 📝 |
| `0x051F` | u8 | Rat active flag | 📝 |
| `0x0058` | u8 | Rat Race section / checkpoint counter | 📝 |

**Start state:** writing `0x0010 = 0x0A` mid-level does not warp cleanly (the result was a glitched mix of level
graphics), so this challenge needs a real save state made at the start of Level 10.
Win = `0x0010` changes from 10 to 11 (Clinger Winger) without lives reaching 0.

## SNES (snes9x)

### Super Mario World – beat a level  (RA 228, ✅ verified, ROM 78)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0100` | u8 | Game mode: 0x0C loading overworld, 0x0E overworld, 0x11-0x13 loading level, **0x14 in level** | ✅ |
| `0x13BF` | u8 | Translevel ID (0x29 = Yoshi's Island 1) | ✅ |
| `0x0DBE` | u8 | Lives, minus one (4 = "×5" on the HUD) | ✅ |
| `0x0DBF` | u8 | Coins | ✅ |
| `0x0019` | u8 | Power-up: 0 small, 1 big, 2 cape, 3 fire | 📝 |
| `0x0F31-0x0F33` | 3 × u8 | Level timer digits (hundreds, tens, ones) | ✅ 2,9,5 |
| `0x1493` | u8 | End-of-level timer (0xFF once the goal tape/orb is touched, counts down) | ✅ used as the win |
| `0x0DD5` | u8 | Exit taken: 1 normal, 2 secret; 0x80 = died/exited without a goal | ✅ |
| `0x141C` | u8 | Goal tape type (0 normal, 1 secret) | 📝 |
| `0x13CE` | u8 | Midway point reached | 📝 |
| `0x1420` | u8 | Dragon coins collected this level | 📝 |
| `0x1F2E` | u8 | Number of exits found (save file progress) | 📝 |

Verified sequence for a goal: the goal tape sets `0x1493 = 0xFF`, which counts down to 1, then `0x0100` goes to 0x0C
and `0x0DD5` becomes 1. Exiting via a death (or Start+Select) leaves `0x0DD5 = 0x80` and lowers `0x0DBE`.
Win = `0x0DD5` becomes 1 or 2 while `0x13BF` is the target level. The bundled preset uses `0x1493 ≥ 1` instead: it
fires the moment the tape is touched (`0x0DD5` is only set seconds later). A start state inside Yoshi's Island 1 is
saved (level start, 4 lives; an idle Mario is killed by the first Galoomba after ~4 s, which is normal).

### Street Fighter II – win a match  (RA 1192 / Turbo RA 648, 📝 RA only – ROM not in RoMM)

RoMM has no SNES Street Fighter II, so nothing could be verified. The closest ROMs available are *Super Street Fighter II
Turbo Revival* (GBA, ROM 191) and *Street Fighter Alpha 3* (GBA, ROM 186).

**SF2: The World Warrior (RA 1192)**

| Address | Size | Meaning |
|---|---|---|
| `0x0039` | u8 | Mode: 0x80 game start (arcade), 0x90 vs battle, 0x04 fighting / demo |
| `0x0C2B` / `0x0E2B` | u8 | P1 / P2 HP (starts 0xB0, 0xFF when KO'd) |
| `0x0CCE` / `0x0ECE` | u8 | P1 / P2 CPU-controlled flag (0 human, 1 CPU) |
| `0x0CD0` / `0x0ED0` | u8 | P1 / P2 rounds won |
| `0x0CD1` / `0x0ED1` | u8 | P1 / P2 character |
| `0x0DC2-0x0DC5` | 4 × u8 | P1 score (BCD) |
| `0x00FA` | u8 | Ending type (0 none … 5 all-character credits) |

**SF2 Turbo (RA 648)**

| Address | Size | Meaning |
|---|---|---|
| `0x003A` | u8 | 0x00 Game Start, 0x10 V.S. Battle |
| `0x0530` / `0x0730` | u8 | P1 / P2 health (0xB0 → 0, 0xFF KO) |
| `0x05C0` / `0x07C0` | u8 | P1 / P2 control: 0 CPU, 1 player |
| `0x05D0` / `0x07D0` | u8 | P1 / P2 rounds won |
| `0x05D1` / `0x07D1` | u8 | Character: 0 Ryu, 1 Honda, 2 Blanka, 3 Guile, 4 Ken, 5 Chun-Li, 6 Zangief, 7 Dhalsim, 8 Bison, 9 Sagat, A Balrog, B Vega |
| `0x18A5` / `0x18A2` | u8 | P1 / P2 match wins (vs mode) |
| `0x18BD` | u8 | Battle number (arcade progression) |
| `0x1C6F` | u8 | Difficulty (0-7) |

Win (2-player): P1 rounds won (`0x05D0`) reaches 2 while both control flags are 1. Win (vs CPU): rounds won reaches 2 and
`0x18BD` advances.

### Kirby's Dream Course – beat a course  (RA 986, ✅ verified, ROM 42)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0084` | u16 | Screen: 0x0500 = results screen | 📝 (0x0230 menus, 0x0400 on course) |
| `0x00C2` | u8 | Demo playing | ✅ 0 |
| `0xD7BE` | u8 | Course ID (0 = Course 1) | ✅ |
| `0x6A5E` | u8 | Hole ID (course × 8 + hole; 1-1 = 0, 2-1 = 8, Extra 1-1 = 0x40) | ✅ 0 on 1-1 |
| `0x6A64` | u8 | Current stroke count | ✅ 0 → 1 after a shot |
| `0xD7F4` | u8 | Lives (HUD "02") | ✅ 2 |
| `0xD7F0` | u8 | Tomatoes / health | ✅ 4 |
| `0xD80A-0xD818` | 8 × u16 | Strokes per hole 1-8 (reset after the course) | 📝 |
| `0xD7E0` / `0xD7E2` | u8 | Course total (P1) / P2 score | 📝 |
| `0xDA4A` | u8 | Hole clear (1 = ball in the cup) | 📝 |
| `0xABB2` | u8 | Last hole completed | 📝 |
| `0xABB7` | u8 | 2P mode | 📝 |
| `0x1801` | u8 | Whose turn (0 P1, 1 P2) | 📝 |

A course is 8 holes. Win = `0x6A5E` is hole 8 of the course (`course × 8 + 7`) and `0xDA4A` becomes 1 (or `0x0084` goes
to 0x0500 on the results screen). A 2P head-to-head works with `0xD7E0` vs `0xD7E2`. Start state at Course 1 hole 1 is
saved. A new game needs a "member" name to be drawn first.

### Super Metroid – (no challenge given; proposals below)  (RA 236, ✅ verified, ROM 80)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0998` | u8 | Game state: 1 title, 2 options, 0x1E intro, **8 gameplay**, 0x0C-0x12 pausing, 0x15-0x1A dying, 0x20 Ceres escape, 0x26 credits | ✅ |
| `0x079B` | u16 | Room ID (0xDF45 = Ceres elevator) | ✅ |
| `0x079F` | u8 | Area: 0 Crateria, 1 Brinstar, 2 Norfair, 3 Wrecked Ship, 4 Maridia, 5 Tourian, 6 Ceres | ✅ 6 |
| `0x09C2` / `0x09C4` | u16 | Energy / max energy | ✅ 99 / 99 |
| `0x09C6` / `0x09C8` | u8 | Missiles / max | ✅ 0 |
| `0x09CA` / `0x09CC` | u8 | Super missiles / max | 📝 |
| `0x09CE` / `0x09D0` | u8 | Power bombs / max | 📝 |
| `0x09A2` / `0x09A4` | u16 | Equipped / collected items (bit flags) | ✅ 0 |
| `0x09A6` / `0x09A8` | u16 | Equipped / collected beams | 📝 |
| `0x09DA-0x09E0` | 4 × u16 | In-game time: frames, seconds, minutes, hours | ✅ |
| `0x0F8C` | u16 | Enemy 0 health (bosses) | 📝 |
| `0xD828` | u8 | Crateria boss bits (bit 2 Bomb Torizo) | 📝 |
| `0xD829` | u8 | Brinstar bosses: bit 0 Kraid, bit 1 Spore Spawn | 📝 |
| `0xD82A` | u8 | Norfair: bit 0 Ridley, bit 1 Crocomire, bit 2 Golden Torizo | 📝 |
| `0xD82B` | u8 | Wrecked Ship: bit 0 Phantoon | 📝 |
| `0xD82C` | u8 | Maridia: bit 0 Draygon, bit 1 Botwoon | 📝 |
| `0xD82D` / `0xD82E` | u8 | Mother Brain / Ceres Ridley | 📝 |

The intro text only advances on button presses. A start state at the beginning of Ceres Station is saved.

### Star Fox – (no challenge given; proposals below)  (RA 351, ✅ verified with differences, ROM 66 = Rev 2)

RA's notes were made on an earlier revision. On the RoMM **Rev 2** ROM some addresses are 2 bytes lower:

| RA address | Rev 2 address | Size | Meaning | Status |
|---|---|---|---|---|
| `0x00FD` | `0x00FD` | u8 | In game (0 title/menus, 1 map or flying) | ✅ |
| `0x0396` | `0x0396` | u8 | Shield (0x28 = 40 full) | ✅ drops when hit |
| `0x16EE` | **`0x16EC`** | u8 | Lives; the HUD shows value − 1 (3 = "×2") | ✅ |
| `0x15AF` | **`0x15AD`** | u8 | Nova bombs (max 5) | ✅ |
| `0x1FF9` | **`0x1FF7`** | u16 | Stage ID; Corneria on Level 1 reads 0x4F8E (RA lists 0x5068) | ✅ differs |
| `0x16DA` | `0x16DA` | u8 | Path (in game: 0 Level 1, 1 Level 2, 2 Level 3) | ✅ 0 |
| `0x16D8` | `0x16D8` | u8 | Stage number within the path (0 = first) | ✅ 0 |
| `0x15BA` | ? | u8 | Level complete ("All aircraft report") | 📝 |
| `0x1FBF-0x1FC5` | ? | u8 | Hit percentage per stage | 📝 |
| `0x189A` | ? | u8 | Continues | 📝 |

Because of the shift, presets should use the Rev 2 addresses verified above. Re-check the 📝 entries on Rev 2 before
using them. A start state at the beginning of Corneria (Level 1) is saved.

---

## PSX (swanstation)

The RoMM PSX images are CHDs, and swanstation loads them directly. The core's memory map exposes main RAM at
`0x000000`; reads were cross-checked against the executable header at `0x10000`.

Memory-card prompts get in the way in Spyro (the "create save file?" dialog loops when a Libretro card can't be
written). For research and for start states, launch with `swanstation_MemoryCards_Card1Type = "None"`. Each game then
offers a "continue without saving" path. Gauntlet start states skip these menus anyway.

### Crash Bandicoot – beat a level  (RA 10434, ✅ verified, ROM 622)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x61994` | u8 | Overworld status: **0 in a stage**, **1 on the map**, 5/6 moving to the previous/next island | ✅ 1 → 0 on entering N. Sanity Beach |
| `0x619C5` | u8 | Selected / current stage: 0 N. Sanity Beach, 1 Jungle Rollers, 2 The Great Gate, 3 Boulders, 4 Upstream, 5 Papu Papu, 6 Rolling Stones, 7 Hog Wild, 8 Native Fortress, 9 Up the Creek, 0xA Ripper Roo, … | ✅ 0 |
| `0x61985` | u8 | Boxes broken in the current stage | ✅ 0 → 2 |
| `0x618ED` | u8 | Lives (map) | ✅ 4 |
| `0x91A94` | u8 | Lives inside N. Sanity Beach. This is a heap object, so the address changes per stage | ✅ 4 → 5 on a 1-up |
| `0x61998` | u8 | RA: "on results screen". Read 1 while playing, so it is unreliable | ⚠️ |
| `0x61988-0x6198B` | bits | Gems collected, one bit per stage (see the RA note) | 📝 |
| `0x619AD-0x619AE` | bits | Keys and coloured gems | 📝 |
| `0x6197C` | u8 | Current bonus stage (Tawna / Brio / Cortex) | 📝 |

Crash 1 has no "quit level" option. Leaving a stage only happens by finishing it or by a game over. **Win = `0x61994`
goes 0 → 1 while `0x619C5` is the target stage.** Lives and boss HP are heap objects that move per stage. Read them
through a pointer, or skip them. Start states on the map (stage 0 selected) and inside N. Sanity Beach are saved.

### Final Fantasy VII – beat Sephiroth  (RA 11242, ✅ battle flow verified, ROMs 644 / 645 / 646)

The final battles are on **Disc 3** (ROM 646). Only Disc 1 was downloaded for research, so the challenge itself still
needs a late-game save state taken just before the Northern Crater fight.

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x062FF9` | u8 | In battle (0/1) | ✅ 0 → 1 at the first MP fight, back to 0 after victory |
| `0x062F54` | u16 | Enemy formation ID ("sticky", keeps the last battle). Guard Scorpion 0x144, Air Buster 0x16C, Jenova∙BIRTH 0x1E8, … | ✅ 0x12C = opening 2 × MP fight |
| `0x0F83C6` | u8 | Battle ended by: **0x20 win**, 0x22 loss, 0x04 escape. Set for about 3 seconds on the victory screen | ✅ 0x20 |
| `0x0F85AC` / `0x0F85B0` | u32 | Enemy 1 current / max HP | ✅ 30 / 30 → 0 |
| `0x0F8614`, `0x0F867C`, `0x0F86E4` | u32 | Enemy 2-4 current HP | ✅ (enemy 2) |
| `0x09C764` | u16 | Cloud current HP | ✅ |
| `0x09D288` | u16 | General game progress ("Game Moment"): 1 = first gameplay, 0x14F left Midgar, 0x29F Aerith, 0x3E7 post-Crater, … | ✅ 0 → 1 |
| `0x09A05C` | u16 | Room / field ID | ✅ 116 (Sector 1 station) |
| `0x09ABF6` | u16 | FMV ID (0x10 Sephiroth emerges, …) | ✅ 0x35 opening |
| `0x09A14E` | u16 | Music ID (0x2F win fanfare, 0x3B game over) | 📝 |
| `0x09D260` / `0x09D264` | u32 | Gil / play time | ✅ |
| `0x09CBDC-0x09CBDE` | 3 × u8 | Party member IDs | 📝 |
| `0x16379A` | u16 | Last action performed (0x1406 Omnislash, 0x030F KotR, 0x143D Game Over) | 📝 |

Win = `0x0F83C6` becomes 0x20 while `0x062F54` equals the Safer∙Sephiroth formation ID. That ID isn't in the RA notes,
so capture it from the late save state (read `0x062F54` once the battle starts). Confirm a pass with
`0x09D288` (game progress) moving past its pre-battle value. The final one-on-one with Sephiroth can't be lost, so use
the Safer∙Sephiroth fight.

### Metal Gear Solid – beat Grey Fox (Ninja)  (RA 11244, ✅ basics verified, ROMs 672 / 673)

The RoMM image is **v1.0**: the map name is at the v1.0 address, and Snake's HP reads at the v1.0 offsets. RA notes
often give two addresses (v1.0 / v1.1); use the v1.0 column. The Ninja fight is in Otacon's lab, late on Disc 1, so it
needs a save state taken just before entering the lab.

| Address (v1.0) | Size | Meaning | Status |
|---|---|---|---|
| `0x117084` | u16 | Game mode: 0 campaign, 0x4D47 main menu, 0x9265 results, 0xA8A1 VR mission, 0xB8B9 credits | ✅ 0x4D47 → 0 |
| `0x0B7500` | 8 × ASCII | Map name ("title", "d00a", **"s00a"** = Dock, …) | ✅ |
| `0x0B7512` | u8 | Difficulty (0 Easy, 1 Normal, 2 Hard, 3 Extreme) | ✅ 1 |
| `0x0B7526` / `0x0B7528` | u16 | Snake current / max HP | ✅ 256 / 256 |
| `0x0B75AC` | u16 | Alerts | ✅ 0 |
| `0x0B75AE` | u16 | Kills | ✅ 0 |
| `0x0B75BE` | u16 | Continues | ✅ 0 |
| `0x0B75BC` | u16 | Rations used | 📝 |
| `0x0B75C8` | u32 | Play time in seconds | ✅ |
| `0x0AE178` | u8 | Radar: 0 normal, 1 jamming, 2 evasion, **3 alert** | ✅ 0 |
| `0x0ADB3F` | u8 | HUD: 0 gameplay, 0x10 HUD but frozen, 0x80 cutscene | ✅ 0 |
| `0x0B8CCE` | u16 | Ninja (Grey Fox) health. RA: "freezing this makes ninja invincible" | 📝 |
| `0x0B8EF6` | u16 | Metal Gear REX health | 📝 |
| `0x0B64F6` | bits | Bit 0 rescued by Ninja, bit 1 escaped the cell | 📝 |

Win = map name is the lab and `0x0B8CCE` reaches 0, or the HUD flag goes to 0x80 (cutscene) after the fight, with
Snake's HP > 0 and continues unchanged. Kills, alerts and continues also make good stealth challenges (see the txt
file). A start state on the Dock (Normal, no memory card) is saved.

### Tekken 3 – win a match  (RA 11259, ✅ verified, ROM 712)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0AE224` | u8 | Screen: 1 title, 2 character select, 3 VS screen, **8 fight** | ✅ |
| `0x0AE204` | u8 | Mode screen: 8 fighting, 9 character select, 16/17 continue screen | ✅ |
| `0x097F40` | u8 | Mode: 0 Arcade, 1 VS | ✅ 0 |
| `0x098106` / `0x098107` | u8 | P1 / P2 character (8 Eddy, 6 Hwoarang, …) | ✅ |
| `0x0A961E` / `0x0AAEAA` | u16 | P1 / P2 health (130 full) | ✅ |
| `0x0A926C` / `0x0AAAF8` | u8 | P1 / P2 rounds won. The P2 struct is P1 + 0x188C | ✅ 0 → 1 |
| `0x0A926E` / `0x0AAAFA` | u8 | Round result: 1 = this player won the round, 0xFF = lost | ✅ |
| `0x095484` | u8 | Current round number | ✅ |
| `0x0A04C2` | u8 | Rounds needed to win the match (2 by default) | ✅ |

Win = P1 rounds won (`0x0A926C`) reaches `0x0A04C2` while `0x0AE224 == 8`. In VS mode (`0x097F40 == 1`) the same check
on `0x0AAAF8` gives the P2 winner, so one preset handles both players.

### Spyro the Dragon – beat a level  (RA 11279, ✅ verified, ROM 706)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x0757D8` | u32 | Game state: **0 in game**, 1 entering level, 2 pause, 4 respawning, 5 game over, 7 flight level end, 8 dragon-rescue replay, 0xA exit level, 0xD title, 0xE cutscene | ✅ 13 → 0, 8 on rescue |
| `0x0758B4` | u32 | Level ID: 0x0A Artisans, 0x0B Stone Hill, 0x0C Dark Hollow, 0x0D Town Square, 0x0E Toasty, 0x0F Sunny Flight, 0x14 Peace Keepers, … | ✅ 0x0A |
| `0x07596C` | u32 | Level ID (second copy) | ✅ 0x0A |
| `0x07582C` | u32 | Lives | ✅ 4 |
| `0x075860` | u32 | Total gems | ✅ 0 |
| `0x075750` | u32 | Total dragons rescued | ✅ 0 → 1 |
| `0x0772D8 + 4 × n` | u32 | Dragons rescued per level (Artisans 0x772D8, Stone Hill 0x772DC, Dark Hollow 0x772E0, Town Square 0x772E4, **Toasty 0x772E8**, …) | ✅ Artisans 0 → 1 |
| `0x077420 + 4 × n` | u32 | Gems collected per level, same order (plus the flight levels) | 📝 |
| `0x075810` | u32 | Dragon eggs | 📝 |
| `0x0756C8` | u32 | Gems in the current level | 📝 |
| `0x07572C` | u32 | Level timer | ✅ counts up |

Spyro levels have no exit goal, so "beat a level" means one of two things. For a boss level, rescue the dragon after the
boss (e.g. Toasty: `0x772E8` goes 0 → 1). For a normal level, rescue every dragon (e.g. Stone Hill: `0x772DC` reaches
its dragon count). A start state at the start of Artisans is saved. Walking up the path rescues the first dragon in
about 3 seconds, which makes a handy quick test.

---

## N64 (mupen64plus_next)

Addresses are **logical** (big-endian, as a preset writes them; Gauntlet applies `swap32`). Where the RA note address
differs, it is shown in the "RA" column. Controller notes for the research pad: RetroPad A = N64 A, RetroPad X = N64 B,
right stick = C buttons.

### Pokémon Stadium 2 – beat the other player  (RA 10258, ✅ verified, ROM 367)

| Address | RA | Size | Meaning | Status |
|---|---|---|---|---|
| `0x09DE97` | `0x09DE94` | u8 | Game mode: 3 main hub, 8 Transfer Pak check, **0x10 Free Battle** | ✅ |
| `0x11F301` | `0x11F302` | u8 | Battle state: 0x22 team preview ("All ready"), **0x0E fighting** (Free Battle; RA says 0x18 in other modes), **0x2A battle over** | ✅ |
| `0x14528E` / `0x1452E6` / `0x14533E` | `0x14528C` / … | u16 | P1 team HP, mons 1-3 (stride 0x58) | ✅ |
| `0x14576E` / `0x1457C6` / `0x14581E` | `0x14576C` / … | u16 | P2 / COM team HP, mons 1-3 | ✅ poked 1,1,1 → KO'd → state 0x2A |
| `0x0D1C34`, `0x145BB0` | – | u16 | Active-mon HP mirrors (display) | ✅ |

**Win = battle state becomes 0x2A while every P2 HP is 0 and some P1 HP is > 0** (and the reverse for P2). A Free Battle
start state is saved: 1P Alakazam/Articuno/Bellsprout vs COM Easy Abra/Aipom/Alakazam.

### Banjo-Kazooie – first to get a Jiggy  (RA 10210, ✅ verified with offset, ROM 305)

The RoMM ROM is USA v1.0. The RA notes target another revision. For this ROM, the **item block is RA − 0xDE0** and
**game state / map are RA − 0xE00**.

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x37DAE4` | u32 | Game state: 3 in game, 4 paused | ✅ pause toggle |
| `0x37DAF5` | u8 | Map: 1 Spiral Mountain, … | ✅ |
| `0x3851A0` / `0x3851A4` | u32 | Health / max health (honeycombs) | ✅ 5 / 5 |
| `0x3851A8` | u32 | Lives | ✅ 3 |
| `0x3851E8` | u32 | **Total Jiggies** | ✅ poked 7 → pause screen shows 7 |
| `0x385188` | u32 | Jiggies in the current world | 📝 offset-derived |
| `0x385180` | u32 | Notes in the current world | 📝 offset-derived |

**Win = total Jiggies (`0x3851E8`) goes above its start value.** For a race, both players start from the same state.
A new-game state outside Banjo's house is saved; the first Jiggy (Spiral Mountain) is about a minute away.

### Donkey Kong 64 – first to get a banana  (RA 10075, ✅ verified, ROM 325)

| Address | RA | Size | Meaning | Status |
|---|---|---|---|---|
| `0x755314` | `0x755317` | u8 | Game state: 2 DK Rap, 3 title, 5 main menu, **6 in game** | ✅ |
| `0x76A0A8` | same | u32 | Map: 0x4C DK Rap, 0x50 main menu, 0xAB DK's House (first control), 0x22 DK Isles, 0x07 Jungle Japes | ✅ |
| `0x76A0B1` | `0x76A0B2` | u8 | Map state: 8 in control, 24/25 cutscene | ✅ |
| `0x7FC990 + 2 × level` | raw = logical ^ 2 | u16 | DK Golden Bananas per level, in level order: Japes 0x7FC990, Aztec 0x7FC992, Factory 0x7FC994, Galleon 0x7FC996, Fungi 0x7FC998, Caves 0x7FC99A, Castle 0x7FC99C, Helm 0x7FC99E, **Isles 0x7FC9A0** | ✅ Isles poked to 5 → pause shows 5; other levels 📝 by array order |
| `0x7FC956` | `0x7FC954` | u16 | DK yellow (coloured) bananas | ✅ |
| `0x744526` / `0x744524` / `0x74452A` / `0x744528` | – (RA raw) | u8 | Kong Battle wins P1 / P2 / P3 / P4 | 📝 |
| `0x0101F0` | same | u32 | Loading / pause flag | 📝 |

Each Kong has its own Golden Banana block (RA notes list them after DK's). **Win = the sum of the GB counters rises
above its start sum.** For the Japes-first race, Japes alone is enough. A state at first control in DK's House (0 GB) is
saved.

### Diddy Kong Racing – win a race  (RA 10202, ✅ verified by structure analysis, ROM 324 = USA Rev 1)

The RA notes are for another revision; their pointers read 0 on this ROM. These addresses were found from the racer
objects:

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x1F05C0` | 8 × ptr | Racer object pointers (`0x80xxxxxx`), entry 0 = Player 1; objects are 0x790 apart | ✅ |
| `0x1F05F0` | 8 × ptr | The same pointers sorted by current position (index 0 = leader) | ✅ |
| `[ptr]+0x247` | u8 | Current place, 1-based | ✅ HUD "8TH" = 8 |
| `[ptr]+0x22B` | u8 | Laps completed (0-based) | ✅ writing 2 shows "3/3" |
| `[ptr]+0x270` | u8 | Race finished: 0 → 1 after the final line | 📝 seen on AIs |
| `[ptr]+0x245` | u8 | Final finishing position (0 while racing) | 📝 seen on AIs |

**Win = P1's `[ptr0]+0x270` becomes 1 with `[ptr0]+0x245 == 1`.** Or, simpler: `*(0x1F05F0) == *(0x1F05C0)` when
the finish flag sets. Presets need pointer support (`ptr & 0x7FFFFF` + offset); see the "Pointers" note at the end.
A start state (Tracks mode, Ancient Lake, car, Diddy, race just started) is saved. For reference, the RA (other
revision) game mode is `0x0DF470` (0x0F on track).

### GoldenEye 007 – first to 5 kills (multiplayer)  (RA 10073, ✅ verified, ROM 338)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x02A8C0` | u32 | Screen: **11 = multiplayer match** | ✅ |
| `0x079EF0 + 0x70 × n` | struct | Player n stats (P1 0x079EF0, P2 0x079F60, P3 0x079FD0, P4 0x07A040) | ✅ |
| `+0x1C` | u32 | Kill count (total). **Not** the displayed score | ✅ |
| `+0x24 + 4 × victim` | u32 | Kills of victim 0-3. The pause-screen score is derived from this array | ✅ P2 kills[P1] = 4 → score 4, rank 1st |
| `+0x24 + 4 × self` | u32 | Suicides (subtracted from the score) | 📝 |

**Score = Σ kills[other] − kills[self]. Win = score reaches 5.** A poked score doesn't end the match, because the
game only checks the kill limit on a kill event. Gauntlet should referee from the array rather than wait for the game's
results screen. A start state (Temple, 2P, First to 5, Rockets) is saved.

### Mario Party 3 – win a minigame  (RA 10108, ✅ verified, ROM 351)

| Address | RA | Size | Meaning | Status |
|---|---|---|---|---|
| `0x0CE203` | `0x0CE200` | u8 | Game state: 0x48 board, 0x47 pre-minigame, 0x70 minigame explanation, **minigame ID while playing** (Etch 'n' Catch 18, Dorrie Dip 62), **0x71 coins awarded** | ✅ |
| `0x0CD068` | `0x0CD06B` | u8 | Current minigame ID | ✅ |
| `0x0D110E + 0x38 × slot` | `0x0D110C` | u16 | Minigame reward pending: set to 10 on the winners when a minigame ends, cleared after the award. Slot order = character-select order (slot 0 = P1) | ✅ |
| `0x0D1112 + 0x38 × slot` | `0x0D1110` | u16 | Coins | ✅ 13 → 23 |
| `0x0D1110 + 0x38 × slot` | `0x0D1112` | u16 | RA "minigame result". Didn't change in Etch 'n' Catch | ⚠️ |
| `0x0D1116 + 0x38 × slot` | `0x0D1115` | u8 | Stars | 📝 |

**Win = while game state is a minigame ID, P1's reward-pending value goes 0 → > 0** (or P1's coins rise while game
state is 0x71). Item minigames (e.g. Dorrie Dip) have no winner. A start state on the Etch 'n' Catch (2 v 2)
explanation screen is saved; press Start to begin. Teams in that state: slots 0+3 (red, Mario + Daisy) vs 1+2 (blue);
with no input the red team won and slots 0 and 3 both went 0 → 10.

### Mario Kart 64 – win a race  (RA 10078, ✅ verified, ROM 350)

| Address | RA | Size | Meaning | Status |
|---|---|---|---|---|
| `0x0DC524` | same | u32 | Game state: 4 racing | ✅ |
| `0x0DC513` | `0x0DC510` | u8 | Race status: 2 countdown, 3 running, **5 finished** (set when P1 crosses the final line) | ✅ |
| `0x0F6994` | `0x0F6996` | u16 | P1 placement, 0-based (0 = 1st) | ✅ 7 → 0 |
| `0x0F6998` | `0x0F699A` | u16 | P1 laps: 0xFFFF before the line, 0 → 3 | ✅ |
| `0x164390` | same | u32 | P1 laps (mirror) | ✅ |
| `0x0F776C` / `0x0F7770` | `0x0F776E` / `0x0F7772` | u16 | P2 placement / laps (racer stride 0xDD8) | 📝 |
| `0x0DC53C` / `0x0DC538` | same | u32 | Game type (0 = GP) / player count | 📝 |

Tested by poking both lap counters to 2 and crossing the line: laps went to 3, status to 5, and the game showed "1st"
and results. **Win = race status becomes 5 with P1 placement 0.** A start state (GP 50cc, Mario, Luigi Raceway, before
the start line) is saved.

### Super Smash Bros. – win a match  (RA 10082, ✅ verified, ROM 386)

| Address | RA | Size | Meaning | Status |
|---|---|---|---|---|
| `0x0A4AD0` | `0x0A4AD3` | u8 | Screen: 7 mode select, 9 VS menu, 16 character select, 21 stage select, **22 in match**, **24 VS results** | ✅ |
| `0x0A4D08` | – | struct | VS settings (+0x03 rule: 1 = time; +0x06 time limit in minutes) | ✅ partly |
| `0x0A4D1C` | – | u32 | Time remaining in frames (counts down; the match ends at 0) | ✅ poked 180 → results |
| `0x0A4D20` | – | u32 | Elapsed frames | ✅ |
| `0x0A4D28 + 0x74 × n` | – | struct | Player n (0-3) | ✅ |
| `+0x00` | – | u8 | CPU level | 📝 |
| `+0x02` | – | u8 | Kind: 0 human, 1 CPU, 2 none | ✅ |
| `+0x03` | – | u8 | Character | 📝 |
| `+0x10` | – | u32 | Falls ("TKO" on results) | ✅ |
| `+0x14` | – | u32 | Total KOs | ✅ |
| `+0x18 + 4 × victim` | – | u32 | KOs on each opponent | ✅ |

The struct matched the results screen exactly: KOs 0/8, TKO 9/0, Pts −9/8, "Pikachu wins". **Win (time) = screen 24
and P1's KOs − falls beats every other player.** Win (stock) = screen 24 and only P1 has stocks left; RA lists the stocks
at raw `0x1317CC`, 📝. A start state (time match, Mario vs CPU Pikachu) is saved.

---

## GameCube (dolphin_libretro)

**Gauntlet has no GameCube system yet.** RetroDECK ships `dolphin_libretro`, and its memory map works with the
network commands: address 0 reads the game ID (`GLME01` for Luigi's Mansion), and RA addresses map 1:1 (MEM1, big-endian).
Adding a `gc` entry to `gauntlet/systems.py` would be enough for presets: extensions `.rvz/.iso/.gcm/.ciso`, core
`dolphin`, linear layout, big-endian, `ram_size = 0x1800000`.

⚠️ **Stability.** In RetroDECK, `dolphin_libretro` repeatedly deadlocked during research: the main loop stopped
servicing the UDP command port, and the socket receive queue filled up. This happened with glcore and Vulkan, with or
without memory reads, usually during loads or menus. The hung process ignores SIGTERM and needs `kill -9`. Test this
before relying on GC challenges.

All five ROMs are in RoMM (IDs below). Only Luigi's Mansion was checked live. The others are from RA notes and need a
save or start state deep enough to test the challenge.

### Luigi's Mansion – catch a Boo  (RA 4325, ✅ partly verified, ROM 739)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x3A3AE4` | u32 | Game state: 0 logo, 1 menu, **2 playing**, 3 file select, 4 entrance cutscene, 5 credits, 6 final score | ✅ 1 → 4 → 2 |
| `0x4D80A4` | u32 | Map: 1 E. Gadd's lab, 2 mansion | ✅ 2 |
| `0x3D5E04-0x3D5E0A` | bits | **Boo caught flags**, one bit per Boo | ✅ set bit 0 → HUD Boo count 0 → 1 |
| `*(0x4D8618) + 0x09` | u8 | Boo count shown on the HUD / Game Boy Horror | ✅ follows the flags |
| `*(0x3A3CC4) + 0x77` | u8 | Boo data (RA) | 📝 |

**Win = popcount of `0x3D5E04-0x3D5E0A` rises.** Boos only appear after the Boo Radar (after Chauncey, Area 2), so
this challenge needs a save state from that point. A start state at the mansion foyer is saved.

### Mario Kart: Double Dash!! – win a race  (RA 7693, 📝 RA only, ROM 740)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x3B0724` | u32 | Game state: 3 = in game | 📝 |
| `0x3B1464` | u32 | Mode: 1 Time Trial, 2 Grand Prix, 3 VS | 📝 |
| `0x3CB6B2` | u8 | **Race finished** flag | 📝 |
| `0x37FF60 + 4 × p` | u32 | Lap, player p | 📝 |
| `0x37FFA0 + 4 × p` | u32 | **Place**, player p | 📝 |
| `0x3B0FC8` | u32 | GP track | 📝 |
| `0x3B124C` / `0x3B1250` | u32 | Driver / partner character | 📝 |

**Win = finished flag set with P1 place == 1** (check whether place is 0- or 1-based before use).

### F-Zero GX – win a race  (RA 9699, 📝 RA only, ROM 733)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x378591` | u8 | Race status 1: bit 0 **finished**, bit 4 racing, bit 6 cup won | 📝 |
| `0x378592` | u8 | Race status 2: bit 5 retired | 📝 |
| `0x378596` | u8 | Course | 📝 |
| `0x378636` / `0x378637` | u8 | Cup / course number in the cup | 📝 |
| `0x378668` | u16 | Ranking points from this race | 📝 |
| `0x37866C` | u16 | Total ranking points | 📝 |
| `0x3F857F-0x3F8582` | bits | GP clear flags per cup / difficulty | 📝 |

RA has no plain "placement" address. In GP, first place always earns the most points for the race (record the
1st-place value once from a live race). So **win = finished bit set and race points == the 1st-place value** (or read
the place from the racer struct once found). Retired (status 2 bit 5) is a loss.

### Pikmin – most Pikmin at the end of the day  (RA 15540, 📝 RA only, ROM 750; a Rev 1 `.ciso` is also local)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x39D9AF` | u8 | Game state: 7 = in a location | 📝 |
| `0x39D987` | u8 | Area | 📝 |
| `0x39DAA4` | f32/u32 | Day phase timer | 📝 |
| `0x39DAB0` | u32 | Day phase (sunset = end of day) | 📝 |
| `0x39DAB4` | u32 | Day number | 📝 |
| `0x3D1DF0` (+4, +8) | u32 | Pikmin in the Onion: blue (red, yellow) | 📝 |
| `0x3D1E70-0x3D1E78` | u32 ×3 | In the party: blue, red, yellow | 📝 |
| `0x3D1EC4-0x3D1ECC` | u32 ×3 | In the field | 📝 |
| `0x3D1E58-0x3D1E60` | u32 ×3 | Lost today | 📝 |
| `0x39D870` | u32 | Total Pikmin sprouted | 📝 |
| `0x1249DE7` | u8 | Ship parts | 📝 |

Addresses are for USA Rev 1. **Score = Onion + field Pikmin when the day number increments** (or at the "day phase =
end" transition). Higher score wins. Alternative: "fewest lost today" from `0x3D1E58`.

### SoulCalibur II – win a match  (RA 3536, 📝 RA only, ROM 755)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x34D519` / `0x36E5B9` | u8 | P1 / P2 character | 📝 |
| `0x34EA0D` / `0x36FAAD` | u8 | **P1 / P2 rounds won** | 📝 |
| `0x3F4705` / `0x3F4715` | u8 | Main menu choice / sub-choice (0 Arcade, 1 VS, …) | 📝 |
| `0x3AFC93` | u8 | Arcade stage number | 📝 |
| `0x28752B` | u8 | Difficulty | 📝 |
| `0x28768B` | u8 | Round time | 📝 |

**Win = P1 rounds won reaches the rounds-to-win setting (default 2) before P2's does.** Arcade progress (`0x3AFC93`)
supports "clear N arcade stages".

---

## GBA (mgba)

Addresses are **native** (`0x03xxxxxx` IWRAM, `0x02xxxxxx` EWRAM); see the table at the top for the RA conversion.
Research pad note: in this setup RetroPad B = GBA A and RetroPad A = GBA B (check `KEYINPUT` at `0x04000130`).

### Metroid Fusion – (no challenge given; proposals below)  (RA 785, ✅ verified, ROM 166)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x03000BDE` | u8 | Game mode: 0 title / file select, **1 in game**, 3 loading into game, 7 story intro, 8 game over, 9 ending, 0x0C demo | ✅ 0, 1, 3, 7, 0x0C seen |
| `0x0300002C` / `0x0300002D` | u8 | Area / room | ✅ 0 / 0 at the start |
| `0x03000138-0x0300013B` | u8 ×4 | In-game time: hours, minutes, seconds, frames | ✅ counts |
| `0x03001310` / `0x03001312` | u16 | **Energy** / max energy | ✅ 99; poked 42 → HUD 42 |
| `0x03001314` / `0x03001316` | u16 | Missiles / max missiles | 📝 reads 10 / 10 before missiles are unlocked |
| `0x0300131B` | bits | Missile / bomb equipment flags | 📝 0 at the start |
| `0x0300003B-0x03000041` | u8 | Sector exploration percentages | 📝 |
| `0x030001D4` | u8 | Boss event status (B.O.X. and others): 0x40 pre-fight, 0x42 fight, **0x44 just defeated** | 📝 |
| `0x03000314` | u16 | B.O.X. HP (0x12C full, 0 dead) | 📝 |
| `0x03000244` | u8 | Core-X event: 0x18 start, 0x1C during, **0x5D dead** | 📝 |
| `0x03000430` | u8 | Serris event | 📝 |

A start state at first control (docking bay, 99 energy) is saved. Good challenge targets: a race to the first
Navigation Room or the first boss (Arachnus, about 5 minutes in), "take no damage" from energy (`0x03001310` never
drops), or speedruns timed with the IGT.

### Pokémon Emerald – beat the Champion  (RA 668, ✅ verified mechanics, ROM 830; the RoMM `.sav` is at 0:07)

Pokémon Gen 3 keeps its save blocks in EWRAM behind **pointers that move** (anti-cheat DMA). Always read the pointer.
Party Pokémon data is encrypted, except the battle stats at +0x50 and beyond.

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x03005D8C` | ptr | **SaveBlock1** pointer (`0x02025A08` in the test) | ✅ |
| `0x03005D90` | ptr | SaveBlock2 pointer (name, IDs, play time at +0x0E) | ✅ |
| `SB1 + 0x04` / `+0x05` | u8 | Map group / map number (0 / 0x12 = Route 103) | ✅ |
| `SB1 + 0x1270` | bits | Event flags: flag `f` = byte `0x1270 + f/8`, bit `f%8` | ✅ |
| `SB1 + 0x137C` | bits | bit 0 SYS_POKEMON_GET, **bit 4 SYS_GAME_CLEAR** (Hall of Fame), bit 7 badge 1 | ✅ bit 0 set; bit 7 → Stone Badge on the trainer card |
| `SB1 + 0x137D` | bits | Badges 2-8 = bits 0-6, bit 7 VISITED_LITTLEROOT | ✅ |
| `SB1 + 0x1339` | bit 7 | TRAINER_WALLACE (Champion) defeated | 📝 (trainer flag 0x500 + 335) |
| `0x020244E9` | u8 | Party count | ✅ 1 |
| `0x020244EC + 100 × i` | struct | Party Pokémon i: +0x54 level, +0x56 HP, +0x58 max HP | ✅ Lv 6, 17/23 |
| `0x02022FEC` | u32 | Battle type flags: bit 3 trainer, bit 0 double; wild = 0x04 | ✅ |
| `0x0202433A` | u8 | **Battle outcome**: 1 won, 2 lost, 4 fled, 6 wild fled, 7 caught | ✅ fled → 4 |
| `0x02038BCA` | u16 | Opponent trainer ID (**Wallace = 335 = 0x14F**) | ✅ reads 0 in a wild battle |

**Win = outcome becomes 1 while the opponent ID is 0x14F** (or SYS_GAME_CLEAR goes 0 → 1). This needs a save state at
the Champion's room. A start state on Route 103 (copied save, not the user's file) is saved.

### Pokémon FireRed – catch a Pokémon in the Safari Zone  (RA 515, ✅ partly verified, ROM 831)

| Address | Size | Meaning | Status |
|---|---|---|---|
| `0x03005008` | ptr | **SaveBlock1** pointer (moved from `0x0202556C` to `0x02025550` during the test) | ✅ |
| `0x0300500C` | ptr | SaveBlock2 pointer | 📝 |
| `SB1 + 0x04` / `+0x05` | u8 | Map group / number (4 / 1 = player's room) | ✅ |
| `SB1 + 0x0EE0` | bits | Event flags (same scheme as Emerald) | 📝 |
| `0x02024029` | u8 | Party count | ✅ 0 at the start |
| `0x02022B4C` | u32 | Battle type flags: **bit 7 (0x80) = Safari battle** | 📝 pokefirered |
| `0x02023E8A` | u8 | **Battle outcome**: 1 won, 2 lost, 4 ran, 7 caught | 📝 RA + pokefirered |
| `0x02039994` | u8 | **Safari Balls left** | 📝 |
| `0x02039996` | u16 | Safari steps left | 📝 |

**Win = outcome becomes 7 while the battle type has bit 7 set** (or Safari Balls drop and the party / PC count
rises). This needs a save state at the Safari Zone gate (Fuchsia City, about 6 badges in). A start state in the
bedroom (new game) is saved.

---

## Pointers (needed by several challenges)

Diddy Kong Racing (racer objects), Luigi's Mansion (HUD Boo count) and Pokémon Gen 3 (save blocks) all keep the
interesting values behind pointers that change between loads. Gauntlet's schema can't express pointers yet. A
`"pointer": {"address": ..., "size": 4, "mask": ...}` field on a memory spec (read pointer → mask → add `address`)
would cover all three. Until then, presets can use the fixed alternatives listed above: Boo flags, battle outcome
and trainer ID, DKR's sorted racer table compared with P1's pointer. The bundled DKR preset instead reads P1's racer
object at its fixed address in the bundled start state (`0x1E6E50`), which is stable because every match loads the
same state.
