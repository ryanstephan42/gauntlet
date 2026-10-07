# RAM research: all 52 new-game ideas

Audit date: 2026-10-06. Entries follow [the ideas list](new-game-ideas.md) in its
original order, including titles marked "existing". An existing game/preset is not
proof that its four proposed challenges have been researched or tested.

## Evidence and scope

**Source-backed** below means the complete public RetroAchievements (RA)
`codenotes2` JSON was retrieved, not merely an AI search summary or a game-page
snippet. The source link at each entry identifies its exact set. Notes are
community reverse engineering, not guarantees about every revision. Where a note
itself says "possible", "?", or supplies no width/value, that uncertainty is retained.
The preliminary community maps in [ram-research.md](ram-research.md) provide
additional leads; the primary-source corrections here take precedence.

**Live read** means actual emulated RAM, not `fakera`, invented sample values or
reading a ROM file. **Gameplay sample** means the corresponding screen was also
checked. **Challenge verified** would require observing its natural success AND
failure transitions from the intended state; none of the new boss challenges
qualifies merely because its address was readable at boot.

Local resources were rediscovered with Gauntlet's `find_installs`: **RetroDECK
RetroArch 1.22.2 was already installed**. No installation was necessary. The
initial shell-only check missed RetroDECK and is superseded. With the user's
authorization, owned ROMs were retrieved from RoMM using the existing scoped token,
kept outside the checkout and checked against RoMM file sizes and SHA-1 hashes.
No token, ROM, BIOS, save or screenshot containing game assets is committed.

Local testing used:

- The existing `prototypes/inwindow/libretro.py` frontend, actual FCEUmm/Snes9x
  system-RAM pointers, and software-only ParaLLEl N64. This gives deterministic
  input/frame stepping without altering the user's emulator configuration.
- Isolated RetroArch launches with a private config, private save directories,
  per-ROM UDP ports and `GET_STATUS` content checks. They exercised Gauntlet's
  real `RetroArchClient`, including the SNES `READ_CORE_RAM` fallback.
- Screenshots and frame-numbered RAM samples kept in the session artifacts.
  Boot/menu zeros are explicitly not proof of boss HP, equipment or victory.

The first UDP cross-check batch reused a port and received the preceding game's
status. **That entire batch is invalid evidence**. It was replaced by unique-port,
content-checked probes; only those appear in the results below.

## Address contract and detection rules

| System/core | Source addresses | Gauntlet conversion / limitation |
|---|---|---|
| NES / FCEUmm | CPU RAM offsets, plus cartridge RAM for some games | `0x0000..0x07FF` system RAM; SMB3's `0x6000..0x7FFF` cartridge RAM requires mapped reads, not indexing the 2 KiB system-RAM pointer |
| SNES / Snes9x | WRAM offsets, sometimes additional mapped SRAM/chip RAM | WRAM `0..0x1FFFF`, little-endian. The tested core falls back to `READ_CORE_RAM`; RA values above `0x1FFFF` are **not** ordinary WRAM offsets |
| N64 / Mupen / ParaLLEl | RA host-order RDRAM | Convert RA u8 address with XOR 3, u16 with XOR 2, aligned u32 unchanged; Gauntlet then uses `swap32`, big-endian. Do not XOR an already-logical address twice |
| PSX / PCSX ReARMed (tested), SwanStation (attempted) | Main-RAM offsets | `0..0x1FFFFF`, little-endian; cached pointers need a main-RAM mask and range check. Readability on one core does not certify another core or disc revision |
| GB/GBC / Gambatte | Native mapped bus addresses | Linear, usually little-endian; e.g. `$DB95`, not a raw index into `retro_get_memory_data(2)`. GB and DX maps are different sets |
| GBA / mGBA | RA concatenated IWRAM/EWRAM | RA `<0x8000` becomes `0x03000000+a`; RA `0x8000..0x47FFF` becomes `0x02000000+a-0x8000`. Native IWRAM reads were checked over UDP |
| Genesis / Genesis Plus GX | RA/core RAM offsets | Repository default is `swap16`, big-endian. Confirm a known u8 AND u16 live before translating a new set; no Genesis ROM in this user's inventory was available |
| PC Engine / PCE Fast | RA RAM offsets | 8 KiB, normally linear/little-endian; region-specific notes must remain separate |
| Neo Geo / FBNeo | Driver-specific RA map | Do not import Genesis's layout just because both use a 68000. Check FBNeo driver, BIOS and ROM-set revision first |
| GameCube / Dolphin | MEM1 offsets | Linear/big-endian; mask `0x80xxxxxx` pointers to MEM1 offsets. US/EU notes differ. No `gc` catalog entry exists yet |
| PS2 / PCSX2 | EE RAM offsets / pointers | Native little-endian; base game and Special Edition maps differ. No `ps2` catalog entry or validated network-read path exists yet |

The memory code already supports pointer metrics, including nested pointers;
Samurai Shodown II does **not** require adding a new pointer feature. However,
null/range checks, float decoding, popcount, BCD conversion, actor lookup,
multi-condition finish guards and edge-trigger latches are not interchangeable
with a single `equals 0` metric. Do not silently approximate an unsupported
condition in a playable preset.

For every challenge: capture the baseline after loading the start state, require
the correct mode/room/opponent, observe a live boss/nonzero count before accepting
its disappearance/zero, distinguish death/retirement/escape from victory, and
latch transient events at emulator-frame cadence. A normal 0.5-second UDP poll can
miss a one-frame finish event. Reloading a state, entering attract mode or loading
an empty actor slot must never award a win.

## A. Boss fights and showdowns

### 1. Metal Gear Solid — PSX

[Primary notes, RA 11244](https://retroachievements.org/dorequest.php?r=codenotes2&g=11244).
Existing live evidence covers US v1.0 campaign mode `0x117084` u16, map ASCII
`0x0B7500`, Snake HP `0x0B7526` u16 and HUD `0x0ADB3F`. It does not verify bosses.

- **Grey Fox:** `0x0B8CCE` u16 Ninja HP is already source-backed in the original
  research. Arm only after the lab fight loads with positive HP; require Snake
  alive, unchanged continue count and a post-fight transition. Cutscene mode alone
  is not a win.
- **Psycho Mantis:** statue/call event notes exist, including v1.1
  `0x0B6570` bit7 and `0x0B657A` bit0 for statues. Neither means Mantis defeated.
  The exact HP/defeat signal and controller-port setup still need a fight state.
- **Sniper Wolf:** identify which of the two encounters is intended, capture its
  map and loaded enemy object, then correlate HP with the victory event. A generic
  boss slot must not be assumed to identify both encounters.
- **Level-1 card:** v1.0 `0x0B757C` is ID-card level; v1.1 uses `0x0B7584`.
  Baseline 0 -> 1 is the acquisition signal. In v1.1 `0x0B757C` is rations.

Owned Disc 1/2 exist in RoMM. Existing Dock evidence is retained; no new natural
Mantis/Wolf/Ninja defeat was observed. Never mix the adjacent v1.0/v1.1 fields.

### 2. Final Fantasy VII — PSX

[Primary notes, RA 11242](https://retroachievements.org/dorequest.php?r=codenotes2&g=11242).
Existing opening-battle observations validate `0x062FF9` battle active,
`0x062F54` u16 sticky formation, `0x0F83C6` outcome (`0x20` win, `0x22` loss,
`0x04` escape), enemy HP `0x0F85AC` u32 with `0x68` stride, and story progress
`0x09D288` u16.

- **Sephiroth:** use Safer Sephiroth on Disc 3, not the scripted final duel.
  Capture its formation and all living enemy parts, then the winning outcome.
  No exact Safer formation is asserted from the partial enum.
- **Guard Scorpion:** formation **`0x0144`** plus outcome `0x20`; this is much
  stronger than the first enemy HP reaching zero in any battle.
- **Chocobo race:** music `0x09A14E` u16 distinguishes race win `0x003C` from
  loss `0x003D`. Gate on an active Gold Saucer race and latch the result; prize
  `0x09D4A4` is not itself a win flag.
- **Reactor door:** field `0x09A05C` u16 and story progress can identify a transition,
  but the exact door event and before/after values need the intended state.

All three discs are owned. Existing battle-flow testing is not a late-game test.
Outcome is transient for approximately three seconds; formation persists afterward.

### 3. Mega Man 2 — NES, with two Mega Man 1 objectives

[MM2 notes, RA 1451](https://retroachievements.org/dorequest.php?r=codenotes2&g=1451)
and [MM1 notes, RA 1448](https://retroachievements.org/dorequest.php?r=codenotes2&g=1448).
MM2 has player HP `0x06C0`, shared boss HP `0x06C1`, current stage `0x002A`
(**Metal Man = 6**) and stage-complete/boss-defeated `0x00BD`, all u8.
The earlier "RA game 44" search result was wrong.

- **Metal Man:** stage 6, initialized boss, HP decrease/death plus clear flag.
- **Wily Dragon:** same HP slot; capture its fortress-stage ID and clear transition
  from a real Dragon state, not an inferred stage-select cursor number.
- **Yellow Devil:** **MM1**, stage 6 at `0x0031`; MM1 boss HP `0x06C1` and
  clear flag `0x00BB` are the candidates.
- **Magnet Beam:** **MM1**, weapons byte `0x005D` bit7. MM2 instead has Items 1–3.

Owned MM2 was run through title/password/stage menus. Positive gameplay/boss HP
was not captured in these menu probes, so it is not marked boss-verified.
Existing MM1 gameplay evidence is separate. Correct the ROM attribution before building.

### 4. Castlevania: Symphony of the Night — PSX

[Primary notes, RA 11240](https://retroachievements.org/dorequest.php?r=codenotes2&g=11240).
State `0x03C9A4` u8: 1 gameplay, 2 menu, 3 room transition, 4 loading.
Alucard HP `0x097BA0` u16; max `0x097BA4`.

- **Richter:** `0x076316` u16 is Shaft-controlled Richter/Doppelganger HP.
  It is shared. Decide whether to kill Richter or save him by destroying Shaft's
  orb; orb-defeated `0x03BE81` is **not** Richter's death.
- **Death:** bestiary `0x03BF8D` bit7 is not sufficient evidence of killing Death.
  Resolve the loaded actor/part HP and post-fight flag; do not reuse Slogra's
  `0x076ED6` from an unrelated boss.
- **Soul of Bat:** `0x097964` u8: 0 absent, 1 owned/off, 3 owned/on. Accept
  ownership bit0, not equality to 3 only.
- **Inverted Castle:** `0x03BE82` is the pre-inverted Maria/Richter cutscene
  flag, not proof of entry. Correlate castle/map state and actual room transition.

No matching SotN ROM was found in the owned inventory; no local test. The intro
Richter/Dracula HP at `0x137988/0x13798C` does not identify the later Richter fight.

### 5. Super Metroid — SNES

[Primary notes, RA 236](https://retroachievements.org/dorequest.php?r=codenotes2&g=236)
and existing Ceres live research. State `0x0998` u16, room `0x079B` u16, area
`0x079F`, collected items `0x09A4` u16. Generic enemy HP `0x0F8C` u16 is reused.

- **Kraid:** boss latch `0xD829` bit0 is preferable to an empty enemy slot.
- **Ridley:** Norfair latch `0xD82A` bit0, with the Lower Norfair encounter;
  Ceres Ridley is not the killable Ridley goal.
- **Morph Ball:** collected-items bit2 (`0x0004`), not equipped-items-only `0x09A2`.
- **Escape Zebes:** identify successful escape/ending state and ship-room
  transition; merely entering a room or starting the timer is not escaping.

Owned ROM hash was checked. Existing Ceres state/energy/area observations are
retained, but neither these boss latches nor the Zebes ending was tested naturally.

### 6. Ocarina of Time — N64

[Primary notes, RA 10113](https://retroachievements.org/dorequest.php?r=codenotes2&g=10113)
and [decompilation](https://github.com/zeldaret/oot).
RA mode `0x11B92C` u32: 0 boot/gameplay, 1 title, 2 file select.
RA age `0x11A5D4` u32: 0 adult, 1 child; source inventory sword byte `0x11A66E`.

- **Gohma:** actor identity/room must precede actor HP. Kokiri's Emerald
  (`0x11A676` bit2, RA host address) is an award proxy **after** victory, not
  the death frame. Resolve the Gohma actor's health through the decomp actor table.
- **Master Sword:** sword byte bit1 plus child -> adult transition; having the
  item in a preloaded adult save is not pulling it.
- **Epona:** RA `0x11B4A5` bit0 is escape-with-Epona; Epona's Song bit5 in
  `0x11A675` is not ownership. Race victory and successful ranch escape differ.
- **Ganon:** multi-phase actor/ending event; Ganondorf and Ganon must not be
  conflated. No static HP zero address is certified here.

US owned ROM was run in ParaLLEl N64 with real 8 MiB RDRAM and file-select
screenshots. The sample mode was 0 while in file select: **the source offset was
not validated on this ROM**. Do not promote the proposed offsets without checking
its revision/decomp map. Health zeros in an unselected save prove nothing.

### 7. A Link to the Past — SNES

[Primary notes, RA 355](https://retroachievements.org/dorequest.php?r=codenotes2&g=355).
Mode `0x10` u8, room `0xA0` u16, world `0x0FFF` u8 (0 light, 1 dark),
sword `0xF359` u8 (2 Master Sword), health `0xF36D`.

- **Agahnim:** room `0x20` Castle Tower versus `0x0D` Ganon's Tower.
  Sprite HP array `0x0E50` + slot and identity array `0x0E20` + slot;
  post-fight world/story transition disambiguates a defeated actor.
- **Master Sword:** `0xF359` 1 -> 2, room/overworld guard; `0xFF` means the
  blacksmiths have the sword, not "a very powerful sword".
- **Dark World:** `0x0FFF` 0 -> 1 while live gameplay, not menu initialization.
- **Ganon:** room `0x0000`, identified sprite and death transition. Triforce-room
  overworld ID `0x88` is a later completion proxy, not raw HP.

Owned US ROM reached name registration: mode 4 and health 0. Name-entry
automation did not reach gameplay, so the objective bytes are source-only.

### 8. Pokémon Red/Blue — GB

[Primary notes, RA 724](https://retroachievements.org/dorequest.php?r=codenotes2&g=724)
and [pokered disassembly](https://github.com/pret/pokered).
Mapped native addresses; these are **not** FireRed/Emerald fields.

- **Brock:** badges `0xD356` bit0 is the persistent success latch.
- **Pikachu:** caught-Pokédex `0xD2FA` bit0. Party species at `0xD164..D169`
  uses internal species IDs, not National Dex numbers. A full party can send a
  caught Pikachu to the PC, so party-only detection is wrong.
- **Starter:** party count `0xD163` and starter species plus leaving Oak's lab
  (`0xD35E` map); count 1 alone could be another Pokémon.
- **Lance:** `0xD866` bit1, Pokémon League defeat flag. An individual opponent
  HP reaching zero does not win his whole multi-Pokémon battle.

No Red/Blue ROM found in the owned inventory. Big-endian Pokémon HP structures
are an exception to the CPU's usual little-endian field convention; use widths
from the disassembly. Pokedex caught spans 19 bytes, not the preliminary report's
mistaken "9 bytes".

### 9. Final Fantasy VI / US Final Fantasy III — SNES

[Primary notes, RA 341](https://retroachievements.org/dorequest.php?r=codenotes2&g=341).
Formation `0x11E0` u16, event flags in `0x1E80..`, Terra field HP `0x1609` u16;
in-battle party HP `0x3BF4` + 2*n are different fields.

- **First boss:** it is **Whelk**, not the Magitek Armor the party pilots.
  `0x1EA6` bit5 explicitly means defeat Whelk.
- **Opera Ultros:** `0x1EE9` bit3. Do not use `0x1E83` bit2: that is the
  earlier raft Ultros encounter.
- **Airship crash / World of Ruin:** map `0x1F64` u16 distinguishes world
  contexts, but the exact post-crash story latch must be captured. Loading any
  World of Ruin save must not count as surviving the crash.
- **Kefka:** formation plus final death/result/ending; `0x0014` u16 sound value
  `0xC17F` is documented during final death, but sound alone is not a robust win.

Owned US Rev 1 boot/intro samples gave Terra HP 63; inactive battle HP was
`0xFFFF`. This is direct evidence that ungated HP checks read sentinel values.
No boss clear was observed.

### 10. Chrono Trigger — SNES

[Primary notes, RA 319](https://retroachievements.org/dorequest.php?r=codenotes2&g=319).
Room `0x0100` u16; enemy IDs `0x5FAD` and HP `0x5FB0` u16, both with `0x80`
per battle-slot stride. Crono field HP `0x2603` u16.

- **Truce Canyon:** select a destination room/story transition and record its
  actual value; a generic room change could be entering instead of escaping.
- **Marle's pendant:** correct the wording: collecting the pendant at the fair
  versus restoring Crono on Death Peak are different events. `0x10057` bit6
  explicitly says Crono saved, **not** the fair pickup.
- **Magus:** identify enemy ID/formation in the intended castle fight, watch
  the appropriate slots, and confirm battle victory; killing one part is not enough.
  If "kill" literally means the optional North Cape duel instead, source
  `0x10138` bit1 is killed Magus (bit0 recruited, bit2 amulet collected).
  Castle story `0x10000` progresses beyond `0x89`; that is not his literal death.
- **Lavos:** final room `0x01DF`; `0x0111` is only a **possible** defeat byte
  in the source. The final core has multiple enemies; HP of the wrong part is
  not victory.

Owned US ROM reached Crono's name screen. Field HP sampled 70; inactive enemy
HP was unrelated `0x33BB`. No fair, canyon or final-battle success was tested.

### 11. Doom bosses — PSX / SNES / GBA

[PSX RA 11256](https://retroachievements.org/dorequest.php?r=codenotes2&g=11256),
[SNES RA 2132](https://retroachievements.org/dorequest.php?r=codenotes2&g=2132),
[GBA RA 528](https://retroachievements.org/dorequest.php?r=codenotes2&g=528).
These are independent ports, not interchangeable maps.

- **Barons:** verify both E1M8 boss actors dead and the exit completion. A
  generic kill count includes ordinary monsters.
- **Cyberdemon:** identify the intended level/actor and successful finish; no
  dedicated boss HP is documented in the complete SNES/GBA note sets.
- **Spider Mastermind:** same actor/level requirement; a port may omit/rearrange
  the original encounter.
- **Icon of Sin:** **Doom II**, not Doom I. PSX Doom's merged/reworked content
  and the original Doom GBA/SNES releases do not establish a MAP30 Icon challenge.
  A separate Doom II version/ROM and its own map are required.

SNES mode `0x06B4`: 4 in level, 2 results; level `0x06D1` enumerates E1M8 = 7,
E1M9 = 8. PSX map `0x078098` changes on results, with special reset behavior.
No listed Doom-port ROM was found; owned Doom 64 is **not** a substitute.

### 12. Doom quick races — same ports, separate goals

Use the three sources in entry 11. PSX equipped weapon `0x0A8858` (shotgun 2,
BFG 7); player pointer `0x0A87EC`, health at +`0x68` u16. SNES equipped weapon
`0x0712`: shotgun 4, BFG `0x0E`. GBA source equipped weapon `0x04F4`: shotgun 2,
BFG 6; native mGBA address is `0x030004F4`.

- **Shotgun:** an ownership transition is ideal; equipped-weapon change alone
  only certifies equipping a shotgun, not its first pickup.
- **E1M1 exit:** SNES level 0 plus mode 4 -> 2, or PSX results-map transition.
  GBA state source `0x6EA4` is `0x0C` gameplay, `0x0D` episode map.
- **E1M9 secret:** validate the port's secret-exit routing, not the original
  PC numbering; reaching any map number 9 is insufficient.
- **BFG:** ownership versus equipment has the same caveat as shotgun.

No local port test. SNES RA `0x020000+` notes include extra chip-mapped memory
outside ordinary WRAM; a Snes9x system-RAM scan cannot verify those fields.

### 13. Resident Evil 2 — PSX / N64

[PSX RA 11245](https://retroachievements.org/dorequest.php?r=codenotes2&g=11245)
and [N64 RA 10077](https://retroachievements.org/dorequest.php?r=codenotes2&g=10077).
PSX notes distinguish Leon/Claire and scenarios; the same byte can have different
meanings. N64 source health `0x0E1320` is u8 (maximum 200).

- **Police Station key:** define Spade versus Club/Heart/Diamond. Claire-A
  Spade collection is `0x0D487C` bit2; not a universal character-independent flag.
- **First Licker:** PSX Claire-A kill `0x0D4838` bit2; Leon-A `0x0D4880` bit2.
  Encounter flags such as `0x0D4815` are not kill flags.
- **G Birkin:** specify form/scenario. N64 camera `0x0E924C` u16 has
  `0x145D` G-type 3 defeated and `0x14A6` G-type 4 defeated; verify the camera
  transition rather than accepting a loaded results scene.
- **Tyrant:** B-scenario Super-X defeat differs from his earlier encounters;
  N64 `0x0E8D2E` bit7 is the published Super-X flag.

Owned N64 US was run in ParaLLEl. Initial health was 0 and intro/camera state
was active, not gameplay. A content-checked PCSX ReARMed UDP probe on owned US
Dual Shock Disc 1 read `0x1FFFFC` as `0x800784B0`, exactly the source's Leon-disc
primary pointer. Leon HP was 0 at boot: pointer/transport corroboration, not a
live fight or boss verification. No objective was naturally completed on either port.

### 14. GoldenEye 007 — N64

[Primary notes, RA 10073](https://retroachievements.org/dorequest.php?r=codenotes2&g=10073).
Existing verified multiplayer stats are not single-player objective data.
The full notes provide u32 mission ID `0x02A8F8` (Dam 1, Facility 2, Cradle
`0x18`), difficulty `0x02A8FC` (0 Agent, 1 Secret Agent, 2 00 Agent), screen
`0x02A8C0` (`0x0B` gameplay, `0x0C` debriefing), and mission state
`0x0364B4` (0 in mission, 1 clear). Objective statuses `0x075D58 + 4*n`
are 0 incomplete, 1 complete, 2 failed; the ordering follows 00 Agent even
at lower difficulties. These aligned u32 RA addresses need no XOR conversion.

- **Dam bungee:** use successful mission-end status after jumping with the
  required objectives complete, not entering a falling animation.
- **Facility:** mission completed, not aborted/dead; objective layout varies
  with difficulty, so start states must pin difficulty.
- **Ourumov on Frigate:** **invalid premise**. Frigate's objectives involve
  hostages/bombs/bugging the helicopter; Ourumov is not its boss. Correct the game
  design before searching for an impossible Frigate Ourumov-death flag.
- **Trevelyan:** Cradle actor/objective victory, not multiplayer kills. Capture
  the active character/objective structure from a Cradle state. Mission-`0x18`
  clear is a later success proxy, not an exact Trevelyan HP/death byte.

Owned ROM and existing multiplayer evidence exist. No single-player completion
offset is live-certified from those multiplayer measurements; the source-only
mission fields above are the concrete starting point for all valid mission goals.

## B. Famous firsts

### 15. Super Mario Bros. — NES

[Primary notes, RA 1446](https://retroachievements.org/dorequest.php?r=codenotes2&g=1446)
and [disassembly](https://github.com/threecreepio/smb-disassembly).
World `0x075F` is zero-based; lives `0x075A` is lives-minus-one (`0xFF` game over).
`0x0760` is an internal level/area counter whose underground transitions also
count; do not assume it always equals the displayed level minus one. Source state
`0x0770` is 0 title/demo, 1 gameplay, 2 world finished, 3 game over; player
state `0x000E` is 4 flagpole, 5 area complete, 8 normal and `0x0B` dying.
The earlier RA 1488 citation was DuckTales, not Super Mario Bros., and was discarded.
Do not reuse SMB3 or Super Mario All-Stars fields.

- **1-2 Warp Zone to World 4:** world 0 -> 3 from the specified 1-2 state.
  Standing near pipes is not taking the warp.
- **1-1:** normal state -> flagpole/area complete then the correct next area,
  excluding death. World-finished state 2 is for a castle/world exit, not every level.
- **3-1 staircase 1-Up:** compare lives against the baseline and the intended
  displayed threshold. A starting five-life state must not win immediately.
- **World-1 Bowser:** specifically World 1-4; its fake Bowser is valid for this
  goal. The initial community-map paragraph restricting every Bowser goal to
  World 8 does **not** apply to this requested World-1 challenge.

No standalone SMB1 ROM found. The owned All-Stars and Deluxe versions have
different RAM maps and were not substituted.

### 16. Super Mario 64 — N64, existing

[Primary notes, RA 10003](https://retroachievements.org/dorequest.php?r=codenotes2&g=10003),
existing USA gameplay evidence/preset in [ram-research.md](ram-research.md),
and [decompilation](https://github.com/n64decomp/sm64).
Logical level `0x32DDF8` u16 and Mario action `0x33B17C` u32 are already verified.

- **Wing Cap:** save-file cap-switch bit, not whether Mario temporarily wears it.
- **Bowser key:** specify first/second key and test its acquisition bit; stars
  are not keys.
- **Castle roof:** Castle Grounds is the same level above and below the roof.
  **Room ID alone cannot certify roof access**; require Mario's Y/position region
  and normal control, excluding a cannon trajectory passing nearby. Source object
  structure has Y +`0xA4` as float, existing flag +`0x76`, behavior pointer
  +`0x20C`; identify Mario's object before reading it. Float-aware region checks
  are not currently a native integer metric.
- **First Bowser:** match the arena and key/exit victory transition. Shared
  actor HP zero between phases/loading is not sufficient.

No change to the existing live-verification claim. The four ideas still need
goal-specific state/flag checks; "existing" does not make roof room-ID detection valid.

### 17. Sonic the Hedgehog 2 — Genesis

[Primary notes, RA 10](https://retroachievements.org/dorequest.php?r=codenotes2&g=10).
RA zone `0xFE11`, act `0xFE10`, rings `0xFE20` u16, emerald count `0xFFB0`,
Super state **`0xF65E`**: 0 normal, 1 transforming, `0xFF` Super, 2 reverting.
The preliminary report's `0xFE65` transposition was rejected against the full note.

- **Emerald Hill act 1:** active gameplay then act/zone clear transition.
- **Robotnik:** Emerald Hill boss slot `0xB520`; require the actual loaded
  boss and its death/act completion, not a zero in a reused slot.
- **First emerald:** baseline emerald count increases after a real special stage.
- **Super Sonic:** `0xF65E == 0xFF`, with emerald/ring prerequisites;
  1 only means the transformation is underway.

No Genesis ROM found. Check byte-swap semantics live before copying these RA
offsets into `swap16` logical vars. Boss slots differ by zone.

### 18. Pac-Man — NES / arcade

[NES primary notes, RA 1491](https://retroachievements.org/dorequest.php?r=codenotes2&g=1491).
Use NES as the documented target; arcade board/driver maps are separate.
State `0x003F`: 4 normal, 6 ghost eaten, 8 dying, `0x0C` last pellet,
`0x0E` switching level; demo `0x0047`, level `0x0068`, pellets `0x006A`.

- **Eat ghost:** gameplay state -> 6, excluding attract demo. `0x0607 == 8`
  lasts 30 frames during ghost-eating, so latch it.
- **First fruit:** `0x0606 == 0x80` or source fruit graphic `0x0037 == 0x2C`
  for eaten cherry; distinguish fruit present from fruit collected.
- **First maze:** armed positive pellets -> zero and last-pellet/advance state.
- **Three mazes:** level progression from the captured baseline; confirm whether
  the exact ROM's counter starts at 0 or 1 before using ">= 4".

No matching NES/arcade ROM found. Pause signatures differ across Namco/Tengen/Japan/EU.
The earlier search's game IDs 1061/1463 were not used as evidence.

### 19. Donkey Kong — NES / arcade

[NES primary notes, RA 1466](https://retroachievements.org/dorequest.php?r=codenotes2&g=1466).
Sublevel `0x0053`, loop `0x0054`, lives `0x0055`, Mario state `0x0096`
(1 walking, 2 ladder, `0x0A` hammer, `0xFF` dying), Pauline saved `0x009A`.

- **Hammer:** state -> `0x0A`; hammer availability `0x0451/0x0452` decreases
  but disappearance alone could be stage reset.
- **25m:** clarify goal: the barrel board **is the starting 25m stage**.
  Loading it cannot be a race win; choose a spatial girder/height target.
- **Pauline:** `0x009A` 0 -> 1 plus first-board completion/sublevel increment.
- **Rivets:** eight flags `0x00C1..0x00C8` plus successful board clear.

Owned **Donkey Kong Classics** (not the standalone RA-supported ROM) reached
gameplay with Mario state 1, sublevel 1, demo 0 and lives 2. This corroborates
basic shared-engine fields on that compilation, not hammer/rivet victory.
Arcade's missing cement board in NES means progression cannot be shared wholesale.

### 20. Dr. Mario / Tetris — NES / SNES / GB

[NES Dr. Mario RA 1469](https://retroachievements.org/dorequest.php?r=codenotes2&g=1469),
[NES Tetris RA 2022](https://retroachievements.org/dorequest.php?r=codenotes2&g=2022),
[SNES compilation RA 1259](https://retroachievements.org/dorequest.php?r=codenotes2&g=1259).

- **10 lines / 25 lines:** Tetris only. NES `0x0050` u16 is BCD: compare
  against `0x10` / `0x25`, not decimal 10 / 25. Confirm increasing progression.
- **All viruses:** NES Dr. Mario `0x0324` (BCD-like HUD count) reaches zero
  while mode `0x0046 == 4` after a positive starting count. SNES virus count
  `0x03E7` has its own mode/clear state.
- **Level 10:** pick the Tetris versus virus-level interpretation explicitly.
  NES Tetris `0x0044`; Dr. Mario level `0x0316`; their numbering/selection rules
  differ. A menu-selected level 10 must not auto-award.
- **GB variants:** no GB title-specific map was certified from these NES/SNES
  notes; do not call them a portable GB preset.

Owned NES Dr. Mario sampled mode 4, viruses 4 with matching gameplay screenshot.
Owned SNES compilation was probed, but the final sample remained on Tetris
settings (zero lines), not a line-clear test.

## C. Fighters

### 21. Street Fighter II Turbo — SNES, existing source research

[Primary notes, RA 648](https://retroachievements.org/dorequest.php?r=codenotes2&g=648).
P1/P2 HP `0x0530/0x0730`, rounds `0x05D0/0x07D0`, character
`0x05D1/0x07D1`, control `0x05C0/0x07C0` (1 player), battle `0x18BD`.

- **First Hadouken:** an attack/projectile hit must be identified, not just HP
  loss. No certified Hadouken-specific hit byte in the researched map.
- **Round:** positive increment in the correct player's rounds counter.
- **Perfect:** round result plus full starting HP (`0xB0`), excluding ties/timeouts.
- **Bison:** character ID 8, arcade mode and target round/match victory;
  `0xFF` is a KO sentinel, not the greatest HP.

No SNES SF2 Turbo ROM found. World Warrior addresses `0x0C2B/0x0E2B` do not apply.

### 22. Mortal Kombat II — SNES / arcade, existing

[Primary SNES notes, RA 647](https://retroachievements.org/dorequest.php?r=codenotes2&g=647).
Existing live SNES US Rev 1 preset: health `0x2EFC/0x30AA`, full `0xA1`,
zero eliminated. Source characters `0x2EF8/0x30A6` and rounds won
`0x2F04/0x30B2` are separate from HP. Arcade offsets are independent.

- **Fatality:** identify the finishing move/result state; KO health zero happens
  before the finisher and is not a Fatality flag. Source `0x3252` is 1/2
  Fatality, 6 Pit Fatality, 8 Kombat Tomb spikes; `0x3253 == 0xFF` means
  finishing move accomplished. Require the allowed move type AND accomplishment
  transition, excluding source type 5 Babality and 7 Friendship.
- **Smoke:** the proposed **Living Forest hidden fighter** premise is wrong
  for MKII's standard Smoke access; his visual cameo is not a fight victory.
  Resolve the supported port's hidden-fight entry; source P2 character `0x0E`
  identifies Smoke. Cheat selection `0x2E9A == 6` is not a defeated-Smoke flag.
- **Kintaro / Shao Kahn:** match opponent identity and final round result; shared
  P2 HP supports the battle but cannot select which boss. Source IDs `0x0C/0x0D`
  identify the two bosses; screen `0x1A0E == 0x1F` is Shao Kahn defeated.
  Source outcome `0x327E == 3` is "Finish Him", not a completed finisher.

Existing versus health is verified; none of these four goal-specific transitions
was newly verified. The source-backed finisher candidates are documented here,
not added to a playable preset without timing/version tests.

### 23. Tekken 3 — PSX, existing

[Primary notes, RA 11259](https://retroachievements.org/dorequest.php?r=codenotes2&g=11259)
and existing live evidence: screen `0x0AE224 == 8`, P1/P2 rounds
`0x0A926C/0x0AAAF8`, HP `0x0A961E/0x0AAEAA` u16, characters `0x098106/7`.

- **Eddy round:** character 8 plus a new rounds-won increment.
- **Jin versus Kazuya:** **Kazuya is not playable in the standard Tekken 3
  roster**. This needs another game/mod, not a Tekken 3 RAM address.
- **Force stage 1:** Force progression is a different mode; normal versus
  round counters do not prove stage clear.
- **Ogre:** distinguish Ogre/True Ogre and final completion from a single KO.

Existing round detection remains valid. The invalid roster matchup must be
corrected before it becomes a challenge.

### 24. Super Smash Bros. — N64, existing

[Primary notes, RA 10082](https://retroachievements.org/dorequest.php?r=codenotes2&g=10082)
and existing verified VS structures. Logical screen `0x0A4AD0`: 22 match,
24 results; player records `0x0A4D28 + 0x74*n`, KOs +`0x14`, falls +`0x10`.

- **First KO:** increment KO, excluding suicide/fall-only events.
- **Home-Run Bat KO:** weapon/attack attribution must accompany KO; stock
  change alone cannot distinguish a bat from another attack.
- **Kirby two-stock:** configure stock mode and character, then survivors at
  results; raw source stock `0x1317CC` still needs mapping/slot validation.
- **Master Hand:** one-player boss structure and victory differ from VS;
  VS results screen and player-stock offsets cannot be blindly reused.

No new challenge completion observed. Existing time-match score testing is
retained without extrapolating it to bat attribution or one-player bosses.

## D. Racing

### 25. Mario Kart 64 — N64, existing

[Primary notes, RA 10078](https://retroachievements.org/dorequest.php?r=codenotes2&g=10078).
Existing logical state `0x0DC513 == 5` finished, P1 place `0x0F6994 == 0`,
laps `0x0F6998` u16, 0-based place. These were live tested crossing the line.

- **Blue Shell hit:** holding/using a shell is not a hit. Identify victim damage
  and projectile attribution; "while in first" also needs an explicit interpretation.
- **Wario shortcut:** lap/position alone can be achieved on the normal route.
  Use course-specific checkpoint/position-region progression, validated against
  ordinary laps and wrong-way/reset behavior.
- **Luigi Raceway / Rainbow Road:** correct course and finished flag with place 0.
  Existing finish mechanism is a strong reusable foundation.

Do not mark shortcut or shell-hit attribution verified because race finish works.

### 26. F-Zero GX — GameCube

[Primary notes, RA 9699](https://retroachievements.org/dorequest.php?r=codenotes2&g=9699).
Race-status `0x378591` bit0 finished, bit4 racing, bit6 cup won;
`0x378592` bit5 retired, course `0x378596`, race points `0x378668` u16.

- **Mute City / Cosmo Terminal / Big Blue:** identify the full named course,
  not just its venue; finish and first-place proof must agree. GP race points are
  a placement proxy only after the first-place value is actually calibrated.
- **Death-Race:** the **Death Race mode is associated with F-Zero X**, not a
  standard GX mode matching this description. Replace it with an actual GX
  story/race target before inventing a finish predicate.

Owned GX exists but a race state/placement calibration was not obtained.
Existing RA-only status notes are not live proof of winning. Two-window cap remains
a hardware hypothesis, not a benchmark result.

### 27. Crash Team Racing — PSX

[Primary notes, RA 10438](https://retroachievements.org/dorequest.php?r=codenotes2&g=10438).
US race-end flag `0x099088` (EU `0x099448`, JP `0x09C548`).
US player pointer `0x097FFC`, main-RAM-masked; +`0x30` Wumpa, +`0x44` laps,
+`0x3DC` boost meter, +`0x3E0` reserve. Track `0x096364` u16.

- **Crash Cove:** track `0x19`, end flag AND first place, not lap count alone.
- **Ripper Roo:** Roo's Tubes track `0x31` plus adventure boss context and victory.
- **Wumpa boost:** fruit count 10 changes item strength, but is not itself a
  turbo event. Require actual boost/reserve transition; distinguish pads/items/drift.
- **Oxide:** Oxide Station `0x69`, adventure boss identity/result, not merely
  winning an arcade race on his circuit.

No matching CTR ROM found. Player position notes contain regional variants;
calibrate the US racer placement field rather than borrowing the EU address.

## E. New games

### 28. Metal Slug — Neo Geo / FBNeo

[Primary notes, RA 11750](https://retroachievements.org/dorequest.php?r=codenotes2&g=11750).
Mission `0x6ED1`: 0..5, 6 all over; flag `0x6ED2`: 1 not defeated,
0 defeated, `0xFF` mission transition; P1 state `0xFDB7`: 1 playing.

- **POW:** `0x6F4C` u8 increases from baseline, P1 active.
- **Mission 1:** mission transition from 0 to 1 plus successful clear context.
- **Heavy Machine Gun:** `0x04B0 == 4`, versus handgun 0.
- **Boss 1:** armed `0x6ED2` 1 -> 0 in mission 0, with survival.
  The same flag also clears a screen, so confirm its timing against boss death.

No matching Neo Geo ROM/BIOS set found. `0x0204 == 0x0202` can mean **mission
end OR game over** and must not be used alone.

### 29. Super Mario Bros. 3 — NES

[Primary notes, RA 1995](https://retroachievements.org/dorequest.php?r=codenotes2&g=1995).
Power `0x00ED`: 3 raccoon, 4 frog, 5 tanooki, 6 hammer.
Mapped cartridge RAM includes world progress `0x7D00..0x7D3F` and source screen
`0x7DFC` u16 (`0x2736` in stage).

- **Leaf:** small/big -> raccoon 3 through a pickup, not an initially equipped state.
- **1-1:** matching map tile clear flag and in-stage -> map transition;
  map return caused by death is not a clear.
- **World-1 airship:** Koopaling damage `0x0083`: 0 full, **3 defeated**.
  This is an increasing damage counter, not HP that reaches zero.
- **Bowser:** own encounter/final event; do not reuse the Koopaling rule.

Owned US ROM was probed but screenshots remained title/menu. System RAM length
was 2048, so a direct pointer cannot read `0x7DFC`; use the mapped UDP space.
The cartridge-RAM clear flags reset per world.

### 30. Kirby's Adventure — NES

[Primary notes, RA 1479](https://retroachievements.org/dorequest.php?r=codenotes2&g=1479).
State `0x0190` includes `0x27` gameplay **and some world intros**; in-game type
`0x051C` 3 boss, screen `0x055E` u16, stage `0x0559`.

- **Fire:** equipped ability `0x05E3 == 0`; **`0xFF` means no ability**.
  Zero is therefore not an initialization-safe acquisition predicate.
- **Whispy / Kracko:** match boss screen and initialized fight, then source
  `0x0531` bit7 (Whispy) / `0x0534` bit7 (Kracko) 0 -> 1. These are explicitly
  named in the complete notes, not inferred from world numbering; an already-set
  progress bit will not detect a repeat win without another fight-ending signal.
- **Nightmare:** game-progress `0x0528 == 8` is a completion candidate,
  not merely entering the Star Rod phase; final boss lies outside the first
  six boss slots.

Owned US reached Vegetable Valley gameplay: state `0x27`, normal type 0,
stage 0, ability `0xFF`, matching the screenshot. **No Fire pickup or boss kill
was observed.** This confirms the important absent-ability sentinel.

### 31. Donkey Kong Country — SNES

[Primary notes, RA 337](https://retroachievements.org/dorequest.php?r=codenotes2&g=337).
Map/stage `0x0527`: 0 stage, 1 overworld; stage `0x0563`, KONG `0x057F`,
bonus timer `0x137F`; Gnawty HP `0x1503`.

- **KONG:** determine the four-letter mask from a stage state; the source
  labels the flag but does not justify guessing all bits or accepting any nonzero.
- **Jungle Hijinxs:** correct stage plus successful exit/progress, not any
  `0x0527` map return (death also returns).
- **Very Gnawty:** initialize the boss and use stage-specific HP/death;
  Really Gnawty also uses `0x1503`.
- **Bonus barrel:** room transition/bonus timer entering activity; the timer
  is reused after expiration, so an arbitrary nonzero value is not proof.

Owned US boot/menu probes completed; no natural level exit or bonus entered.
No unsupported single-condition preset was generated.

### 32. Contra — NES

[Primary notes, RA 1447](https://retroachievements.org/dorequest.php?r=codenotes2&g=1447).
State `0x0018`: 1 title, 2 demo, 3 starting, 5 gameplay, 6 ending;
stage `0x0030`: 0 Jungle, 2 Waterfall, 8 ending.
P1 weapon `0x00AA` low nibble, Spread 3.

- **Spread:** weapon low nibble -> 3 during real gameplay; ignore rapid-fire high bits.
- **Level 1 / boss 1:** stage-0 completion/boss-clear then progression to 1;
  enemy HP `0x0578+slot` and type `0x0528+slot` are shared.
- **Level 3 boss:** identify the Waterfall boss (often called Gromaides/Java)
  and stage 2. Name ambiguity is not permission to assign an arbitrary enemy slot.

Owned US actual RAM was probed; a sample state 2 was an attract-mode Base
scene, **not player gameplay**. A real RetroArch UDP check confirmed the NES
mapped transport and correct content, but it did not verify Spread/clear.

### 33. Samurai Shodown II — Neo Geo / FBNeo

[Primary notes, RA 12708](https://retroachievements.org/dorequest.php?r=codenotes2&g=12708).
P1/P2 character pointers `0x0A48/0x0A4C` **u16**, +`0x68` character u8,
+`0xBA` HP u16. State `0x0AE4 == 3` fighting; round flags `0x0AD4`
bit0 P1, bit1 P2, bit2 draw; condition `0x0ADF == 3` perfect.

- **First hit:** baseline opponent HP decreases with attack/hit attribution.
  Round victory flags do not detect a first hit.
- **Round / perfect:** round winner flag transition, plus condition 3 for perfect.
- **Kuroko:** match hidden referee character ID and legitimate win; his exact
  ID must be checked from a fight state, not assumed from another fighter.

No owned set found. Gauntlet's pointer support can express HP indirection, but
byte order, pointer target address-space translation and transient result values
still require the exact FBNeo driver. The preliminary "pointer support missing"
report was incorrect.

### 34. Castlevania — NES

[Primary notes, RA 1462](https://retroachievements.org/dorequest.php?r=codenotes2&g=1462).
Stage `0x0028` base 0; state `0x0018`: 5 gameplay, `0x0C` end orb,
`0x0F` ending. Real player HP `0x0045`, whip `0x0070`, boss arena `0x0048`,
real boss HP `0x01A9`, displayed HP `0x01AA`.

- **Whip:** baseline increase in `0x0070`, stable after the pickup animation.
  The primary note repeats 0 for basic and first upgrade: that textual typo
  must not override a live numeric check.
- **Giant Bat / Medusa:** stage-specific initialized boss HP -> defeated,
  then orb/exit. Zero at title/empty boss arena is not a kill.
- **Dracula:** distinguish his phases and use final ending, not the first
  humanoid-form HP zero.

Owned US reached gameplay: state 5, stage 0, full real HP `0x40`, whip 0.
This was screenshot-checked. The earlier sample whip 1 was during intro and is
not evidence of a pickup. No boss defeat observed.

### 35. Mega Man X — SNES

[Primary notes, RA 637](https://retroachievements.org/dorequest.php?r=codenotes2&g=637).
Stage `0x1F7A`: 8 Penguin, `0x0C` Sigma 4; X HP `0x0BCF`, max `0x1F9A`,
upgrade `0x1F99` bit3 legs, Hadouken `0x1F7E` bit7.

- **Dash:** legs-upgrade bit3 transitions on the capsule.
- **Chill Penguin:** stage 8, entity type `0x0E72 == 2` for the published
  slot, matched loaded boss HP/death. Slots can move.
- **Sigma first form:** specify final-stage sword Sigma versus Velguarder;
  require the corresponding actor/phase, not "any Sigma-stage boss".
- **Hadouken:** `0x1F7E & 0x80`, not a nonzero low-bit acquisition counter.

Owned US Rev 1 direct-core title samples and a content-checked Snes9x UDP probe
both returned HP/max 0 **at title**. UDP fell back to `READ_CORE_RAM`; this
validates transport, not those item or boss goals.

### 36. Link's Awakening — GB, with owned DX comparison

[GB notes, RA 669](https://retroachievements.org/dorequest.php?r=codenotes2&g=669),
[DX notes, RA 5371](https://retroachievements.org/dorequest.php?r=codenotes2&g=5371)
and [DX disassembly](https://github.com/zladx/LADX-Disassembly).
Sword level `0xDB4E`, equipped slots `0xDB00/1`, health `0xDB5A`, screen `0xDB54`.

- **Sword:** `0xDB4E` 0 -> 1, stronger than checking the currently selected button.
- **Moldorm:** identify room/entity HP through the disassembly; instrument
  `0xDB65` is a later award proxy, not the exact boss-death frame.
- **Trendy crane:** choose a prize (e.g. Yoshi Doll), then its inventory/event
  acquisition; winning any object and collecting a specified prize differ.
- **Nightmare:** final multi-form actor and ending state. No dedicated fixed
  Nightmare HP was established from the full GB code notes.

Only DX US/EU Rev 2 is owned, not original GB. Its complete notes were fetched;
Gambatte UDP correctly read native `0xDB95` and `0xDB5A` (both 0 at boot).
The direct frontend's native map requires descriptor support; a 32 KiB `ram_size`
scan from 0 is not a native GB WRAM scan. No sword/boss transition observed.

### 37. Majora's Mask — N64

[Primary notes, RA 10679](https://retroachievements.org/dorequest.php?r=codenotes2&g=10679)
and [decompilation](https://github.com/zeldaret/mm).
RA mode `0x1F3318` u32; source Deku Mask slot `0x1EF6FE` u8 = `0x32`;
remains byte `0x1EF72C` bit0 Odolwa, bit1 Goht.

- **Deku Mask:** actual inventory value transition after the healing sequence,
  not being in Deku form at the start of the prologue.
- **Odolwa:** remains award is a stable later proxy; `0x416924` is labelled
  **possible** Woodfall boss health and must remain tentative.
- **Goht:** `0x416FD4` source health, with actor/temple guard. Remains bit1
  does not refire when repeating a boss already beaten in the save.
- **Stop Moon:** Majora's multi-phase battle and successful ending; stopping
  the countdown by playing Song of Time is not the intended victory.

Owned US software-core probe reached file select and read mode 2. A separate
content-checked Mupen UDP sample was mode 0 during early boot. These establish
mode/transport sampling, not Mask or boss validation. Apply N64 byte conversion.

### 38. Yoshi's Island — SNES

[Primary notes, RA 558](https://retroachievements.org/dorequest.php?r=codenotes2&g=558).
Level `0x021A`, source stars `0x03B6` u16, boss-defeat `0x0B7B`
(1 normally; `0xFF` Salvo exception), scene `0x5B18`: `0x6C` map, `0xE9` level.

- **1-1:** correct level plus real successful exit/score result.
- **20 stars at finish:** stars must be sampled **at successful finish**,
  not awarded merely for reaching 20 mid-level. Confirm the internal counter's
  scale; do not assume display tens/ones `0x03A1/3` and u16 counter are equivalent.
- **Burt:** matched boss room and `0x0B7B` transition after an initialized fight.
- **Baby Bowser:** separate giant-boss phase and final ending; an earlier
  defeat-flag update could be only the first phase.

Owned US Rev 1 boot samples had zero stars; no level clear was reached.
RA notes above `0x1FFFF` are mapped Super FX/extra regions, not plain WRAM.

### 39. Bonk's Adventure — PC Engine

[Primary notes, RA 2279](https://retroachievements.org/dorequest.php?r=codenotes2&g=2279).
Round `0x0067` (`0x04` Huey boss, `0x26` King Drool), active `0x005C == 1`,
power form `0x0DBA`: 0 normal, 1 Old Bonk, 2 Super Bonk.

- **Stage 1:** define first substage versus whole round; `0x0067` progression
  can distinguish them once the baseline is selected.
- **First boss Huey:** `0x072C` wraps three times and dies at `0xD0` or
  `0xE8` per the source; **not HP == 0**. Prefer a confirmed post-fight transition.
- **Meat:** form 0 -> powered state; pre-existing power must not auto-award.
- **King Drool:** shared `0x06E9` tracks accumulated damage, 0 full and
  `>=0xB4` dead. Gladdis uses the same byte with `>=0x3C`.

No owned PCE ROM found. Punchy Pedro's binary state `0x0329` is not Huey's state.
Enemy health wraps/ascending damage make a generic "all bosses reach zero" wrong.

### 40. Perfect Dark — N64

[Primary notes, RA 10110](https://retroachievements.org/dorequest.php?r=codenotes2&g=10110).
Mission status `0x06AE74`: 1 completed, 0 failed/aborted/incomplete;
kill count `0x09A050`; objectives `0x09D088 + 4*n`: 1 complete, 2 failed.

- **dataDyne / Carrington Institute:** mission ID/context and completion,
  all required difficulty-specific objectives, alive; stale status after a load
  must be cleared at baseline.
- **5 Falcon 2 targets:** total kill count cannot establish which weapon was
  used, nor shooting-range targets versus mission enemies. Require range
  target/weapon-specific state; don't relabel generic kills as this objective.
- **Beat Elvis:** **invalid boss premise**: Elvis is Joanna's ally. Source
  `0x06825C` Elvis hit count does not turn him into a legitimate boss objective.

Owned US real-core boot probes produced zeros and a black transition screenshot;
no mission success validated. Source widths for sparsely labelled counters need
a live/decomp check before constructing vars.

### 41. R-Type — PC Engine

[Primary notes, RA 2145](https://retroachievements.org/dorequest.php?r=codenotes2&g=2145).
Force `0x0154`: 1 ready, 2 upgraded, 3 full; attached `0x015A == 1`.
Stage `0x12D9` covers 1–4 then `0x12A7` 5–8; demo `0x12D3 == 1`.

- **Force:** 0 -> owned 1+; detaching it is not losing ownership.
- **Stage 1 / Stage 3:** current-stage advancement during non-demo play,
  excluding death/continue, with correct region's stage storage.
- **Dobkeratops:** source has no fixed boss HP. Use identified multi-part
  boss actors or a validated successful stage-1 transition, not arbitrary enemy HP.

No owned PCE ROM found. Full notes include **US/Japan address reuse**: fields
that are US score digits can be Japanese power-up flags. Select one complete
region map. R-Type DX/R-Types/R-Type III are not this cartridge's RAM map.

### 42. Resident Evil — PSX / GameCube

[Owned PSX set RA 29328](https://retroachievements.org/dorequest.php?r=codenotes2&g=29328)
and [GC remake RA 3358](https://retroachievements.org/dorequest.php?r=codenotes2&g=3358).
They are different games/engines. PSX source inventory `0x0C8784` + 2*n,
enemy HP `0x0C532C` u16 (**`0xFFFF` dead**, not necessarily 0).

- **Mansion key:** specify Sword/Armor/Shield/Helmet. PSX `0x0C86DC` bit4
  Armor pickup is not the same key as the first Sword-key target.
- **Yawn:** GC `0x1F3A87` bit1 attic fight; second fight uses `0x1F3ACD`
  bit7. Specify encounter, do not count either interchangeably.
- **Tyrant:** GC `0x1F3AD6` bit6 first fight; rooftop final battle differs.
- **Escape:** GC `0x1F3A7D` bit7 game complete, with live before/after state.
  PSX needs its own ending/result guard, not the GC flag.

Owned PSX US was downloaded/hash-checked. SwanStation did not answer on the
isolated port; the available PCSX ReARMed alternative successfully returned
content-checked `READ_CORE_MEMORY` bytes. Player/enemy HP were 0 at boot,
not fight evidence. In particular, source `0x0C8454 == 0` says "in game" only
after valid initialization; a boot zero must not satisfy that predicate.
Complete RA 29328 notes include Original/Arrange semantics, so match the
executable/version before trusting fields; RoMM's RA ID is not an independent
achievement-hash match.
No GC remake ROM found (owned Resident Evil **Zero** is not the remake).

### 43. Streets of Rage 2 — Genesis

[Primary notes, RA 3](https://retroachievements.org/dorequest.php?r=codenotes2&g=3).
Screen `0xFC02 == 0x14` in game; stage `0xFC42` (0 first, `0x0E` eighth),
level-clear `0xFCC8` 0/`0xFF`; P1 HP `0xEF80` full `0x68`.

- **Stage 1:** clear flag in stage 0 plus progression.
- **Barbon:** shared boss/enemy HP `0xF180`, with actor identity/loaded status.
- **Mr. X / Shiva:** both final-stage encounters require their own opponent
  identification and sequence state. A single stage-8 HP zero can award for
  the wrong foe.

No Genesis ROM found. Shared object HP is not a per-boss guarantee; validate
P1/P2 and enemy-slot byte ordering using the actual core.

### 44. Gunstar Heroes — Genesis

[Primary notes, RA 7](https://retroachievements.org/dorequest.php?r=codenotes2&g=7).
Level `0xA204`, screen `0xA284`, P1 vitality `0xA424` u16; weapon slots
`0xA46E/0xA470`: 4 Force, 8 Lightning, `0x0C` Chaser, `0x10` Flame.

- **Seven Force:** seven transformations share/reallocate boss objects;
  `0xA824/0xC9A4/0xCA04/0xCB84/0xCBE4/0xD0C4` are candidate vitality
  slots. First form zero is not full fight victory.
- **Dice Palace:** name the actual boss/board result and detect final clear,
  not a defeated sub-room enemy or a dice-result change.
- **Stage 1:** level transition after the specified boss, with successful exit.
- **Fire + Force:** both slots contain `{0x10,4}` in either order, combined
  state active; having just one of them is not the requested combination.

No owned Genesis ROM. Owned Gunstar **Super** Heroes GBA is not a substitute.
The earlier apparent Force-enum contradiction was a truncated-read artifact.

### 45. Paper Mario — N64

[Primary notes, RA 10154](https://retroachievements.org/dorequest.php?r=codenotes2&g=10154).
US source story `0x0DBD73` u8; battle `0x0DC068` u8 (`0x21` victory).
US actor-pointer table `0x0DC150`, actor type +`0x135`, max HP +`0x1BA`,
current +`0x1BB`; mask full pointers then convert subfield host/logical offsets.

- **Goomba Road:** correct story/map transition, not any Goomba encounter win.
- **Kent C. Koopa:** actor identity + battle victory; tattle flag
  `0x0DBEF7` bit1 means information obtained, **not defeated**.
- **First Bowser:** **scripted unwinnable prologue battle**. Replace "beat"
  with a defined survival/story beat or select a later winnable Bowser encounter.
- **Final Bowser:** battle phase/actor identity, final victory and story/ending.
  Battle victory from an earlier enemy cannot satisfy it.

Owned US actual RDRAM sampled Mario HP 10 at file select and map-info pointer
`0x80074024`. Those initialized values do not certify being in gameplay.
US/JP/EU story/HP/actor tables differ; notes include all three.

### 46. Metroid: Zero Mission — GBA

[Primary notes, RA 534](https://retroachievements.org/dorequest.php?r=codenotes2&g=534).
Native mGBA mode `0x03000C70` (4 gameplay), area/room `0x03000054/55`,
collected suit byte `0x0300153E` bit6 Morph Ball.
RA event bytes `0x03FE03/4/9` translate to **`0x02037E03/4/9`**, not IWRAM.

- **Morph Ball:** collected bit6 0 -> 1, not temporary Morph Ball pose.
- **Kraid:** native `0x02037E03` bit6.
- **Ridley:** native `0x02037E04` bit5.
- **Escape Chozodia:** Mecha Ridley `0x02037E09` bit2 starts self-destruct;
  it does **not** mean escape completed. Require final escape/ending transition
  with Samus alive before timeout.

Owned US direct pointer probes initially read **wrong EWRAM offsets**; those
are not validation. Content-checked UDP subsequently confirmed native IWRAM:
mode 1 intro, area/room 0/0; low `0x0C70` read 0 and is not the correct mode.
Entity array native `0x030001AC`, stride `0x38`, HP +`0x14` is shared.
Boss latches are preferable to uninitialized enemy HP.

### 47. Ninja Gaiden — NES

[Primary notes, RA 1859](https://retroachievements.org/dorequest.php?r=codenotes2&g=1859).
Ryu HP `0x0065` max `0x10`; boss display `0x0066`; stage `0x006D`.

- **Act 1-1:** stage 0 -> 1 with legitimate progression, not title initialization.
- **Act-1 boss:** stage 1 (Barbarian); loaded boss HP/death then progression.
- **Act-3 boss:** stage 7 (Kelbeross), not source stage 3 (Act 2-2).
- **Jaquio:** match final boss-rush phase and actual actor, not any final-act
  HP zero. Real enemy HP `0x0490..97`, boss flags `0x0498..9F`;
  HUD HP is a lagged display copy.

Owned US direct-core probe remained at title with player/boss HP zero.
This is exactly why an unarmed `boss HP == 0` predicate cannot be used.

### 48. Earthworm Jim — Genesis / SNES

[Genesis RA 11](https://retroachievements.org/dorequest.php?r=codenotes2&g=11)
and [SNES RA 889](https://retroachievements.org/dorequest.php?r=codenotes2&g=889).
SNES level `0x512A` u16: 0 New Junk City, 3 Evil the Cat; plasma ammo
`0x69A0` u16; in-game/demo HUD `0x6620` upper nibble 3, demo `0x6B8E`.

- **New Junk City:** successful level transition with demo 0.
- **Evil the Cat:** identify his level-3 actor; generic entity HP at
  `0x51F2 + 0x80*n` is not guaranteed to be the boss.
- **Psy-Crow:** Genesis `0xA728` candidate HP, with race/fight phase guard.
  Do not transplant it to SNES.
- **Plasma Blaster:** SNES plasma ammo acquisition/increase plus pickup context;
  the normal gun is available already. Ammo alone may be consumed/replenished.

Owned SNES US was loaded/probed, but the final screenshot was a black
transition with level/plasma zero; no natural victory/pickup validated.
SNES `0x52F2` specifically covers fridge/cow and Rusty in the published note,
not every boss. Genesis level `0xA693` and next level `0xFF84` are separate maps.

### 49. Luigi's Mansion — GameCube

[Primary notes, RA 4325](https://retroachievements.org/dorequest.php?r=codenotes2&g=4325).
The source's address-0 note explicitly says **unlabelled notes are EU**.
US mode `0x3A3AE4`, US Boo pointer `0x3A3CC4`, existing US Boo flags
`0x3D5E04..0A` and HUD pointer `0x4D8618` remain separate from EU fields.

- **First Boo:** existing verified US flag/HUD foundation; capture a real
  post-radar state and natural catch. Earlier testing **wrote** a bit to show
  HUD count increasing; that is not evidence of a natural catch.
- **Neville:** EU HP `0x3C3295`, progression `0x3C3369` bit6.
- **Chauncey:** EU progression `0x3C336C` bit0; sequence `0x3C3344 == 0x23`.
- **King Boo:** EU progression `0x3C337F` bit5. Portrait/gallery flags update
  during later processing, not necessarily at the fight-ending frame.

Owned **US** ROM was downloaded/hash-checked and tested in Dolphin via
content-checked UDP `READ_CORE_RAM`. MEM1 `0x000000` returned ASCII **GLME01**,
the source's exact US identity (EU would be GLMP01). US state `0x3A3AE4` u32
was 0 (Nintendo logo) and map `0x4D80A4` u32 was 0, not a loaded boss room.
The source enumerates state 1 menu, 2 playing, 3 file select, 5 credits;
US map 2 mansion, 9 King Boo/Bowser, `0x0A` Chauncey. These provide US
context guards without importing EU boss flags.
US actor/pointer correlation still needs suitable boss states; old load/menu
hangs remain a risk, but the renewed run establishes readable MEM1 transport.

### 50. Super Mario RPG — SNES

[Primary notes, RA 471](https://retroachievements.org/dorequest.php?r=codenotes2&g=471).
Battle flag `0x3021 == 1`, formation `0xFA0E` u16, enemy HP `0xFC11` u16
with `0x80` stride; HP at **`0xFC12` is only its second byte**.

- **Mack:** formation `0x012E`, initialized living enemies then victory.
  RA `0x023082` bit0 is labelled "Defeated Mack?" and lies outside WRAM;
  it is not certified for Snes9x's fallback.
- **Bowyer:** formation `0x0131`, same multi-enemy/final-result guard.
- **Mushroom Kingdom start:** define a specific story transition, not merely
  "win the start"; no precise success predicate until that moment is selected.
- **Smithy:** `0x0134` identifies Smithy 1 only. Final form/head changes and
  final ending need their own formation/event mapping.

Owned US reached name selection; Mario field HP `0x1F801` sampled 20, battle
HP region showed filler `0x5555`. No boss victory. Screen `0x1FFC` differs by core
(published Snes9x exploring `0x36`, bsnes `0x83`), so pin the core/state.

### 51. Tony Hawk's Pro Skater 2 — PSX

[Primary notes, RA 11282](https://retroachievements.org/dorequest.php?r=codenotes2&g=11282).
Mode `0x0D626C`: 1 career, 2 free skate, 3 single-run/demo; level `0x0D6270`.
Run pointer `0x0D67E0` is zero outside a level; sticky `0x0D291C` needs that guard.

- **S-K-A-T-E / secret tape:** Tony Hangar goals `0x0BA798` u16 are per-skater,
  per-level bitsets. Exact goal masks must be calibrated; collecting one letter
  or showing a tape pickup sprite is not complete S-K-A-T-E.
- **First gap:** Hangar gap bits `0x0BBC1C` latch recognized gaps. Compare
  before/after and require a successfully landed run; a gap attempted mid-bail
  must not count.
- **900:** run +`0x920` contains 28-byte trick entries, name pointer +0,
  rotations +`0x0C`, trick flag +`0x14`. Require **The 900** trick identity and
  a landed combo. Merely rotating 900 degrees on another trick is not it.

No PSX THPS2 ROM found; owned N64 THPS2 has another map. Goal flags for Bob,
custom skaters, etc. are at other addresses. No invented universal goal mask.

### 52. Devil May Cry 3 — PS2, turns only

[Base game RA 32480](https://retroachievements.org/dorequest.php?r=codenotes2&g=32480)
and [Special Edition RA 2936](https://retroachievements.org/dorequest.php?r=codenotes2&g=2936).
Base enemy pointer `0x645A48` u32; HP fields are **floats**:
Cerberus +`0xA530`, Vergil +`0xAF94`. Base mission pointer `0x731654`,
mission +`0xC80`; UI pointer `0x645AE0`, +`0x30` menu `0x3F` mission clear.

- **Cerberus:** positive float HP -> defeated with mission 3/context and victory.
- **Agni and Rudra:** both enemies/phases must be defeated, including the
  surviving brother's combined weapon phase; do not accept one actor zero.
- **First weapon:** base Cerberus unlock `0x7316A7`, Agni/Rudra `0x7316A8`;
  "first weapon" must mean the first acquired weapon, not starter Rebellion.
- **Vergil first duel:** mission-specific actor and victory; later Vergil and
  boss-rush encounters use different context.

SE enemy pointer **`0x61AC90`**, Vergil +`0xB814`, Agni +`0x6A38`;
SE events `0x78F040` distinguish Cerberus/Agni fight stages, SE item
`0x78EEE7/8` are different from base. No DMC3 ROM found (owned DMC1 is not it).
Gauntlet integer metrics do not decode floats; PS2 integration and float-aware
conditions are real blockers, not a reason to treat IEEE-754 bytes as integer HP.

## Local evidence ledger and remaining verification

The direct-core runs returned real RAM for 18 NES/SNES/GBA targets and five
N64 targets. Not all reached gameplay. The following are the useful positive
observations, with all other samples treated as menu/boot/attempt evidence.

| Owned ROM | SHA-1 | Observation |
|---|---|---|
| Castlevania USA | `48ad27d5e6e0c68b1eab91c137a325d54ef19243` | FCEUmm state 5, stage 0, HP 64, whip 0; gameplay screenshot |
| Kirby's Adventure USA | `22663ce2da1343f3ba3ab3c7314b068c5a02f850` | State `0x27`, normal 0, stage 0, no-ability `0xFF`; gameplay screenshot |
| Dr. Mario Japan/USA | `c014ab83cfa9e10ffe870d5b852ca9d7237eb273` | State 4, viruses 4; gameplay screenshot |
| Donkey Kong Classics USA/Europe | `47303599d3d78291b1043493383cd68d096584ac` | Sublevel 1, walking 1, demo 0, lives 2; compilation gameplay, not standalone ROM |
| Majora's Mask USA | `d6133ace5afaa0882cf214cf88daba39e266c078` | ParaLLEl file-select mode 2; separate Mupen UDP boot read, correct content |
| Paper Mario USA | `3837f44cda784b466c9a2d99df70d77c322b97a0` | File-select initial HP 10, real pointer `0x80074024`; not a battle test |
| Zero Mission USA | `5de8536afe1f0078ee6fe1089f890e8c7aa0a6e8` | mGBA UDP native `0x03000C70` = 1; low offset = 0, proving mapping matters |
| Mega Man X USA Rev 1 | `c65216760ba99178100a10d98457cf11496c2097` | Correct-content SNES UDP reads; `READ_CORE_RAM` fallback verified, title HP 0 |
| Link's Awakening DX US/EU Rev 2 | `1c091225688d966928cc74336dbef2e07d12a47c` | Gambatte UDP native `$DB95/$DB5A` readable at boot; original GB not tested |
| Resident Evil USA PSX | `5001af9464e1d372571cf108a45b665ac355ef38` | PCSX ReARMed mapped UDP reads, correct disc content; boot HP 0, SwanStation attempt unresponsive |
| Resident Evil 2 Dual Shock USA Disc 1 | `e76d8440170e456bccd676004991e5aa6fabdfe7` | PCSX ReARMed source pointer `0x800784B0` corroborated; boot Leon HP 0 |
| Luigi's Mansion US RVZ | `9a1058058d8468e297916b208730135e4c951a14` | Dolphin MEM1 UDP reads, exact US identity `GLME01`; Nintendo-logo state 0, not a boss test |

ROM inventory absence is a **local-test blocker**, not evidence that no RAM map
exists. A missing exact byte is a **research finding**, not a guessed address.
Late-game bosses remain unverified because no suitable owned start states were
available and booting a game does not reach those encounters. Further certification
needs per-challenge before/fight/success/death/reload traces on the pinned ROM/core.

No new playable presets were generated: unresolved versions, impossible premises,
unsupported float/actor predicates and unvalidated finish conditions must not be
presented as working challenges. Every ideas-list entry now has a source/evidence
disposition and all four proposed goals have either a concrete RAM lead or an
explicit, challenge-specific blocker/correction.
