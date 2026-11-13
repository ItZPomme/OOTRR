# OoT Remake Randomizer

Randomizer for the *Ocarina of Time* remake (Switch 2), built on the principles of OoT Randomizer: region graph,
child / adult logic, "assumed fill" placement that guarantees beatable seeds, spoiler log by spheres. It produces a
**LayeredFS mod** (modified files only): the original game files are never touched and are not in this repository.

**To play** (installation, menu settings, spoiler, troubleshooting): [`docs/GUIDE.md`](docs/GUIDE.md).

Contributors and AI agents: start with [`AGENTS.md`](AGENTS.md), then
[`docs/GAME_KNOWLEDGE.md`](docs/GAME_KNOWLEDGE.md), [`docs/FORMATS.md`](docs/FORMATS.md),
[`docs/ROADMAP.md`](docs/ROADMAP.md) and [`CONTRIBUTING.md`](CONTRIBUTING.md).

## Status

- All chests are shuffled (114, or 134 with maps and compasses), except small keys, boss keys, minigame chests and
  the Boss Rush chests.
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

## Settings

`python -m ootrr --list-settings` gives the up-to-date list.

| Setting | Values | Effect |
|---|---|---|
| `open_forest` | `closed`, `closed_deku`, `open`, `ask` | Blocking Kokiri removed, invisible walls disabled; `ask` = question at the start of the game (prototype) |
| `open_door_of_time` | yes / no | Door open; letter and lullaby at the start; the Ocarina of Time stays in the moat (visible with the 3 stones) and gives the Song of Time |
| `skip_child_zelda` | yes / no | Zelda's letter and lullaby at the start, castle quest done (day / night cycle) |
| `starting_age` | `child`, `adult`, `random` | Starting age; adult = Temple of Time, open door and free time travel forced, Master Sword given |
| `random_spawn` | yes / no | Start anywhere outside dungeons (`data/spawns.json`), depending on age |
| `start_with_consumables` | yes / no | 10 Deku Sticks and 20 Deku Nuts at the start |
| `shuffle_songs` | `vanilla`, `shuffle`, `random` | Songs in place, shuffled among themselves, or in the pool |
| `shuffle_ocarinas` | yes / no | Fairy Ocarina (Saria) and Ocarina of Time (moat) shuffled; no = in place |
| `shuffle_gifts` | yes / no | 20 shuffled gifts: Fire Arrows (Lake Hylia), man on the roof (Kakariko), Dampé's gravedigging tour, shooting gallery, bowling, horseback archery, diving, adult fishing, Anju, Darunia, Gerudo card, Light Arrows, 6 Great Fairies (verified in the files, **to validate in game**; tokens with the native menu) |
| `free_time_travel` | yes (default) / no | The sword sends you back to child at any time (the remake requires the Forest Temple) |
| `bridge`, `bridge_count` | `open`, `vanilla`, `stones`, `medallions`, `dungeons`, `hearts` + number | Rainbow bridge condition |
| `shuffle_rewards` | `vanilla`, `shuffled` | Stones and medallions shuffled between bosses and Link's pocket |
| `shuffle_hearts` | `none`, `freestanding`, `all` | Freestanding Pieces of Heart (and boss Heart Containers) shuffled |
| `maps_compasses` | `vanilla`, `start_with`, `shuffle`, `removed` | Maps and compasses |
| `skip_cutscenes` | `none`, `safe` | Cutscenes without effect marked as seen, Rauru and Saria skipped, interrupting Kokiri disabled |
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

## Structure

| Path | Role |
|---|---|
| `ootrr/data/` | Items, named rules, regions, chests, cutscenes |
| `ootrr/rules.py`, `search.py`, `fill.py` | Rules, reachability, placement |
| `ootrr/world.py`, `settings.py` | World data and settings -> what the mod must do |
| `ootrr/spoiler.py`, `patch.py` | Spoiler log, JSON patch |
| `ootrr/modbuild.py` | Mod building and installation |
| `ootrr/formats/` | Zstd, SARC, BYML, RESTBL, GameData, BFEVFL scripts, MSBT messages |
| `ootrr/tools/` | Verification, inspection, saves, test mods |
| `docs/` | Game knowledge, formats, remaining work |

## Current limitations

- Rules marked `prudent` in `chests.json`: the exact chest location is not confirmed.
- Not shuffled: NPCs, songs, fairies, small keys, chests with conditional content, minigame chests and 4 story-event
  chests.
- Upgrades are not yet progressive in chests.
- The rainbow bridge with conditions has not been tested in game yet.
- See [`docs/ROADMAP.md`](docs/ROADMAP.md).
