# New game and challenge ideas (for review)

Candidates to add alongside the games already in [`games+challenges.txt`](../games+challenges.txt) and
`gauntlet_data/` (SM64, MK2, Super Mario Kart, Super Bomberman, SF2, 3rd Strike, Galaga, Tetris, Punch-Out, Mario Kart 64,
Smash 64, GoldenEye, etc.).

## What makes a good Gauntlet game
- **Short rounds** (30 s – 3 min), so a match fits in a couch session.
- **One clear number in RAM** (score, lines, kills, laps, coins, HP) so the win check is a simple `reach` or `compare`.
- **Easy start**: a title-screen or early-level save state, or a RAM write that jumps to the right spot.
- **Works both ways**: turns (everyone plays the same challenge, best number wins), race (same start state, first to the
  goal wins), or versus (head to head).
- **Shop-friendly**: a value we can add to or subtract from for buffs and debuffs (lives, time, HP, coins).

Repeat challenges are fine. Each game below lists 4 challenges, and some are the same challenge in different forms.
Mode: **T** = turns, **R** = race (turns that run at the same time), **V** = versus. Likely RAM metric in italics.
RAM addresses are not researched yet. Anything marked ✔ is a straight reuse of an existing preset pattern.

---

## Arcade / puzzle (best fit: instant score metrics)

### 1. Dr. Mario (NES / SNES)
1. **Virus Clear Race** (R): first to clear all viruses on the same level. *viruses left = 0*
2. **Speed Level 15** (T): fewest seconds to clear a level 15 board. *virus count, timer*
3. **Versus Match** (V): win a 2P vs match. *wins counter*
4. **Combo King** (T): most viruses cleared in 60 s. *viruses cleared*

### 2. Tetris (Game Boy) / Tetris Attack
1. **Sprint 40** (R): first to 40 lines. *lines*
2. **Score Attack** (T): highest score in 3 minutes. *score*
3. **Versus** (V): survive the other player's garbage. *game over flag*
4. **Tetris!** (T): first to clear 4 lines at once. *lines cleared per drop*

### 3. Pac-Man (Arcade / NES)
1. **Dot Dash** (T): most dots in 90 s. *dots eaten*
2. **Ghost Hunter** (T): most ghosts eaten on one power pellet. *ghost chain*
3. **First Fruit** (R): first to reach and eat the first fruit. *fruit flag*
4. **Survivor** (T): longest before losing all lives. *frames alive / level*

### 4. Dig Dug (Arcade / NES)
1. **Clear the Round** (R): first to clear round 1. *enemies left = 0*
2. **Pump Master** (T): most enemies popped in 90 s. *kills*
3. **Rock Drop** (T): first rock-crush kill. *rock-kill flag*
4. **High Score** (T): top score in one life. *score*

### 5. Bubble Bobble (NES / Arcade)
1. **Stage Sprint** (R): first to finish stage 5. *stage number*
2. **Bubble Burst** (T): most enemies popped in 60 s. *kills*
3. **No-Damage Stage** (T): clear a stage without dying. *lives unchanged*
4. **2P Co-op Race** (V): who has more points after 3 stages. *score*

### 6. Street Fighter II: Turbo / Super / Alpha 2 (SNES / Arcade)
1. **First Blood** (V): first player to land a hit. *HP change*
2. **Best of 3** (V): win a match. *rounds won*
3. **Perfect** (V): win a round with full HP. *HP at round end*
4. **Mirror Match** (V): Ken vs Ken, normal win condition. *rounds won*

(Existing SF2 and 3rd Strike entries can share these.)

---

## NES / SNES / Genesis platformers and action

### 7. Super Mario Bros. (NES)
1. **World 1-1 Race** (R): first to touch the flagpole. *level complete flag*
2. **Coin Count** (T): most coins in 60 s. *coins*
3. **Score Attack** (T): highest score in 90 s. *score*
4. **Fire Flower Rush** (R): first to get Fire Mario. *power-up state*

### 8. Sonic the Hedgehog (Genesis)
1. **Green Hill Act 1 Race** (R): first to the signpost. *act clear flag*
2. **Ring Count** (T): most rings in 60 s. *rings*
3. **Speedrun** (T): fastest clear of Act 1. *timer*
4. **Spin Dash Boss** (R): first to beat the Zone 1 boss. *boss HP = 0*

### 9. Super Metroid (SNES)
1. **First Missile Pickup** (R): first to grab the missile tank from a start state. *missile max*
2. **Kill Count** (T): most enemies in 2 minutes in one room. *kills*
3. **Boss Rush** (R): first to beat Spore Spawn. *boss HP = 0*
4. **Energy Tank Hunt** (R): first to find an energy tank. *energy max*

### 10. Donkey Kong Country (SNES)
1. **Level Race** (R): first to finish Jungle Hijinxs. *level complete flag*
2. **Banana Count** (T): most bananas in 90 s. *bananas*
3. **KONG Letters** (R): first to get K-O-N-G. *letters flags*
4. **Boss Rush** (R): first to beat Very Gnawty. *boss HP = 0*

### 11. Contra (NES)
1. **Level 1 Clear** (R): first to the end of Level 1. *level counter*
2. **Boss Kill** (R): first to beat the Level 1 boss. *boss HP = 0*
3. **Lives Left** (T): most lives after a fixed stretch. *lives*
4. **Spread Gun Rush** (R): first to pick up the Spread Gun. *weapon id*

### 12. Kirby's Adventure / Kirby Super Star (NES / SNES)
1. **Level Race** (R): first to finish Vegetable Valley 1. *level complete flag*
2. **Copy Ability Rush** (R): first to get Fire. *ability id*
3. **Health Left** (T): most HP at the end of a stage. *HP*
4. **Gourmet Race** (V): Kirby Super Star race, first to the finish. *position*

---

## Fighters and brawlers (head to head)

### 13. Killer Instinct (SNES / Arcade)
1. **Best of 3** (V): win a match. *rounds won*
2. **First Combo** (V): first 5-hit combo. *combo counter*
3. **Ultra Finish** (V): win by Ultra. *finisher flag*
4. **Perfect** (V): win a round with full HP. *HP*

### 14. Teenage Mutant Ninja Turtles: Tournament Fighters (SNES / Genesis)
1. **Best of 3** (V). *rounds won*
2. **First KO** (V). *HP = 0*
3. **Perfect** (V). *HP*
4. **Low HP Comeback** (V): win after being under 10% HP. *HP*

### 15. Super Smash Bros. Melee (GameCube)
1. **Stock Match** (V): 3 stocks, last one standing. *stocks*
2. **KO Count** (V): most KOs in 2 minutes. *KOs*
3. **Damage Race** (V): most damage in 60 s. *damage dealt*
4. **Home-Run Contest** (T): farthest hit. *distance*

---

## Racing and sports

### 16. F-Zero (SNES)
1. **Mute City Lap** (T): best single lap. *lap time*
2. **Race Win** (R): first place after 5 laps. *position, lap*
3. **Time Attack** (T): fastest 3-lap total. *race timer*
4. **Survival** (T): longest without crashing. *energy, frames*

### 17. Rock 'n' Roll Racing (SNES / Genesis)
1. **Race Win** (V). *position*
2. **Kill Count** (T): most hits in 90 s. *kills*
3. **Cash Grab** (T): most money in a race. *cash*
4. **Lap Race** (R): first to 3 laps. *lap*

### 18. NBA Jam (SNES / Genesis / Arcade)
1. **First to 15** (V): first to 15 points. *score*
2. **Quarter** (V): highest score after one 2-minute quarter. *score*
3. **Dunks Only** (T): most dunks in a quarter. *dunks*
4. **Steal Race** (T): most steals. *steals*

### 19. Mario Tennis / Mario Golf (N64 / GBC)
1. **First to a Set** (V). *games won*
2. **Rally Count** (T): longest rally. *rally counter*
3. **Closest to the Pin** (T): shortest distance on a par 3. *distance*
4. **Lowest Score** (T): best score on hole 1. *strokes*

### 20. Excitebike / Rad Racer (NES)
1. **Track 1 Time** (T): fastest lap. *timer*
2. **Race Win** (R): first to finish. *position*
3. **No Crash** (T): fewest crashes in 1 lap. *crashes*
4. **Distance** (T): farthest in 60 s. *distance*

---

## Multiplayer party

### 21. Bomberman 64 / Saturn Bomberman
1. **Last Alive** (V): last player standing. *alive flags*
2. **Kill Count** (T): most kills in 2 minutes. *kills*
3. **Power-Up Rush** (R): first to get 3 power-ups. *power-ups*
4. **Survival** (T): longest alive. *frames alive*

### 22. Mario Party (N64) / WarioWare (GBA)
1. **Minigame Win** (V): win one minigame. *winner flag*
2. **Coin Grab** (T): most coins from a minigame. *coins*
3. **5 Microgames** (T): most microgames passed (WarioWare). *score*
4. **Boss Microgame** (R): first to beat one. *result flag*

### 23. Worms / Micro Machines (Genesis / SNES)
1. **Lap Race** (R): first to finish 3 laps. *lap*
2. **First Kill** (V): first kill. *kills*
3. **Total Wipeout** (V): last one standing. *alive flags*
4. **Time Trial** (T): fastest lap. *timer*

---

## Suggested first picks
Best ratio of effort to fun, because the metrics are simple and a start state is easy:
1. **Dr. Mario** and **Tetris** (score or lines, instant rounds)
2. **Super Mario Bros.** (NES flagpole race)
3. **Sonic the Hedgehog** (rings and Act 1 race)
4. **NBA Jam** (score, plays fast)
5. **Killer Instinct** (reuses the fighter pattern from MK2 / SF2)

## Open questions for review
- Do we want mostly **race** challenges (everyone plays at once) or more **turns** (needs one controller each, but simpler)?
- Are Genesis, Saturn and GameCube in scope? The README currently covers NES, SNES, N64, PSX, GBA, GameCube and FBNeo.
- Which of these are worth a RAM research pass first (see `docs/ram-research.md` for the process)?
