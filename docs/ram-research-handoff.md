# RAM research handoff

Updated: 2026-10-07. This is a checkpoint for continuing on another machine,
not a declaration that every proposed challenge works.

**PR publication update:** the user subsequently requested committing and publishing
these four documents as a pull request. The uncommitted/unpushed status below
describes the handoff checkpoint before publication. Once the branch is pushed,
fetching and checking out `ryanstephan42-game-ram-research` transfers the documents;
the optional evidence artifacts remain outside git and still need private transfer.

## Request and current outcome

The user requested comprehensive RAM-read research for every unresearched game in
`docs/new-game-ideas.md`, proceeding through the entire list and documenting each
game, ideally testing locally with real emulator RAM. The user explicitly
authorized downloading their owned ROMs from RoMM using their existing
ultimate-emulation token and installing RetroArch if needed.

**All 52 numbered entries and their 208 proposed goals now have research
dispositions.** The authoritative deliverable is
[new-game-ram-research.md](new-game-ram-research.md), in original list order.
It contains source-backed addresses, conversions, goal-specific detection leads,
invalid-premise corrections, local observations and explicit unresolved fields.
It does not claim that every address or challenge was live-verified.

Actual RAM was sampled using real libretro cores and isolated RetroArch UDP
launches. Most runs reached only boot/menu screens. Useful screenshot-correlated
gameplay was obtained for Castlevania NES, Kirby's Adventure, Dr. Mario NES and
Donkey Kong Classics. Late-game natural boss wins remain unverified.
No new production code or playable presets were created.

## Repository state to transfer

- Repository: `ryanstephan42/gauntlet`.
- Branch: `ryanstephan42-game-ram-research`.
- Current HEAD: `9b01018b083d89f26824b4cf34145a1f8532d16d`.
- Current worktree:
  `/home/r/workspace/copilot-worktrees/gauntlet/ryanstephan42-turbo-guacamole`.
- Work is **uncommitted and has not been pushed**. Checking out this branch on
  another machine alone will not transfer the research.
- Modified: `docs/new-game-ideas.md`, `docs/ram-research.md`.
- New: `docs/new-game-ram-research.md`, this handoff.
- No PR was created. No commit was requested or made.

Transfer all four documents, preserving the modified files as well as the new
ones. A normal unstaged `git diff` does **not** include untracked files.
Use your own secure file transfer or deliberately commit/push the documentation
before moving machines. Do not transfer the main checkout in place of this
worktree. On the destination, use its session worktree, not the original host paths.

### What each document does

| Document | Role |
|---|---|
| `docs/new-game-ram-research.md` | Authoritative 52-entry audit; use its corrections over preliminary maps |
| `docs/new-game-ideas.md` | Original ideas preserved; now links the audit, removes the stale unresearched claim, distinguishes proposed predicates, and corrects the Magnet Beam first-pick attribution |
| `docs/ram-research.md` | Existing evidence plus preliminary NES/SNES community maps and explicit primary-source corrections |
| `docs/ram-research-handoff.md` | Machine-transfer checkpoint and remaining-work checklist |

## Optional evidence and tool artifacts

The original host's artifact directory is:

```text
/home/r/.copilot/session-state/b335bfcb-188b-4e0e-b9a4-63e3fa5087b1/files/
```

These artifacts are **outside git** and will not accompany a branch checkout.
Transfer the following privately if continuing evidence review or emulator work:

- `notes-*.json`: cached full public RA primary code-note responses. The audit
  references 61 distinct nonempty sets; additional exploratory sets also exist.
- `probes/*.json` and corresponding screenshots: frame/input sequences, exact
  bytes, core versions and visual evidence. Screenshots contain game assets:
  do not add them to the repository.
- `udp-confirmed-*.json`: correct-content, unique-port UDP records. Current
  records cover RoMM IDs 46, 165, 248, 388, 692, 693 and 739.
- `core_probe.py`, `udp_check.py`, `romm_fetch.py`,
  `research-retroarch.cfg`: reusable experimental helpers.
- `romm-inventory.json`: owned-game/revision inventory, not a credential.
- `handheld-research.txt`: raw background-research report, **not authoritative**
  for Gauntlet architecture or conversions.

**Do not use `udp-probe-results.json`: its shared-port batch received another
game's responses and the entire batch is invalid evidence.**

`download-manifest.json` is overwritten by each downloader invocation; it is not
a cumulative inventory. Owned ROMs are in `owned-roms/`, private emulator writes
in `probe-saves/`. Do not commit ROMs, BIOS, saves, tokens or copyrighted assets.
Prefer re-downloading authorized owned files on the destination rather than
bundling credentials or ROMs into a handoff archive.

The helper scripts contain **absolute paths to the old worktree/artifact root**.
Adapt those paths before use. Inspect configuration paths too. The experimental
native-memory descriptor reader handles only simple descriptors without
disconnect bits; it is not a general banked-memory implementation.

## Original machine's emulator and RoMM setup

RetroArch was already available through RetroDECK, despite not appearing in
`command -v retroarch`. Version: **1.22.2**, Git `69a4f0e`.
Gauntlet's `find_installs()` discovered it.

```text
Launch prefix:
flatpak run --command=/app/retrodeck/components/retroarch/bin/retroarch net.retrodeck.retrodeck

Host core directory:
/home/r/.local/share/flatpak/app/net.retrodeck.retrodeck/current/active/files/retrodeck/components/retroarch/rd_extras/cores

Sandbox core directory:
/app/retrodeck/components/retroarch/rd_extras/cores
```

Private config/save directories and explicit Flatpak filesystem access isolated
the research from the user's emulator configuration. OpenGL video worked; null
video exited silently. No PSX BIOS was found in the inspected RetroDECK BIOS
directory. SwanStation did not answer on its isolated probe port, but PCSX
ReARMed successfully loaded the owned discs and provided mapped reads.
Do not assume the destination has the same cores, BIOS or driver behavior.

RoMM on the original host:

```text
Base API: https://glados-box.tailca7638.ts.net:8443/api/
Existing token file: /home/r/.local/share/ultimate-emulation/romm.token
Related project: /home/r/workspace/ultimate-emulation
Inventory: GET roms?limit=1000&offset=0&with_files=true
Owned-file download: roms/{file_id}/files/content/{URL-encoded filename}
```

The credential was read privately inside Python, never printed or committed.
The destination needs its own authorized token access and network/Tailscale
connectivity. Do not put the token in command arguments, documentation or logs.
Validate downloaded size and SHA-1 against RoMM. Inventory held 858 owned ROMs.

## Recent observations and factual corrections

- **Resident Evil PSX, RoMM 692:** owned USA CHD, SHA-1
  `5001af9464e1d372571cf108a45b665ac355ef38`. PCSX ReARMed returned mapped
  `READ_CORE_MEMORY`; source player/enemy HP were zero at boot.
  Source game-state zero is not initialization-safe proof of gameplay.
- **Resident Evil 2 PSX, RoMM 693:** owned Dual Shock USA Disc 1 CHD, SHA-1
  `e76d8440170e456bccd676004991e5aa6fabdfe7`. Source primary pointer at
  `0x1FFFFC` returned `0x800784B0`, matching Leon disc; boot HP zero.
- **Luigi's Mansion, RoMM 739:** US RVZ, SHA-1
  `9a1058058d8468e297916b208730135e4c951a14`. Dolphin `READ_CORE_RAM`
  returned exact MEM1 US identity `GLME01`, US mode 0 (Nintendo logo) and map 0.
  This establishes real readable MEM1, not a boss victory.
- **Super Mario Bros. RA ID is 1446**, not 1488 (DuckTales) or 2.
  Source world is zero-based, lives-minus-one, and internal level counter also
  counts underground transitions. World-finished state is not every flagpole.
- **Sonic 2 Super-state is `0xF65E`**, not the transposed `0xFE65`.
- **Mortal Kombat II SNES RA ID is 647**. Primary finisher type/accomplishment,
  boss IDs, round counters and Shao Kahn defeat-screen candidates were added.
  They are not new live-verified finisher detectors.
- **Kirby:** source explicitly identifies Whispy `0x0531` bit7 and Kracko
  `0x0534` bit7. Fire ability is 0; absent ability is `0xFF`.
- **Chrono Trigger:** optional literal Magus kill is `0x10138` bit1.
  Castle-fight story advancement is not Magus's death. Black Omen progress is
  not a certified Lavos victory.
- **GoldenEye:** source mission ID/difficulty/screen/clear/objective addresses
  were added, rather than claiming multiplayer observations validate missions.
- Preliminary maps were corrected for ALttP sword (`0xF359`, not `0xF3C5`),
  FF6 field versus battle HP, SMB world-exit behavior and Doom SNES source
  availability. More preliminary prose may still merit review.

Invalid/ambiguous proposals remain documented, not silently replaced:
MM2 Yellow Devil/Magnet Beam belong to MM1; FF6 first boss is Whelk; Frigate
does not have an Ourumov boss; standard Tekken 3 has no Kazuya matchup;
GX Death Race appears to mean F-Zero X; Elvis is an ally; Paper Mario prologue
Bowser is unwinnable; Doom I ports do not establish a Doom II Icon of Sin goal.

## Address and detection constraints

Refer to the audit's address-contract table before creating presets.

- N64 RA host-order offsets: u8 XOR 3, u16 XOR 2, aligned u32 unchanged;
  then Gauntlet `swap32`, big-endian. Never double-convert.
- mGBA RA offsets below `0x8000` map to `0x03000000+a` IWRAM; higher offsets
  through `0x47FFF` map to `0x02000000+a-0x8000` EWRAM.
  Zero Mission's initial direct-pointer low-offset reads were wrong; native UDP
  confirmed `0x03000C70` mode 1 while low `0x0C70` returned 0.
- Gambatte native bus addresses are not raw system-RAM-pointer indexes.
- Snes9x fallback exposes WRAM, not all RA SRAM/Super FX/SA-1 domains.
- Genesis swap assumptions were not live-tested; Neo Geo has driver-specific
  mapping and must not inherit Genesis layout by CPU family.
- Dolphin MEM1 is big-endian; Luigi unlabelled primary notes are **EU**, so
  do not paste EU boss flags into the tested US ROM.
- Gauntlet already supports nested pointer metrics. It does not natively decode
  float HP/coordinates, BCD or popcount as general metric semantics.
- Every victory requires context, initialization, baseline transition and
  death/abort/reload exclusions. A boot zero or empty actor slot is not victory.
  Frame-transient signals can be missed by the normal 0.5-second UDP poll.

## What remains, in priority order

1. **Securely transfer the uncommitted documentation and optional evidence.**
   Confirm the destination has all four docs before treating the branch as resumed.
2. **Incorporate the last source-review findings** not yet edited into the audit:
   MGS snowfield Sniper Wolf has US v1.1 pointer `0x0B7E78`, source health/hit
   counter at +`0x6D8`; source animation `0x16FA76` u16 is `0x0A0B` hit/dead
   versus `0x090B` hit/not dead (US v1.0/v1.1). Width of the health/hit field is
   unspecified and must remain tentative. Guard encounter/actor and actual
   post-fight success; current audit has only a generic Wolf lead.
3. **Add precise SM64 cap/key semantics from the last decomp check:**
   `src/game/save_file.h` has a `SaveFile` u32 flags field after its first eight
   bytes; Wing Cap switch mask `0x2`, key 1 `0x10`, key 2 `0x20`, basement door
   unlocked `0x40`, upstairs door `0x80`. The correct runtime save-buffer
   address/current-file selection is not yet resolved; do not invent it.
   Source Mario X coordinate `0x33B1AC` is float; roof Y/region still needs a
   pinned runtime mapping and calibrated boundaries.
4. **Finish factual review of preliminary community maps.** Keep direct
   corrections or superseded warnings explicit. The newer audit takes precedence;
   do not resurrect historical guessed IDs or broad HP-zero finish predicates.
   One specific unresolved review point: NES Tetris `0x0050` is described as BCD
   in the audit; RA 2022 labels it u16 lines but does not specify encoding.
   Check a disassembly/live counter before relying on BCD thresholds.
5. **Rerun final validation after any edits.** Prior validation succeeded:
   exactly 52 headings in original order, four original goals per game (208),
   61 referenced nonempty primary JSON sets, existing local Markdown targets,
   and `git diff --check`. Scope the goal count to the numbered game sections:
   suggested-first-picks later in the ideas file would otherwise overcount.
   Documentation-only changes do not need application tests.
6. **Inspect final diff/status and secret/binary exclusion.** Ensure only intended
   documentation changes are transferred/persisted. No credential or ROM has been
   added to git. No current-request todos exist in the session database.
7. **Finish with an honest summary.** All entries researched does not mean all
   goals verified. Report real probes, version/transport limits and remaining
   encounter-state certification. No production preset implementation was requested.

Additional emulator work is optional, not a prerequisite to claiming research
coverage. If extending it, prefer bounded real gameplay traces on owned ROMs over
more boot samples. Natural success AND failure/reload observations from intended
start states are required before labeling a new challenge verified.

## Process state and safe resumption

At the latest check, **no research RetroArch, downloader or direct-core helper
process remained running**. Probe subprocess wrappers sometimes exited while
Flatpak child emulators continued running; those specific owned PIDs were cleaned
up. Check the destination's processes after each probe, and terminate only the
specific processes started for this work, never by process-name killing.

Earlier background research agents are unavailable after interruption. Do not
restart them for the same broad objectives or wait on their old IDs. Continue
directly from the audit and cached primary notes. The original research task has
not been marked complete; this handoff pauses it at final-review stage.
