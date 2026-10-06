# New game and challenge ideas (v2, for review)

Revised after feedback:
- **Race first.** Everyone plays at once from the same start state; first to the goal wins. Turns and score-attack are
  avoided. Versus is only used for fighters and similar games that are head to head by nature.
- **All emulatable consoles are in scope** (NES, SNES, Genesis, Game Boy/GBC/GBA, N64, PSX, Saturn, Dreamcast, PS2,
  GameCube, arcade, and so on).
- **Length mix (a spread, not a rule).** Nothing in the code enforces length. We just want a healthy spread across the pool
  so a random playlist is unlikely to be several long matches in a row. Tiers:
  **[XS]** 15-30 s (grab an item, hit a flag), **[S]** 1-4 min (a short level, a small boss, a race to an item),
  **[L]** 5+ min (a long dungeon or big boss). Iconic moments can be any tier, a quick iconic one is great.
  Target pool shape: about 20% XS, 55-60% S, 20-25% L. Keep L rare; no game should be mostly L.
- **Iconic moments, not scores.** Each challenge is one recognizable thing from gaming history, like "beat Grey Fox"
  (already in the list). Win condition is nearly always a boss HP = 0, a flag, an item, or a level-complete flag.

Tags: **R** = race (same start state, first to finish), **V** = versus (head to head), **R*** = race where the start
state is a save made just before the moment. Win-condition ideas are in *italics*; none of the RAM is researched yet.

## Format
Each game has 3-4 moments. Most are "be first to do the famous thing".

---

## Boss fights and showdowns

### Metal Gear Solid (PSX) - already on the list
1. **Beat Grey Fox** (R*): the cyborg ninja fight. *boss HP = 0*
2. **Beat Psycho Mantis** (R*): swap controller ports to dodge his reads. *boss HP = 0*
3. **Beat Sniper Wolf** (R*): the snowfield sniper duel. *boss HP = 0*
4. **Beat Metal Gear REX** (R*): the tank-vs-Snake finale with Stingers. *boss HP = 0*

### Final Fantasy VII (PSX) - already on the list
1. **Beat Sephiroth** (R*): the final boss. *boss HP = 0*
2. **Beat Midgar Zolom** (R*): the swamp snake. *enemy HP = 0*
3. **Beat Ruby Weapon** (R*): the optional superboss. *boss HP = 0*
4. **Win the Chocobo race** (R*): the Gold Saucer race. *race complete flag*

### Mega Man 2 / 3 (NES)
1. **Beat Wily's Dragon** (R*). *boss HP = 0*
2. **Beat the Yellow Devil** (R*): the "pattern" fight in Mega Man 1. *boss HP = 0*
3. **Defeat all Robot Masters in Mega Man 2 stage 1** (R*): first to Metal Man down. *boss HP = 0*
4. **Get the Magnet Beam** (R*): no Mega Man game is complete without it. *item flag*

### Castlevania: Symphony of the Night (PSX)
1. **Beat Richter Belmont** (R*): the first big fight. *boss HP = 0*
2. **Beat Death** (R*): the scythe fight. *boss HP = 0*
3. **Get the Soul of Bat relic** (R*): the first relic. *item flag*
4. **Reach the Inverted Castle** (R*): the famous second-half reveal. *map flag*

### Super Metroid (SNES)
1. **Beat Ridley** (R*). *boss HP = 0*
2. **Escape Zebes** (R*): the countdown run. *escape flag / room id*
3. **Beat Kraid** (R*). *boss HP = 0*
4. **Get the Morph Ball** (R*): the first upgrade. *item flag*

### Zelda: Ocarina of Time (N64)
1. **Beat Ganon** (R*). *boss HP = 0*
2. **Pull the Master Sword** (R*): start as a kid. *item/age flag*
3. **Beat Gohma** (R*): the first dungeon boss. *boss HP = 0*
4. **Win Epona** (R*): get the horse by winning the Lon Lon Ranch race. *item flag*

### Zelda: A Link to the Past (SNES)
1. **Beat Agahnim** (R*): bounce his spell back. *boss HP = 0*
2. **Get the Master Sword** (R*): the Lost Woods pedestal. *item flag*
3. **Beat Ganon** (R*). *boss HP = 0*
4. **Cross to the Dark World** (R*): the first warp. *world flag*

### Pokemon Red/Blue (GB)
1. **Beat Brock** (R*). *badge flag*
2. **Catch Pikachu** (R*): get it from Viridian Forest. *party flag*
3. **Beat the Elite Four's Lance** (R*). *trainer defeated flag*
4. **Stop MissingNo.** (R*): pull off the Cinnabar glitch. *item/party flag*

### Final Fantasy VI (SNES)
1. **Beat Ultros at the opera** (R*): the opera scene with Celes. *flag*
2. **Beat Kefka** (R*). *boss HP = 0*
3. **Survive the World of Ruin start** (R*): the airship crash. *flag*
4. **Win the Magitek Armor fight** (R*): the very first boss. *flag*

### Chrono Trigger (SNES)
1. **Beat Lavos** (R*). *boss HP = 0*
2. **Kill Magus** (R*). *boss HP = 0*
3. **Pull Marle's pendant out of time** (R*): the Leene Square scene. *event flag*
4. **Escape Truce Canyon** (R*): a quick intro dungeon. *event flag*

---

## Famous firsts and "gaming history" moments

### Super Mario Bros. (NES)
1. **Find the Warp Zone in 1-2** (R): the famous pipes to World 4. *world counter = 4*
2. **Beat Bowser by skipping the axe fight** (R*): run past him with fire. *world clear flag*
3. **Beat 8-4 without the Fire Flower** (R*). *world clear flag*
4. **Get 1-Up from the 3-1 stairs** (R*): the infinite-lives staircase. *lives >= 5*

### Super Mario 64 (N64) - already in `gauntlet_data/m64.json`
1. **Get the Bowser key** (R*): the first key. *key flag*
2. **Get the Wing Cap** (R*): the red switch. *cap flag*
3. **Beat Bowser (World 1)** (R*). *boss HP = 0*
4. **Reach the roof of the castle** (R*): the Yoshi easter egg. *room id*

### Sonic the Hedgehog 2 (Genesis)
1. **Get all Chaos Emeralds in the first special stage** (R*): first to a 7-ring emerald. *emerald count*
2. **Beat Dr. Robotnik in Emerald Hill** (R*). *boss HP = 0*
3. **Become Super Sonic** (R*): collect the emeralds and hit 50 rings. *Super flag*
4. **Escape the Death Egg** (R*). *final boss flag*

### Doom bosses (PSX / SNES / GBA / PC ports)
1. **Beat the Cyberdemon** (R*): E2M8 / E1M8 style big fight. *boss HP = 0*
2. **Beat the Spider Mastermind** (R*): E3M8, the end of Inferno. *boss HP = 0*
3. **Beat the Barons of Hell** (R*): E1M8 Hell Barons. *boss kill count*
4. **Kill the Icon of Sin** (R*): Doom II MAP30 (rocket into the boss's head). *boss HP = 0*

### Doom (PSX / SNES / GBA) quick races
1. **Find the secret level (E1M9)** [XS] (R*). *level id*
2. **Pick up the shotgun** [XS] (R): first weapon grab on E1M1. *weapon flag*
3. **Escape E1M1** [XS] (R): the first level. *level complete flag*
4. **Pick up the BFG** [XS] (R*): the famous weapon. *weapon flag*

### GoldenEye 007 (N64)
1. **Bungee jump off the Dam** (R*): the opening jump. *level progress flag*
2. **Beat Facility** (R*). *level complete flag*
3. **Beat Ourumov in the Frigate** (R*). *objective flag*
4. **Beat Trevelyan** (R*): the Cradle finale. *boss HP = 0*

### Resident Evil 2 (PSX / N64)
1. **Beat Tyrant** (R*). *boss HP = 0*
2. **Beat the first Licker** (R*). *enemy HP = 0*
3. **Reach the Raccoon Police Station** (R*). *room id*
4. **Beat the G Virus Birkin** (R*). *boss HP = 0*

---

## Fighters (versus is the natural mode)

### Street Fighter II: Turbo (SNES) - already on the list
1. **Beat Ryu with Ken** (V): the mirror of the story fight. *rounds won*
2. **Hadouken to win** (V): win a round with a fireball. *KO flag*
3. **Beat M. Bison** (R*): first to the final boss and beat him. *boss HP = 0*
4. **Win a round with a perfect** (V). *HP at round end*

### Mortal Kombat II (arcade / SNES) - already in `gauntlet_data/mk2.json`
1. **Fatality** (V): first to land a Fatality. *finisher flag*
2. **Beat Shao Kahn** (R*). *boss HP = 0*
3. **Find Smoke** (R*): the Living Forest hidden fighter. *flag*
4. **Beat Kintaro** (R*). *boss HP = 0*

### Tekken 3 (PSX)
1. **Beat Ogre** (R*). *boss HP = 0*
2. **Win with Eddy Gordo** (V). *rounds won*
3. **Jin vs. Kazuya** (V): the father-son fight. *rounds won*
4. **Beat Tekken Force mode stage 1** (R*). *stage clear flag*

### Super Smash Bros. (N64) - already on the list
1. **KO with a Home-Run Bat** (V): the one-hit KO item. *KO flag*
2. **Beat Master Hand** (R*). *boss HP = 0*
3. **Win as Kirby** (V). *stocks*
4. **Ring-out the opponent** (V): first KO. *stock change*

---

## Racing moments

### Mario Kart 64 (N64) - already on the list
1. **Beat Rainbow Road** (R): first to finish. *race complete flag*
2. **Hit with a Blue Shell** (R): get a Blue Shell hit while first. *item flag*
3. **Cross the Wario Stadium finish first** (R). *race complete flag*
4. **Take the Wario Stadium shortcut** (R): the famous Wario Stadium cut. *lap/position flag*

### F-Zero GX (GameCube) - already on the list
1. **Win Mute City** (R). *race complete flag*
2. **Beat the Big Blue boss lap** (R). *race complete flag*
3. **Boost off Death-Race** (R): the long race. *race complete flag*
4. **Win Cosmo Terminal** (R). *race complete flag*

### Crash Team Racing (PSX)
1. **Beat Oxide** (R*). *race complete flag*
2. **Get the Gem Cup** (R*). *cup flag*
3. **Win Crash Cove** (R). *race complete flag*
4. **Beat Ripper Roo** (R*). *boss race flag*

---

## Platformers and puzzles that are naturally races

### Dr. Mario / Tetris (NES / SNES / GB)
1. **Clear 25 lines** (R): first to 25. *lines >= 25*
2. **Clear all viruses** (R): first to clear. *virus count = 0*
3. **Double Tetris** (R): first to clear four lines twice. *tetris counter = 2*
4. **Reach level 10** (R). *level >= 10*

### Pac-Man (arcade / NES)
1. **Eat the first Ghost** (R). *ghost flag*
2. **Eat the first fruit** (R). *fruit flag*
3. **Clear the first maze** (R). *dots = 0*
4. **Eat Blinky at the first power pill** (R). *ghost flag*

### Donkey Kong (arcade / NES)
1. **Reach the 25m Girder** (R). *level flag*
2. **Reach the Hammer** (R): the first hammer. *item flag*
3. **Climb to Pauline** (R): finish the first stage. *level complete flag*
4. **Win the rivets** (R). *stage flag*

---

## Heavier consoles: PS2, Dreamcast, Saturn (for an i7 + RTX 2060)
Opinion, not benchmarked. Racing means one RetroArch window per player, so 4 players = 4 emulators at once. The 2060 is a
solid GPU for this. The CPU is the real limit, and an older i7 has few strong cores, so I'd treat this as the cap:
- **NES to PS1, GB/GBA, Genesis, SNES, N64 (4 windows):** fine. N64 at 4 windows is OK at native resolution.
- **Dreamcast (Flycast), 2-3 windows:** fine, at native resolution. 4 may work; test it.
- **Saturn (Kronos or Yabause), 2 windows:** fine. 3-4 is doubtful on an older i7. Beetle Saturn is too heavy for a race here.
- **PS2, 1 window only:** even one PS2 instance takes most of that CPU, so don't race it. Use **turns**, one quick challenge each.
- **GameCube/Wii (Dolphin):** 2 windows at most. Treat like PS2 for 3-4 players.
- **Plan:** set a per-game race window cap, with turns as the fallback, and run a 4-window test on the real machine before
  committing to any game here. Lowering internal resolution and turning off shaders helps a lot.
- **PS2/DC/Saturn quick turns candidates:**
  - PS2: Devil May Cry 3, beat Cerberus [S]. Shadow of the Colossus, topple the first colossus [S]. God of War, kill the Hydra [S].
  - Dreamcast: Sonic Adventure, finish Emerald Coast [S]. Crazy Taxi, first fare to the drop-off [XS].
  - Saturn: Nights into Dreams, clear Spring Valley stage 1 [S]. Panzer Dragoon, beat the first boss [S].

## What to pick first
Best ratio of effort to fun: single boss fights from a save state are the easiest (HP = 0, we already do this
for Punch-Out and Mega Man).
1. **MGS: Beat Grey Fox** (already in the list)
2. **Super Mario Bros.: Warp Zone** (a flag, no save state needed)
3. **Super Metroid: Beat Ridley** (simple boss HP)
4. **Zelda: ALttP: Get the Master Sword** (an item flag)
5. **Tetris/Dr. Mario: Clear all viruses** (no save state)

## Decisions so far
- Mostly race; versus only for fighters; turns only for heavy consoles.
- Iconic moments mixed with quick races to items or level exits; no score-attack.
- Length is a distribution goal, not a coded rule: mostly [S], some [XS], rare [L].
- Save states for each boss fight: yes, will be made.
- Hardware is an i7 + RTX 2060: PS2 turns only, Saturn 2 windows, Dreamcast 2-3, everything lighter 4.
- Doom bosses: added a dedicated list.

## Next step (if you agree)
Tag every challenge with [XS]/[S]/[L], add quick items or level-exits to the boss-heavy games, and trim the pool to the
target mix. Most boss fights below are currently [S] or [L].
