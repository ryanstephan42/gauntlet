# New game and challenge ideas (v3, for review)

52 games, 4 challenges each. Section E games are listed as added; the old Super Mario World, Punch-Out, Banjo-Kazooie, Star Fox 64, Crash Bandicoot and Pokemon Emerald entries were removed because they already exist in the repo. Use it as a pool to pick priorities from.

## Ground rules (from review)
- **Mostly race.** Everyone plays at once from the same start state; first to the goal wins. **V** (versus) only for fighters
  and similar. **T** (turns) only for consoles too heavy to run several windows (see "Heavier consoles").
- **Iconic moments over scores.** Win conditions are boss HP = 0, a flag, an item or a level exit. No score attack.
- **Length is a spread, not a coded rule.** Tiers: **XS** 15-30 s, **S** 1-4 min, **L** 5+ min. Target pool is about
  20% XS, 55-60% S, 20-25% L, so a random playlist rarely has several long matches in a row. Iconic moments can be any tier.
- **Save states:** each `*` needs one (a state just before the moment). No `*` means the title screen or a RAM write is enough.
- All emulatable consoles are in scope. Hardware is an i7 + RTX 2060, so heavy consoles are capped (see below).

Format: `Name [tier] (mode)`: what happens. *Likely win condition.* RAM addresses are not researched yet.
Games already in `games+challenges.txt` or `gauntlet_data/` are marked (existing).

---

## Build priority (by system)
Priority follows which systems have verified RAM reads. Within a tier, pick by the "first picks" list below.
1. **Tier 1: NES, SNES, N64** (RAM reads proven). Build here first.
   - NES: Mega Man 2, Super Mario Bros., Super Mario Bros. 3, Kirby's Adventure, Contra, Castlevania, Ninja Gaiden, Pac-Man, Donkey Kong, Dr. Mario/Tetris, Punch-Out (existing).
   - SNES: Super Metroid, ALttP, FF6, Chrono Trigger, Super Mario World (existing), Yoshi's Island, DKC, Mega Man X, Super Mario RPG, SF2 (existing).
   - N64: Ocarina of Time, Majora's Mask, Super Mario 64 (existing), GoldenEye, Perfect Dark, Mario Kart 64 (existing), Smash 64 (existing), Paper Mario.
2. **Tier 2: PSX and GameCube** (very cool, RAM maps need verifying). PSX: MGS, FF7, SotN, RE/RE2, Doom, Tekken 3, CTR, Tony Hawk 2.
   GameCube: F-Zero GX, Luigi's Mansion, Resident Evil (GC). GameCube is capped at 2 race windows (see below).
3. **Tier 3: everything else** (RAM not yet checked, mostly lighter cores). GB/GBA, Genesis, Neo Geo, TurboGrafx-16, arcade. PS2 is last (turns only).

---

## A. Boss fights and showdowns

### 1. Metal Gear Solid (PSX) (existing)
1. **Beat Grey Fox** [S] (R*): the cyborg ninja fight. *boss HP = 0*
2. **Beat Psycho Mantis** [S] (R*): swap controller ports to dodge his reads. *boss HP = 0*
3. **Beat Sniper Wolf** [S] (R*): the snowfield duel. *boss HP = 0*
4. **Get the Card Key** [XS] (R*): first to the Level 1 card from the elevator. *item flag*

### 2. Final Fantasy VII (PSX) (existing)
1. **Beat Sephiroth** [L] (R*): the final boss. *boss HP = 0*
2. **Beat the Guard Scorpion** [S] (R*): the first boss. *boss HP = 0*
3. **Win the Chocobo race** [S] (R*): the Gold Saucer race. *race complete flag*
4. **Open the Mako Reactor door** [XS] (R*): first to the first reactor's exit. *event flag*

### 3. Mega Man 2 (NES) (existing)
1. **Beat Metal Man** [S] (R*): the classic first pick. *boss HP = 0*
2. **Beat the Wily Dragon** [S] (R*). *boss HP = 0*
3. **Beat the Yellow Devil (Mega Man 1)** [S] (R*): the pattern fight. *boss HP = 0*
4. **Get the Magnet Beam** [XS] (R*): the famous item. *item flag*

### 4. Castlevania: Symphony of the Night (PSX)
1. **Beat Richter Belmont** [S] (R*). *boss HP = 0*
2. **Beat Death** [S] (R*): the scythe fight. *boss HP = 0*
3. **Get the Soul of Bat** [S] (R*): the first relic. *item flag*
4. **Enter the Inverted Castle** [L] (R*): the famous second-half reveal. *map flag*

### 5. Super Metroid (SNES)
1. **Beat Kraid** [S] (R*). *boss HP = 0*
2. **Beat Ridley** [S] (R*). *boss HP = 0*
3. **Get the Morph Ball** [XS] (R*): the first upgrade. *item flag*
4. **Escape Zebes** [L] (R*): the countdown run. *room id*

### 6. Zelda: Ocarina of Time (N64)
1. **Beat Gohma** [S] (R*): the first dungeon boss. *boss HP = 0*
2. **Pull the Master Sword** [XS] (R*). *item/age flag*
3. **Win Epona** [S] (R*): the Lon Lon Ranch race. *item flag*
4. **Beat Ganon** [L] (R*). *boss HP = 0*

### 7. Zelda: A Link to the Past (SNES)
1. **Beat Agahnim** [S] (R*): bounce his spell back. *boss HP = 0*
2. **Get the Master Sword** [S] (R*): the Lost Woods pedestal. *item flag*
3. **Cross to the Dark World** [XS] (R*): the first warp. *world flag*
4. **Beat Ganon** [L] (R*). *boss HP = 0*

### 8. Pokemon Red/Blue (GB)
1. **Beat Brock** [S] (R*). *badge flag*
2. **Catch a Pikachu** [S] (R*): Viridian Forest. *party flag*
3. **Pick a starter** [XS] (R*): first to leave the lab with one. *party flag*
4. **Beat Lance** [L] (R*). *trainer defeated flag*

### 9. Final Fantasy VI (SNES)
1. **Beat the Magitek Armor** [S] (R*): the first boss. *flag*
2. **Beat Ultros at the opera** [S] (R*): the opera scene. *flag*
3. **Survive the airship crash** [XS] (R*): the World of Ruin start. *flag*
4. **Beat Kefka** [L] (R*). *boss HP = 0*

### 10. Chrono Trigger (SNES)
1. **Escape Truce Canyon** [S] (R*): a quick intro dungeon. *event flag*
2. **Pull Marle's pendant out of time** [XS] (R*): the Leene Square scene. *event flag*
3. **Kill Magus** [S] (R*). *boss HP = 0*
4. **Beat Lavos** [L] (R*). *boss HP = 0*

### 11. Doom bosses (PSX / SNES / GBA)
1. **Beat the Barons of Hell** [S] (R*): E1M8. *boss kill count*
2. **Beat the Cyberdemon** [S] (R*). *boss HP = 0*
3. **Beat the Spider Mastermind** [S] (R*): E3M8. *boss HP = 0*
4. **Kill the Icon of Sin** [S] (R*): Doom II MAP30. *boss HP = 0*

### 12. Doom quick races (PSX / SNES / GBA)
1. **Pick up the shotgun** [XS] (R): first weapon grab on E1M1. *weapon flag*
2. **Escape E1M1** [S] (R). *level complete flag*
3. **Find the secret level (E1M9)** [S] (R*). *level id*
4. **Pick up the BFG** [XS] (R*): the famous weapon. *weapon flag*

### 13. Resident Evil 2 (PSX / N64)
1. **Get the Police Station key** [XS] (R*). *item flag*
2. **Beat the first Licker** [S] (R*). *enemy HP = 0*
3. **Beat G Birkin** [S] (R*). *boss HP = 0*
4. **Beat the Tyrant** [L] (R*). *boss HP = 0*

### 14. GoldenEye 007 (N64)
1. **Bungee jump off the Dam** [XS] (R): the opening jump. *level progress flag*
2. **Beat Facility** [S] (R). *level complete flag*
3. **Beat Ourumov in the Frigate** [S] (R*). *objective flag*
4. **Beat Trevelyan** [L] (R*): the Cradle finale. *boss HP = 0*

---

## B. Famous firsts and gaming-history moments

### 15. Super Mario Bros. (NES)
1. **Find the Warp Zone in 1-2** [XS] (R): the famous pipes to World 4. *world counter = 4*
2. **Beat 1-1** [XS] (R). *level complete flag*
3. **Get the 1-Up on the 3-1 stairs** [S] (R*): the infinite-lives staircase. *lives >= 5*
4. **Beat Bowser in World 1** [S] (R*): run past him with fire. *world clear flag*

### 16. Super Mario 64 (N64) (existing)
1. **Get the Wing Cap** [S] (R*): the red switch. *cap flag*
2. **Get the Bowser key** [S] (R*): the first key. *key flag*
3. **Reach the castle roof** [XS] (R): the Yoshi easter egg. *room id*
4. **Beat Bowser (World 1)** [S] (R*). *boss HP = 0*

### 17. Sonic the Hedgehog 2 (Genesis)
1. **Beat Emerald Hill Act 1** [XS] (R). *act clear flag*
2. **Beat Dr. Robotnik in Emerald Hill** [S] (R*). *boss HP = 0*
3. **Get the first Chaos Emerald** [S] (R*): the special stage. *emerald count*
4. **Become Super Sonic** [L] (R*): emeralds plus 50 rings. *Super flag*

### 18. Pac-Man (arcade / NES)
1. **Eat a Ghost** [XS] (R): first to eat one on a power pill. *ghost flag*
2. **Eat the first fruit** [XS] (R). *fruit flag*
3. **Clear the first maze** [S] (R). *dots = 0*
4. **Clear the first three mazes** [S] (R). *level >= 4*

### 19. Donkey Kong (arcade / NES)
1. **Grab the first hammer** [XS] (R). *item flag*
2. **Reach the 25m girder** [XS] (R). *level flag*
3. **Climb to Pauline** [S] (R): finish the first stage. *level complete flag*
4. **Win the rivets** [S] (R). *stage flag*

### 20. Dr. Mario / Tetris (NES / SNES / GB)
1. **Clear 10 lines** [XS] (R). *lines >= 10*
2. **Clear all viruses** [S] (R). *virus count = 0*
3. **Reach level 10** [S] (R). *level >= 10*
4. **Clear 25 lines** [S] (R). *lines >= 25*

---

## C. Fighters (versus is the natural mode)

### 21. Street Fighter II: Turbo (SNES) (existing)
1. **First Hadouken** [XS] (V): land the first fireball. *hit flag*
2. **Win a round** [S] (V). *rounds won*
3. **Perfect round** [S] (V): win with full HP. *HP at round end*
4. **Beat M. Bison** [S] (R*): first to the final boss and beat him. *boss HP = 0*

### 22. Mortal Kombat II (arcade / SNES) (existing)
1. **First Fatality** [S] (V). *finisher flag*
2. **Find Smoke** [S] (R*): the Living Forest hidden fighter. *flag*
3. **Beat Kintaro** [S] (R*). *boss HP = 0*
4. **Beat Shao Kahn** [L] (R*). *boss HP = 0*

### 23. Tekken 3 (PSX) (existing)
1. **Win a round with Eddy Gordo** [S] (V). *rounds won*
2. **Jin vs. Kazuya** [S] (V): the father-son fight. *rounds won*
3. **Beat Tekken Force stage 1** [S] (R*). *stage clear flag*
4. **Beat Ogre** [L] (R*). *boss HP = 0*

### 24. Super Smash Bros. (N64) (existing)
1. **First KO** [XS] (V). *stock change*
2. **KO with the Home-Run Bat** [S] (V): the one-hit item. *KO flag*
3. **Win a 2-stock match as Kirby** [S] (V). *stocks*
4. **Beat Master Hand** [S] (R*). *boss HP = 0*

---

## D. Racing

### 25. Mario Kart 64 (N64) (existing)
1. **Hit someone with a Blue Shell** [XS] (R): while in first. *item flag*
2. **Take the Wario Stadium shortcut** [S] (R). *lap/position flag*
3. **Win Luigi Raceway** [S] (R). *race complete flag*
4. **Win Rainbow Road** [L] (R). *race complete flag*

### 26. F-Zero GX (GameCube) (existing)
1. **Win Mute City** [S] (R). *race complete flag*
2. **Win Cosmo Terminal** [S] (R). *race complete flag*
3. **Win Big Blue** [S] (R). *race complete flag*
4. **Win Death-Race** [L] (R): the long race. *race complete flag*

### 27. Crash Team Racing (PSX)
1. **Win Crash Cove** [S] (R). *race complete flag*
2. **Beat Ripper Roo** [S] (R*). *boss race flag*
3. **Grab the first Wumpa boost** [XS] (R). *boost flag*
4. **Beat Oxide** [L] (R*). *race complete flag*

---

## E. New games (the 25 added this round)

### 28. Metal Slug (Neo Geo)
1. **Rescue the first POW** [XS] (R). *POW count*
2. **Beat Mission 1** [S] (R). *mission clear flag*
3. **Pick up the Heavy Machine Gun** [XS] (R). *weapon flag*
4. **Beat the Mission 1 boss** [S] (R*). *boss HP = 0*

### 29. Super Mario Bros. 3 (NES)
1. **Get the Raccoon Leaf** [XS] (R). *power-up state*
2. **Beat 1-1** [XS] (R). *level complete flag*
3. **Beat the World 1 airship** [S] (R*). *world clear flag*
4. **Beat Bowser** [L] (R*). *world clear flag*

### 30. Kirby's Adventure (NES)
1. **Copy Fire** [XS] (R). *ability id*
2. **Beat Whispy Woods** [S] (R*). *boss HP = 0*
3. **Beat Kracko** [S] (R*). *boss HP = 0*
4. **Beat Nightmare** [L] (R*). *boss HP = 0*

### 31. Donkey Kong Country (SNES)
1. **Collect the K-O-N-G letters** [S] (R*). *letter flags*
2. **Beat Jungle Hijinxs** [S] (R). *level complete flag*
3. **Beat Very Gnawty** [S] (R*). *boss HP = 0*
4. **Find a Bonus Barrel** [XS] (R*). *bonus flag*

### 32. Contra (NES)
1. **Pick up the Spread Gun** [XS] (R). *weapon id*
2. **Beat Level 1** [S] (R). *level counter*
3. **Beat the Level 1 boss** [S] (R*). *boss HP = 0*
4. **Beat Java (Level 3 boss)** [S] (R*). *boss HP = 0*

### 33. Samurai Shodown II (Neo Geo)
1. **First hit** [XS] (V). *hit flag*
2. **Win a round** [S] (V). *rounds won*
3. **Perfect round** [S] (V). *HP at round end*
4. **Beat Kuroko** [S] (R*): the hidden referee fight. *boss HP = 0*

### 34. Castlevania (NES)
1. **Get the Whip upgrade** [XS] (R). *item flag*
2. **Beat the Giant Bat** [S] (R*). *boss HP = 0*
3. **Beat Medusa** [S] (R*). *boss HP = 0*
4. **Beat Dracula** [S] (R*). *boss HP = 0*

### 35. Mega Man X (SNES)
1. **Get the Dash upgrade** [XS] (R). *item flag*
2. **Beat Chill Penguin** [S] (R*). *boss HP = 0*
3. **Beat Sigma's first form** [S] (R*). *boss HP = 0*
4. **Get the Hadouken** [L] (R*): the hidden capsule. *item flag*

### 36. Zelda: Link's Awakening (GB)
1. **Get the sword** [XS] (R). *item flag*
2. **Beat Moldorm** [S] (R*). *boss HP = 0*
3. **Win the Trendy Game crane** [S] (R*). *item flag*
4. **Beat the Nightmare** [L] (R*). *boss HP = 0*

### 37. Zelda: Majora's Mask (N64)
1. **Get Deku Mask** [XS] (R). *item flag*
2. **Beat Odolwa** [S] (R*). *boss HP = 0*
3. **Beat Goht** [S] (R*). *boss HP = 0*
4. **Stop the Moon** [L] (R*). *boss HP = 0*

### 38. Yoshi's Island (SNES)
1. **Beat 1-1** [XS] (R). *level complete flag*
2. **Collect 20 stars to finish a level** [S] (R). *star counter*
3. **Beat Burt the Bashful** [S] (R*). *boss HP = 0*
4. **Beat Baby Bowser** [L] (R*). *boss HP = 0*

### 39. Bonk's Adventure (TurboGrafx-16)
1. **Beat Stage 1** [XS] (R). *stage clear flag*
2. **Beat the Stage 1 boss** [S] (R*). *boss HP = 0*
3. **Get the first Meat Power-up** [XS] (R). *power-up flag*
4. **Beat King Drool** [L] (R*). *boss HP = 0*

### 40. Perfect Dark (N64)
1. **Beat dataDyne Central** [S] (R). *level complete flag*
2. **Kill 5 Falcon 2 targets** [XS] (R). *kill count*
3. **Beat Carrington Institute** [S] (R). *level complete flag*
4. **Beat Elvis** [L] (R*). *boss HP = 0*

### 41. R-Type (TurboGrafx-16)
1. **Get the first Force pod** [XS] (R). *item flag*
2. **Beat Stage 1** [S] (R). *stage clear flag*
3. **Beat Dobkeratops** [S] (R*): the Stage 1 boss. *boss HP = 0*
4. **Beat Stage 3** [S] (R*). *stage clear flag*

### 42. Resident Evil (PSX / GameCube)
1. **Get the Mansion key** [XS] (R). *item flag*
2. **Beat the giant snake** [S] (R*). *boss HP = 0*
3. **Beat Tyrant** [S] (R*). *boss HP = 0*
4. **Escape the Mansion** [L] (R*). *ending flag*

### 43. Streets of Rage 2 (Genesis)
1. **Beat Stage 1** [S] (R). *stage clear flag*
2. **Beat the Stage 1 boss** [XS] (R*). *boss HP = 0*
3. **Beat Mr. X** [S] (R*). *boss HP = 0*
4. **Beat Shiva** [S] (R*). *boss HP = 0*

### 44. Gunstar Heroes (Genesis)
1. **Beat Seven Force** [S] (R*). *boss HP = 0*
2. **Beat the Dice Palace boss** [S] (R*). *boss HP = 0*
3. **Beat Stage 1** [XS] (R). *stage clear flag*
4. **Pick the Fire + Force weapon** [XS] (R). *weapon flag*

### 45. Paper Mario (N64)
1. **Beat Goomba Road** [XS] (R). *event flag*
2. **Beat Kent C. Koopa** [S] (R*). *boss HP = 0*
3. **Beat Bowser (first fight)** [S] (R*). *boss HP = 0*
4. **Beat Bowser at the end** [L] (R*). *boss HP = 0*

### 46. Metroid: Zero Mission (GBA)
1. **Get the Morph Ball** [XS] (R). *item flag*
2. **Beat Kraid** [S] (R*). *boss HP = 0*
3. **Beat Ridley** [S] (R*). *boss HP = 0*
4. **Escape Chozodia** [L] (R*). *flag*

### 47. Ninja Gaiden (NES)
1. **Beat Act 1-1** [XS] (R). *act clear flag*
2. **Beat Act 1 boss** [S] (R*). *boss HP = 0*
3. **Beat Act 3 boss** [S] (R*). *boss HP = 0*
4. **Beat Jaquio** [L] (R*). *boss HP = 0*

### 48. Earthworm Jim (Genesis / SNES)
1. **Beat New Junk City** [S] (R). *level complete flag*
2. **Beat Evil the Cat** [S] (R*). *boss HP = 0*
3. **Beat Psy-Crow** [S] (R*). *boss HP = 0*
4. **Get the Plasma Blaster** [XS] (R). *weapon flag*

### 49. Luigi's Mansion (GameCube)
1. **Catch the first Boo** [XS] (R). *event flag*
2. **Beat Neville** [S] (R*). *boss HP = 0*
3. **Beat Chauncey** [S] (R*). *boss HP = 0*
4. **Beat King Boo** [L] (R*). *boss HP = 0*

### 50. Super Mario RPG (SNES)
1. **Beat Mack** [S] (R*). *boss HP = 0*
2. **Beat Bowyer** [S] (R*). *boss HP = 0*
3. **Win the Mushroom Kingdom start** [XS] (R). *event flag*
4. **Beat Smithy** [L] (R*). *boss HP = 0*

### 51. Tony Hawk's Pro Skater 2 (PSX)
1. **Collect S-K-A-T-E** [S] (R*). *letter flags*
2. **Find the secret tape** [S] (R*). *item flag*
3. **Do the first gap** [XS] (R). *gap flag*
4. **Do a 900** [XS] (R*): the famous trick. *trick flag*

### 52. Devil May Cry 3 (PS2, turns only, Tier 3)
1. **Beat Cerberus** [S] (T*). *boss HP = 0*
2. **Beat Agni and Rudra** [S] (T*). *boss HP = 0*
3. **Pick up the first weapon** [XS] (T). *item flag*
4. **Beat Vergil (first duel)** [S] (T*). *boss HP = 0*

---

## Heavier consoles: PS2, Dreamcast, Saturn (for an i7 + RTX 2060)
Opinion, not benchmarked. Racing means one RetroArch window per player, so 4 players means 4 emulators at once. The GPU
is fine. The CPU is the limit, so:
- **NES to PS1, GB/GBA, Genesis, SNES, N64:** 4 windows, fine.
- **Dreamcast (Flycast):** 2-3 windows at native resolution. Test 4.
- **Saturn (Kronos or Yabause):** 2 windows. 3-4 is doubtful. Beetle Saturn is too heavy to race here.
- **PS2:** 1 window only, so use **turns** with one quick challenge each.
- **GameCube/Wii (Dolphin):** 2 windows at most. Treat 3-4 players like PS2.
- **Plan:** set a per-game race window cap with turns as the fallback, test 4 windows on the real PC before committing, and
  lower the internal resolution / skip shaders.
- **Quick turns candidates:** PS2 Shadow of the Colossus first colossus [S], God of War Hydra [S]; Dreamcast Sonic
  Adventure Emerald Coast [S], Crazy Taxi first fare [XS]; Saturn Nights Spring Valley 1 [S], Panzer Dragoon first boss [S].
  (Luigi's Mansion, F-Zero GX and Smash Melee are GameCube; the 2-window cap applies.)

## Suggested first picks
Easiest to build and fun right away:
1. **Super Mario Bros. Warp Zone** [XS] (a flag, no state)
2. **Doom: pick up the shotgun / escape E1M1** [XS-S] (simple flag)
3. **Super Metroid: Morph Ball and Ridley** [XS/S]
4. **MGS: Grey Fox** [S] (the one you asked for)
5. **Zelda ALttP: Master Sword** [S] (item flag)
6. **Mega Man 2: Magnet Beam / Metal Man** [XS/S]

## Decisions so far
- Mostly race; versus only for fighters; turns only for heavy consoles.
- Iconic moments mixed with quick race-to-item and level-exit challenges; no score attack.
- Length is a distribution goal, not a coded rule.
- Save states for each boss fight: yes.
- Hardware: i7 + RTX 2060.

## Open questions
- Which games from the 52 do you want to prioritize first? I can then do the RAM research for those.
- Any games you want swapped out, or any systems to add (Neo Geo, TurboGrafx, Game Boy Advance carts, Wii)?
