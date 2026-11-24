# OoT Remake Randomizer

Randomizer for the *Ocarina of Time* remake (Switch 2), built on the principles of OoT Randomizer: region graph,
child / adult logic, "assumed fill" placement that guarantees beatable seeds, spoiler log by spheres. It produces a
**LayeredFS mod** (modified files only): the original game files are never touched and are not in this repository.

**To play** (installation, menu settings, spoiler, troubleshooting): [`docs/GUIDE.md`](docs/GUIDE.md).

Contributors and AI agents: start with [`AGENTS.md`](AGENTS.md), then
[`docs/GAME_KNOWLEDGE.md`](docs/GAME_KNOWLEDGE.md), [`docs/FORMATS.md`](docs/FORMATS.md),
[`docs/ROADMAP.md`](docs/ROADMAP.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Status

- All chests are shuffled (114, or 134 with maps and compasses), except minigame chests and the Boss Rush chests.
  The 37 small key chests and 6 boss key chests join them with `small_keys` / `boss_keys` (PC-built mod only,
  **not validated in game yet**).
- Freestanding Pieces of Heart, boss Heart Containers, stones and medallions can be shuffled.
- Open forest, open Door of Time, free time travel, bridge conditions, starting items, many skipped cutscenes.
- In progress: Deku Scrub salesmen, Skulltulas, shops (mechanisms validated, logic to write), in-game setting
  questions.

## Usage

Python 3.10+, then once: `python -m pip install -r requirements.txt` (installs `zstandard`).
You need the RomFS extracted from **your own copy** of the game (the update's one: `updates\<version>\romfs`).

```bash
python -m ootrr --seed 1234 --romfs "PATH\TO\updates\<version>\romfs" --install
```

- `--install` copies the mod into `<emulator>\load\0400486024DEC000\OoTRR` (emulator closed). Detected folder:
  `%APPDATA%\fritchii` (recent Fritchii), otherwise `%APPDATA%\eden`; override with the `OOTRR_EMU_DIR` variable.
- `output\OoTRR_<seed>_<hash>_spoiler.txt`: required items, playthrough by spheres, content of each location.
- `output\OoTRR_<seed>_<hash>_patch.json`: everything the mod applies.
- Without `--romfs`, only the seed is generated (spoiler + patch).
- Settings: `--set name=value` (repeatable) or `--settings file.json` (see `settings.example.json`).

### Desktop app and races

`python -m ootrr.tools.longshot_app` (or `OoTRR-App.exe`, built by `python -m ootrr.tools.build_longshot_app`)
installs a seed for Longshot or Eden with the settings on pages. **Copy Settings** / **Copy with Seed** put a short,
versioned settings string on the clipboard (`R2-<settings><check>[-<seed>[-H<seed hash>]]`, `ootrr/race.py`; format 2 since the key settings), **Paste Settings**
applies one: the same string with the same seed and OoTRR version builds exactly the same seed. After an install the
app draws the seed's 5 **hash symbols** (32 items of the game, drawn by the app, no game file); the spoiler log and
the command line name them (`Hash symbols: ...`) so racers can compare. Once the host has installed the seed, their
**Copy with Seed** also carries the seed hash, and a racer's app then says after the install whether they got the
same seed. See [`docs/GUIDE.md`](docs/GUIDE.md).

## Settings

`python -m ootrr --list-settings` gives the up-to-date list.

| Setting | Values | Effect |
|---|---|---|
| `open_forest` | `closed`, `closed_deku`, `open`, `ask` | Blocking Kokiri removed, invisible walls disabled; `ask` = question at the start of the game (prototype) |
| `open_door_of_time` | yes / no | Door open; letter and lullaby at the start; the Ocarina of Time stays in the moat (visible with the 3 stones) and gives the Song of Time |
| `skip_child_zelda` | yes / no | Zelda's letter and lullaby at the start, castle quest done (day / night cycle) |
| `starting_age` | `child`, `adult`, `random` | Starting age; adult = Temple of Time, open door and free time travel forced, Master Sword given |
| `start_with_consumables` | yes / no | 10 Deku Sticks and 20 Deku Nuts at the start |
| `cucco_count` | 1 to 7 (default 7) | Cuccos Anju needs in her pen before her reward (PC-built mod only; verified in the files, **to validate in game**) |
| `big_poe_count` | 1 to 5 (default 5) | Big Poes the Poe buyer needs before his reward; the remake gives the bottle at 500 points = 5 Big Poes (PC-built mod only; verified in the files, **to validate in game**) |
| `fast_bunny_hood` | yes / no (default no) | Link runs 1.5 times faster while he wears the Bunny Hood, as in Majora's Mask (PC-built mod only; **validated in game** in Longshot) |
| `blue_fire_arrows` | yes / no (default no) | Ice Arrows act as Blue Fire: shooting one at red ice melts it (Ice Cavern, King Zora, who then gives the Zora Tunic); the logic accepts Ice Arrows, the Bow and magic instead of a bottle (PC-built mod only; **validated in game** in Longshot) |
| `complete_mask_quest` | yes / no (default no) | Happy Mask Shop quest completed from the start: nothing to sell or pay, every mask can be borrowed, Mask of Truth included; Keaton still after the Kakariko gate (PC-built mod only; verified in the files, **to validate in game**) |
| `shuffle_songs` | `vanilla`, `shuffle`, `random` | Songs in place, shuffled among themselves, or in the pool |
| `shuffle_ocarinas` | yes / no | Fairy Ocarina (Saria) and Ocarina of Time (moat) shuffled; no = in place |
| `shuffle_gifts` | yes (default) / no | 26 shuffled gifts: Fire Arrows (Lake Hylia), the 5 bottles (Anju, Talon, market potion shop, 5 Big Poes, Ruto's letter), adult Anju's Pocket Egg, Biggoron (Claim Check; the Biggoron Sword joins the pool), man on the roof (Kakariko), Dampé's gravedigging tour, shooting gallery, bowling, horseback archery, diving, adult fishing, Darunia, Gerudo card, Light Arrows, 6 Great Fairies (verified in the files, **to validate in game**; tokens with the native menu) |
| `adult_trade_sequence` | yes / no (default no) | The logic follows the vanilla adult trade sequence (Pocket Egg -> ... -> Claim Check, then Biggoron) and Biggoron's gift can be any item; off: Biggoron only gives an item that is never needed. The trade items themselves are not shuffled (verified in the files, **to validate in game**) |
| `free_time_travel` | yes (default) / no | The sword sends you back to child at any time (the remake requires the Forest Temple) |
| `bridge`, `bridge_count` | `open`, `vanilla`, `stones`, `medallions`, `dungeons`, `hearts` + number | Rainbow bridge condition |
| `shuffle_rewards` | `vanilla`, `shuffled` | Stones and medallions shuffled between bosses and Link's pocket |
| `shuffle_hearts` | `none`, `freestanding`, `all` (default) | Freestanding Pieces of Heart (and boss Heart Containers) shuffled |
| `maps_compasses` | `vanilla`, `start_with`, `shuffle`, `removed` | Maps and compasses |
| `small_keys` | `vanilla` (default), `own_dungeon`, `any_dungeon`, `removed`, `random` | Small keys of the 8 dungeons with keys (Forest, Fire, Water, Shadow, Spirit, Bottom of the Well, Gerudo Proving Grounds, Ganon's Castle). `own_dungeon`: a key only moves to another chest of the same room (prudent logic, see below); `removed`: no key in the chests, each dungeon's key counter starts full; `random`: any chest of the world. PC-built mod only, **not validated in game** |
| `boss_keys` | same values | Boss keys (6 dungeons, Ganon's Castle included). `removed`: owned from the start. PC-built mod only, **not validated in game** |
| `key_locations` | `chests` (default), `ground` | Where shuffled small keys may go. `ground`: also ground items (boss Heart Containers, Pieces of Heart, Gold Skulltula drops), only for a key of the dungeon the item lies in (the game adds a ground key to the dungeon of the current map). Boss keys stay in chests. PC-built mod only |
| `skip_trials` | yes / no (default no) | Ganon's Castle trials completed from the start: the six barriers and the one around the tower are down, the trial rooms stay open for their chests; the logic no longer needs the castle's small key for Ganon, Light Arrows still needed (PC-built mod only; **validated in game** in Longshot) |
| `skip_cutscenes` | `none`, `safe` | Cutscenes without effect marked as seen, cutscenes the game lets you skip (+ / X) never played (their effects kept), Rauru and Saria skipped, interrupting Kokiri disabled |
| `logic` | `glitchless`, `none` | `glitchless`: the seed can always be finished without glitches; `none`: no logic, items placed at random (placement constraints kept), the seed is very likely impossible to finish without glitches |
| `logic_lens_required`, `accessibility` | | Logic options |

Test options (outside the logic, for in-game experiments): `--test-chest`, `--test-pickup`, `--test-drop`,
`--test-scrub`, `--test-set`, `--test-flag`, `--test-give ITEM` (starting inventory) and
`--test-start BANC=POINT` (e.g. `HyruleField_Child=HyruleField_FrontOfMarket`).

## Tools

```bash
python -m ootrr --check                      # validate the data
python -m unittest discover -s tests         # tests (100 seeds per preset)
python -m ootrr.tools.verify --romfs ... --mod ... --patch ...   # check an installed mod
python -m ootrr.tools.events --romfs ... DoorOfTime --entry DoorOfTime_Draw   # read a game script
python -m ootrr.tools.lookup --romfs ... flag IsGet.Item_Hookshot             # flags, messages, actors, tables
python -m ootrr.tools.inventory --romfs ... --out inventory      # list every chest of the game
python -m ootrr.tools.roundtrip --romfs ...  # check BYML rewriting on every map
python -m ootrr.tools.saves backup <name>    # Eden saves (also restore, list)
python -m ootrr.tools.ingame_spoiler --romfs ...   # spoiler of the in-game menu playthrough (latest save)
python -m ootrr.tools.ingame_spoiler --seed 727557 --set shuffle_shops=4   # ... or menu seed + settings
```

A [PopTracker](https://github.com/black-sliver/PopTracker) map tracker built from this logic lives in its own
repository: [OOTRR-Tracker](https://github.com/ItZPomme/OOTRR-Tracker).

## Structure

| Path | Role |
|---|---|
| `ootrr/data/` | Items, named rules, regions, chests, cutscenes |
| `ootrr/rules.py`, `search.py`, `fill.py` | Rules, reachability, placement |
| `ootrr/world.py`, `settings.py` | World data and settings -> what the mod must do |
| `ootrr/spoiler.py`, `patch.py` | Spoiler log, JSON patch |
| `ootrr/race.py` | Settings string (copy / paste for races) and hash symbols |
| `ootrr/modbuild.py` | Mod building and installation |
| `ootrr/formats/` | Zstd, SARC, BYML, RESTBL, GameData, BFEVFL scripts, MSBT messages |
| `ootrr/tools/` | Verification, inspection, saves, test mods |
| `docs/` | Game knowledge, formats, remaining work |

## Current limitations

- Rules marked `prudent` in `chests.json`: the exact chest location is not confirmed.
- Not shuffled: NPCs, songs, fairies, chests with conditional content, minigame chests and 4 story-event chests.
- Dungeon keys (`small_keys`, `boss_keys`): the dungeons have no door layout in the data, so the logic is prudent:
  with shuffled small keys, every location of a dungeon needs all its small keys, except (with `own_dungeon`) the
  chests of the rooms that hold keys in the original game. A key of another dungeon is shown as the Treasure Chest
  Shop's "door key" (also for boss keys); the chest event adds it to the right dungeon (see GAME_KNOWLEDGE,
  "Dungeon keys"). Not available with the in-game menu.
- Upgrades are not yet progressive in chests.
- The rainbow bridge with conditions has not been tested in game yet.
- See [`docs/ROADMAP.md`](docs/ROADMAP.md).
