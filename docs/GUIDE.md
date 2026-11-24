# Installation and usage guide

This guide is for someone who wants to **play** the randomizer without knowing the code. To contribute, see
[`AGENTS.md`](../AGENTS.md) and [`CONTRIBUTING.md`](../CONTRIBUTING.md).

The randomizer comes in two forms:

| | In-game menu (recommended) | Mod generated on PC |
|---|---|---|
| Where settings are chosen | In the game, after "New Game" | On the command line, before generating |
| New seed | Every new game, nothing to reinstall | One installation per seed |
| Features | All (shops, Deku Scrubs, adult start…) | No shuffled shops |
| Spoiler log | `ootrr.tools.ingame_spoiler` (reads the save) | Written with the seed |
| Extra things to install | Nothing with a release (native module provided); devkitPro from source | Nothing |

---

## 1. What you need

1. **Your own copy** of *The Legend of Zelda: Ocarina of Time* (Switch 2) **and its update** (version 131072,
   called "2.0.0" in the code). No game files are provided here.
2. A Yuzu-derived emulator: **Eden** or **Fritchii**, with your own keys.
3. **Python 3.10 or newer** (Windows: tick "Add python.exe to PATH" during installation).
4. The randomizer:
   - **Easiest (Windows, no Python)**: `OoTRR-installer.exe` from the latest GitHub **release** (*Releases* tab).
     It contains everything needed: nothing else to install (skip steps 3 and 4 of this guide, see "Install" in
     chapter 5).
   - **With Python**: the latest GitHub **release** (*Releases* tab of the repository). Download the source code
     (*Source code (zip)*) **and** the `subsdk9` file (already compiled native module) from the **same** release,
     then unzip the source code and put `subsdk9` in its folder.
   - Or the up-to-date sources ("Code" button -> "Download ZIP", or `git clone`): you then need to compile the
     native module with **devkitPro** (devkitA64 + libnx, installed in `C:\devkitPro`, "Switch development"
     component of the Windows installer).

A release's `subsdk9` module only works with the source code of **that** release (it contains the logic and menu
settings of that version): do not mix versions.

## 1b. Getting your game

The randomizer contains **no game files** and distributes none: every player builds the mod from **their own
copy** of the game. From **your** console and **your** purchased game, you need:

- the game and its **update** (version 131072 / 2.0.0), copied with a console dumping tool;
- your console's **keys** (`prod.keys`, `title.keys`), placed in the emulator (see its documentation).

Then install the game **and** its update in the emulator (*File* -> *Install files to NAND*), and check that it
starts normally before going further.

## 2. Extracting the update's RomFS

The randomizer reads the game files from the **update's RomFS** (not the base game's).
With Eden / Fritchii: right-click the game -> *Dump RomFS* (or *Extract*), choosing the update, or any extraction
tool you like. You should get a folder containing `Banc`, `Event`, `Pack`, `GameData`, etc., for example:

```
D:\dumpnup\The Legend of Zelda Ocarina of Time\updates\131072\romfs
```

This path is called **ROMFS** below (put it in quotes if it contains spaces).

## 3. Installing the Python dependencies

Open a terminal in the repository folder, then:

```bash
python -m pip install -r requirements.txt
```

Check that everything is in place:

```bash
python -m ootrr --check
```

## 4. Where the mod is installed

`--install` copies the mod into `<emulator>\load\0400486024DEC000\<mod name>`:

- `%APPDATA%\fritchii` if it exists (Fritchii), otherwise `%APPDATA%\eden` (Eden);
- for another folder, set the `OOTRR_EMU_DIR` environment variable (folder that contains `load`).

Rules:

- **The emulator must be closed** during installation (otherwise files stay locked and the mod is half
  installed).
- **Only one OoTRR mod active at a time**: in the emulator, right-click the game -> *Properties* -> *Add-Ons*,
  tick only `OoTRR-menu`.

---

## 5. In-game menu (recommended)

### Install

Emulator **closed**.

- **Easiest**: run `OoTRR-installer.exe`, choose the **update's** `romfs` folder in the window that opens, and wait
  for the "Installed" message (about a minute). Windows may show a SmartScreen warning (unsigned program):
  *More info* -> *Run anyway*.

Or, in a terminal opened in the randomizer folder:

- with a **release** (native module provided, no devkitPro needed):

  ```bash
  python -m ootrr.tools.menutest --romfs "ROMFS" --native subsdk9 --install
  ```

- from the **sources** (compiles the native module with devkitPro):

  ```bash
  python -m ootrr.tools.menutest --romfs "ROMFS" --install
  ```

The command prepares the modified game files from **your** RomFS and installs everything under the name
`OoTRR-menu`. It takes a few minutes. Only redo it when you change randomizer version.
Then, in the emulator: right-click the game -> *Properties* -> *Add-Ons*, tick `OoTRR-menu`.

### Play

1. Start the game, choose **New Game**.
2. The randomizer menu opens (3 pages). Change settings with the D-pad.
3. Go to the next page with the **Next Page** button at the bottom of the page (A). **B** goes back to the previous
   page (from page 1: to the main menu). On the last page, **Start the Game** leads to the usual confirmation.
4. The seed is generated at the start of the game. It is stored in the save: reloading the game gives exactly the
   same item placement.

The seed shown in the "Manual Seed" description is the one that will be used. Enable **Manual Seed** to type a seed
on the keyboard at launch (same seed + same settings = same game).

### Menu settings

**Page 1 — the world**

| Setting | Effect |
|---|---|
| Manual Seed | Off: random seed (shown). On: a keyboard opens at launch to enter it. |
| Kokiri Forest | Closed (original game), Closed Deku (exit to the field open), Open (Deku Tree open too). |
| Open Door of Time | Door of Time open from the start. |
| Free Time Travel | The Master Sword sends Link back to child at any time (otherwise the remake requires the Forest Temple). |
| Skip Child Zelda | Zelda's Letter and Lullaby at the start; the castle quest is done (the day / night cycle starts). |
| Rainbow Bridge | Condition of the bridge to Ganon's Castle: Open, Vanilla, Stones, Medallions, Dungeons, Hearts. The required number is chosen at the top of page 2. |
| Starting Age | Child (Link's house), Adult (Temple of Time, Master Sword given, open door and free time travel forced) or Random. |
| Start With Consumables | Small Deku Stick and Deku Nut bags full (10 and 20). |

**Page 2 — what is shuffled**

At the top of the page, depending on the bridge condition chosen on page 1: Stones Required (1–3), Medallions
Required (1–6), Rewards Required (1–9), or Hearts Required (3 or 12) + Extra Hearts (+0 to +8).

| Setting | Effect |
|---|---|
| Dungeon Rewards | Stones and medallions shuffled between bosses and Link's pocket. |
| Heart Pieces | Freestanding Pieces of Heart (Freestanding), and boss Heart Containers too (All). |
| Gold Skulltulas | Gold Skulltulas drop a seed item (Overworld: outside dungeons; All: all of them). |
| Maps and Compasses | In place, given at the start, or removed. |
| Shuffle Ocarinas | Saria and the moat give a seed item; the 2nd ocarina obtained is the Ocarina of Time. |
| Lens Required | The logic requires the Lens of Truth for invisible passages. |

**Page 3 — shops, Deku Scrubs, songs, gifts and logic**

| Setting | Effect |
|---|---|
| Shops | 0 to 4 items per shop (8 shops) sell a seed item, once. |
| Shop Prices | Vanilla (price of the replaced item, 99 max), Affordable (10), Random (0 to 95). |
| Deku Scrubs | The 5 Deku Scrubs that sell a unique item sell a seed item. |
| Deku Scrub Prices | Vanilla (40), Affordable (10), Random (0 to 95). |
| Songs | Vanilla (songs in place), Shuffle (shuffled among the 12 song locations), Random (song locations join the pool: a song can be in a chest, and an NPC can give any item). |
| Gifts | Minigame rewards (shooting galleries, bowling, horseback archery, diving, fishing), the five bottles (Anju, Talon, market potion shop, Ghost Shop Big Poes, Ruto's letter), Darunia, Gerudo card, Light Arrows, Fire Arrows, man on the roof, Dampé's gravedigging tour, Great Fairies and Biggoron (Claim Check) give a seed item; the Biggoron Sword is in the item pool (new, not fully validated in game yet). |
| Adult Trade Sequence | On: the logic follows the adult trade sequence (Pocket Egg, Cojiro, Odd Mushroom, Odd Potion, Poacher's Saw, Broken Goron's Sword, Prescription, Eyeball Frog, Eyedrops, Claim Check) and Biggoron can give any item. Off: Biggoron only gives an item you never need to finish. |
| Logic | Glitchless (default: the seed can always be finished without glitches) or No Logic (items anywhere, only the placement rules are kept: the seed is very likely impossible to finish without glitches, for players who want that). The spoiler log says when a seed is not beatable. |

Always on in the menu: cutscenes with no effect on the game, and the cutscenes the game lets you skip with + / X,
are not played (what they do is kept: items, quest steps, world changes). The ending, the credits, the last fights
against Ganondorf and Ganon, and a few scenes that change the time of day are still played (skip them with +).

Also always on: **progressive items** (new, not fully validated in game yet). The first item of a chain you find
is always the first step, whatever the seed put there: Hookshot then Longshot; Bow then the bigger quivers;
Slingshot then the bigger bullet bags; Deku Stick and Deku Nut capacity upgrades; Bomb Bag then the bigger bags;
Goron's Bracelet, Silver Gauntlets, Golden Gauntlets; Silver then Golden Scale; Adult's then Giant's Wallet; Fairy Ocarina then Ocarina of Time (menu only). With the in-game menu this works everywhere. With a PC-built mod
(desktop app, Longshot), chests and NPC gifts are progressive. Gifts are exact; a progressive chest is always a
small chest, and you always end with the biggest quiver / bullet bag / bomb bag, but chests may skip the medium
one. Deku Scrubs and ground items give the item as placed (for the Hookshot, strength and the scales, progressive only
when the seed put every copy in a chest or a gift).

### Seeing your game's spoiler log

Without building anything: the tool reads the seed and settings from the most recent save.

```bash
python -m ootrr.tools.ingame_spoiler --romfs "ROMFS"
```

- `--slot 2`: a specific save slot;
- before playing, with the seed shown in the menu and the chosen settings:
  `python -m ootrr.tools.ingame_spoiler --seed 727557 --set shuffle_shops=4 --set starting_age=adult`
  (setting names: `python -m ootrr --list-settings`).

The spoiler is written to `output\OoTRR_menu_<seed>_<hash>_spoiler.txt`: start, required items, playthrough by
spheres and content of each location.

---

## 6. Mod generated on PC (no menu)

One seed = one mod. Settings are given on the command line:

```bash
python -m ootrr --seed 1234 --romfs "ROMFS" --install --set open_forest=open --set shuffle_hearts=all
```

- `--set name=value` (repeatable) or `--settings file.json` (template: `settings.example.json`);
- `python -m ootrr --list-settings` lists all settings and their values;
- the mod is installed as `OoTRR`; the spoiler and patch are in `output\`;
- without `--romfs`, only the seed is generated (spoiler + patch), no mod.

Shuffled shops are only available with the in-game menu. The other way round, the dungeon key settings
(`small_keys`, `boss_keys`, "Dungeons" page of the desktop app) only exist for the PC-built mod:

- `own_dungeon`: small keys stay in their dungeon, the keys lying on the ground included (a key may move to
  another chest of the same room); boss keys go anywhere in their dungeon;
- `any_dungeon`: in any dungeon; `random`: in any chest of the world;
- `removed`: small keys: no key in the chests, every dungeon starts with all its keys (go and open the locked doors);
  boss keys: owned from the start;
- `key_locations = ground`: a small key may also lie on the ground in its own dungeon (a boss's Heart Container, a
  Gold Skulltula's drop); boss keys stay in chests;
- a key found outside its dungeon says "You got a door key!" (the key of the Treasure Chest Shop): it still counts
  for its own dungeon (the spoiler log tells which one, e.g. `OoTRR_SmallKey_ForestTemple`).

These settings are **not validated in game yet** (feedback welcome).

Also PC-only: `gerudo_card` ("Gerudo Card" on the app's "Shuffle" page). `random` (default): the Gerudo Membership
Card is in the item pool and the Gerudo who gives it gives a seed item; `vanilla`: she gives the card, as in the
original game. The in-game menu always shuffles it with the gifts.

Also PC-only: `gerudo_fortress` ("Carpenters" on the "World" page). `normal` (default): free the 4 carpenters of
the Gerudo Fortress to get the Gerudo Membership Card check; `fast`: the first carpenter you free is enough (the
other three stay in their cells). Validated in game. Coming from Gerudo Valley, let the carpenter boss stop you in
front of the fortress first: he starts the rescue quest.

Also PC-only: `ganon_boss_key` ("Ganon's Boss Key" on the "Dungeons" page). `boss_keys` (default, "Same"): like the
other boss keys. The other values ignore `boss_keys`: `vanilla`: in its chest; `removed`: owned from the start;
`random`: in any chest of the world. The rainbow bridge's conditions also exist: `stones`, `medallions`, `dungeons` (stones + medallions) or `hearts`: you own
Ganon's Castle boss key once you enter the castle's main room with `ganon_boss_key_count` of them; no message is shown,
the key should appear on the dungeon's map screen. Its chest in the tower then holds a seed item.
Verified in the files, **to validate in game**.

Also PC-only: `skip_trials` ("Skip Trials" on the "World" page). On: the six trials of Ganon's Castle are completed
from the start, so the barrier around the tower is down and you can go straight up to Ganondorf. The trial rooms can
still be visited for their chests (and the castle's small key); Light Arrows are still needed for Ganondorf. Validated
in game.

Also PC-only: `skip_tower_collapse` ("Skip Tower Collapse" on the "Dungeons" page). On: once Ganondorf is beaten you go
straight to Ganon's arena instead of escaping the collapsing tower with Zelda. Nothing in the tower is randomized, but
you lose its pots between the two fights. Validated in game.

### Desktop app (`OoTRR-App.exe`) and races

The desktop app (`OoTRR-App.exe` from the release, or `python -m ootrr.tools.longshot_app`) builds the same PC mod
for Longshot or Eden, with the settings on pages instead of `--set`. At start it checks GitHub for a newer release:
if there is one, an **Update available** button (bottom left) opens its page, where you download the new
`OoTRR-App.exe` (the app downloads nothing itself; offline, it just says nothing). For a race:

1. The host sets the options, presses **Install Seed**, then **Copy with Seed** (under Install Seed): a short string such
   as `R2-0VZV0RT00T4-999-HE668CBE6F0` goes to the clipboard (settings + seed + the host's seed hash; copied before
   installing, it has no `-H...` part). **Copy Settings** copies the settings only, each racer then rolls their own
   seed.
2. The others copy that string and press **Paste Settings**: every option (and the seed, if the string has one) is
   set. Don't change anything afterwards. A damaged string, or one from another string format, is refused with a
   message in the log.
3. Everyone presses **Install Seed**. Five item symbols then appear above the log (the seed's hash, as in OoT
   Randomizer; hover one to read its name). Same 5 symbols in the same order = same seed. The spoiler log names them
   on its `Hash symbols` line, and the command line prints them too. When the pasted string has the host's seed
   hash, the app also says "same seed as the host" or, in red, that the seed differs (another OoTRR version).

Everyone must use the same OoTRR version: the same string and seed give the same placement only with the same
generator (a different version gives different symbols, which shows the mismatch). Text seeds are shared as the
number the generator uses (same seed).

### Plandomizer (choose where items are)

`OoTRR-Plando.exe` from the release (or `python -m ootrr.tools.plando_app`) opens a window to build a seed by hand.
It uses the same game, emulator and RomFS folders as the desktop app:

- **Starting age** and **Start point** (top): child or adult, and where Link appears (the list of
  `data/spawns.json` for that age; "Default" = Link's house / Temple of Time).
- **Starting items…**: choose items Link receives at the start. If a selected item is in the shuffled pool, that
  copy is replaced by a green rupee; items not in the pool are added as extra starting items. Only items supported by
  the game's pouch action are listed; dungeon maps and compasses use `maps_compasses`, and dungeon keys use their key
  settings. The tunics appear as `Armor_Adult_Goron` and `Armor_Adult_Zora` (their game actor names); `Goron_Tunic`
  and `Zora_Tunic` are logic aliases, not pouch actor names. The selection is saved in the plando file and included
  in the spoiler.
- **Settings…**: the same settings as the desktop app. The list of locations follows them (scrubs, Skulltulas,
  songs... only appear when they are shuffled).
- **Locations** (left, by region): select one, then double-click an item on the right. "(Random)" leaves it to the
  generator. Boss reward locations take stones and medallions (with `shuffle_rewards = shuffled`), song locations take
  songs (with `shuffle_songs = shuffle`; with `random` they are normal locations). An item placed twice (a second
  Hookshot) replaces a rupee.
- **Check** generates the seed and writes its spoiler in `%APPDATA%\OoTRR\plando`; **Install** (bottom: Longshot or
  Eden, game closed) also builds the mod `OoTRR`, like the desktop app: it replaces the installed seed. Start a new
  game.

Every other item is placed by the generator with the logic: the seed stays finishable, and a plando that cannot be
finished (the Hammer in a chest that needs the Hammer) fails with a message. **Save** writes a JSON file you can
reopen or generate from the command line: `python -m ootrr --plando FILE.json --romfs ROMFS --install`. The
in-game menu generates its own seeds: plandos only work with the PC mod.

---

## 7. Saves

Games are in the emulator's saves. To keep a copy (emulator closed):

```bash
python -m ootrr.tools.saves backup before_gohma
python -m ootrr.tools.saves list
python -m ootrr.tools.saves restore before_gohma
```

When the mod changes (repository update), an old game may be regenerated differently on load: start a new game
after each update.

## 8. Troubleshooting

- **Endless loading or crash**: close the emulator and look at the end of the log
  `%APPDATA%\fritchii\log\eden_log.txt` (or `%APPDATA%\eden\log\…`). Lines starting with `OoTRR:` come from the
  native module (seed, settings read, items given). Attach this file when you report a problem, with the seed and
  settings.
- **The menu does not appear after "New Game"**: check that `OoTRR-menu` is the only OoTRR mod ticked and that it
  contains `exefs\subsdk9` (otherwise compilation failed: run `menutest` again and read the error).
- **"devkitPro not found"**: you are installing from a release: add `--native subsdk9` (`subsdk9` file from the
  same release, in the randomizer folder).
- **"cannot compile the native module"**: devkitPro must be in `C:\devkitPro` with devkitA64.
- **Installing changes nothing**: the emulator was open during installation; close it and run the command again.

## 9. Status and limitations

Features **validated in game**: shuffled chests, freestanding hearts, Gold Skulltulas, Deku Scrubs, shops (one
purchase per item), boss rewards (Link's pocket), open forest, Door of Time, free time travel, bridge (open), maps
and compasses at the start, Saria's items shuffled, starting consumables, day / night cycle with "Skip Child
Zelda", shuffled songs, Master Sword guard, "Next Page" button and B to go back.

Features **not validated in game yet** (feedback welcome): adult start, bombs from a chest without a bag (rupees
instead), shuffled Ocarina of Time (moat), high random Deku Scrub prices, some gifts (man on the roof, Dampé's
tour, Fire Arrows).

Not shuffled: NPCs (except Saria, songs and gifts), minigame chests (keys: see the `small_keys` and `boss_keys`
settings of the PC-built mod). Remaining work:
[`ROADMAP.md`](ROADMAP.md).
