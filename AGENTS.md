# AGENTS.md — guide for AI agents (and humans in a hurry)

Randomizer for *The Legend of Zelda: Ocarina of Time* — Switch 2 remake (*Tears of the Kingdom* engine).
Python 3.10+, dependencies: `zstandard` (and `ainb` for the in-game menu). The generator produces a
**LayeredFS mod** (modified files only) that is installed into the Eden emulator (or another Yuzu fork).
**Docs, new code comments, commit messages and release notes are written in English.** Older code comments
are still in French; translate them when you edit those lines.

Then read, in this order:
1. [`README.md`](README.md) — usage, settings; [`docs/GUIDE.md`](docs/GUIDE.md) for players.
2. [`docs/GAME_KNOWLEDGE.md`](docs/GAME_KNOWLEDGE.md) — everything known about the game (flags, quests,
   scripts, pitfalls). **Read it before touching the game.**
3. [`docs/FORMATS.md`](docs/FORMATS.md) — file formats and inspection tools.
4. [`docs/ROADMAP.md`](docs/ROADMAP.md) — remaining work, by priority.

## Rules

- **No game files in the repository** (RomFS, exefs, keys, saves). Everyone extracts their own copy; the path is
  passed with `--romfs`. `output/` and `saves/` are ignored by git.
- Never call a feature "done" without an in-game test: the engine often reacts differently than expected (see
  "Pitfalls" in GAME_KNOWLEDGE). In messages and docs, distinguish **verified in the files** (tools `verify`,
  `events`, `lookup`) from **validated in game**.
- Any logic change must keep the tests green:
  `python -m unittest discover -s tests` (100 seeds per preset; `OOTRR_TEST_SEEDS=20` to go faster).
- Rule files are data (`ootrr/data/**.json`); rules are compiled from Python-like expressions by
  `ootrr/rules.py` (never `eval`).
- For an in-game experiment, use the `--test-*` options (outside the logic) rather than changing the generator,
  then install as `--mod-name OoTRR-essai`.
- The emulator must be **closed** to install (files are locked otherwise). Only one OoTRR mod active at a time.

## Useful commands

```bash
python -m pip install -r requirements.txt
python -m ootrr --check                                  # validate the data
python -m ootrr --list-settings                          # settings
python -m ootrr --seed 1234 --romfs ROMFS --install      # generate + build + install
python -m ootrr.tools.menutest --romfs ROMFS --install   # in-game menu mod (compiles the native module)
python -m unittest discover -s tests                     # tests
python -m ootrr.tools.native_check                       # native generator == Python generator
python -m ootrr.tools.verify --romfs ROMFS --mod MOD --patch output/..._patch.json
python -m ootrr.tools.events --romfs ROMFS DoorOfTime --entry DoorOfTime_Draw   # read a script
python -m ootrr.tools.events --romfs ROMFS Dm_Kokiri_0155 --find Item_Ocarina_Fairy
python -m ootrr.tools.lookup --romfs ROMFS flag IsGet.Item_Hookshot             # save flag
python -m ootrr.tools.lookup --romfs ROMFS msg EventFlowMsg/Enemy_Event 0001    # message
python -m ootrr.tools.lookup --romfs ROMFS actor Banc/KokiriForest Npc_Kokiri   # actors of an area
python -m ootrr.tools.saves backup NAME                  # emulator saves (emulator closed)
python -m ootrr.tools.build_installer                    # output/OoTRR-installer.exe (PyInstaller)
```

`ROMFS` = the `romfs` folder of the extracted **update** (e.g. `.../updates/<version>/romfs`).

## Code map

| Path | Role |
|---|---|
| `ootrr/__main__.py` | Command line, test options, `build_mod` (JSON patch -> ModBuilder) |
| `ootrr/settings.py` | Settings: values, validation, description |
| `ootrr/world.py` | Data loading, settings -> locations, start flags, removed actors, expressions, etc. |
| `ootrr/rules.py` | Rule compiler (vocabulary at the top of the file) |
| `ootrr/search.py` | Child / adult reachability, spheres (the child only uses adult items after going back) |
| `ootrr/fill.py` | "Assumed fill" placement, shuffled boss rewards |
| `ootrr/patch.py` | Result -> JSON patch (everything the builder must apply) |
| `ootrr/modbuild.py` | Mod building: maps, GameData, scripts, RSDB, actor archives, messages, AINB modules |
| `ootrr/ingame_menu.py` | In-game menu: GameData structures, option tables, texts, title sequence |
| `ootrr/formats/` | Read/write: zstd, SARC, BYML, RESTBL, GameData, BFEVFL (scripts), MSBT (messages) |
| `ootrr/tools/` | Tools: verification, inspection, saves, test mods, menu mod, installer |
| `ootrr/data/` | Items, named rules, regions, chests, cutscenes, gifts |
| `native/` | Native module (exlaunch) for the in-game menu and seed generation, see `native/README.md` |
| `tests/` | Generation and format tests |

## Flow of a seed

`settings` -> `World` (data + settings) -> `fill.generate` (placement + "beatable" check) ->
`patch.build_patch` (JSON) -> `__main__.build_mod` -> `ModBuilder.build` (writes the mod to a temporary folder,
then copies it into the emulator). With the in-game menu, the native module runs the same generator inside the
game (`ootrr/native_logic.py` exports the data; `tools.native_check` checks both generators agree).

## Adding something: recipes

- **A chest**: entry in `ootrr/data/world/chests.json` (actor hash, region, rule, vanilla item,
  `event: keep|drop`). Finding the hash: `tools.inventory` or `tools.lookup actor`.
- **A start flag**: `World.start_flags()` (GameData flag name -> value; `#hash` for an entry without a known name;
  text value for an Enum).
- **An item given at the start**: location moved to `Root` (see `_start_location_names`); the builder inserts an
  "add to inventory" action into the intro.
- **A gift from a scene or an NPC**: entry in `ootrr/data/gifts.json` (flow, event number, parameter, vanilla
  text) and `"gift": true` on the location.
- **Editing a script**: `formats/evfl.py` — `replace_strings`, `skip_event_steps`, `add_actions`, `insert_flow`
  (questions, actions, copies of steps; before an event or at the start of an entry point; `set` only writes
  text parameters), `ensure_actor_member`. Always re-read the result with `tools.events`.
- **An actor presence condition**: `World.actor_changes()` -> `{"Presence": {...}}`.
- **A computed condition** ("has the 3 stones", "N medallions"): `World.bool_exps()`
  (postfix expressions, see `gamedata.encode_bool_exp`).
- **Changing a string of an AINB logic module**: `World.logic_patches()` — same length required.
