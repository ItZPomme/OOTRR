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
  `python -m unittest discover -s tests` (100 seeds per preset; `OOTRR_TEST_SEEDS=20` to go faster). Seeds are
  generated in worker processes (`tests/seed_pool.py`, one per CPU; `OOTRR_TEST_JOBS=1` for sequential).
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
python -m ootrr.tools.plando_app [FILE.json]            # plandomizer window: chosen items, start age / point, settings
python -m ootrr --plando FILE.json --romfs ROMFS --install   # same, from the command line
python -m ootrr.tools.coords --romfs ROMFS --area Banc/HyruleField --filter Obj_TBox --follow  # Link's position (menu mod) + nearest actors
python -m ootrr.tools.checkwatch --romfs ROMFS           # live: GameData changes, event, nearest actor hashes (Longshot, HOS_CONTROL=1)
python -m ootrr.tools.build_installer                    # output/OoTRR-installer.exe (PyInstaller)
python -m ootrr.tools.longshot_app                       # seed installer window, Longshot or Eden (or Longshot-Installer.bat)
python -m ootrr.tools.build_longshot_app --all           # output/OoTRR-App.exe + OoTRR-Plando.exe (windowed) + OoTRR-Overlay.exe (PyInstaller)
python -m ootrr.multiworld --players 2 --names A,B --seed 1 -o output/mw.json   # multiworld seed (docs/MULTIWORLD.md)
python -m ootrr.tools.mw_server output/mw.json          # multiworld item relay server (port 38300)
python -m ootrr.tools.mw_host output/mw.json            # same + UPnP + room code; tools.mw_join CODE to join
python -m ootrr.tools.mw_app                            # Multiworld window (the app's "+ Multiworld" button)
python -m ootrr.tools.make_icon                          # redraws the logo: ootrr/assets/longshot.png + .ico
```

`ROMFS` = the `romfs` folder of the extracted **update** (e.g. `.../updates/<version>/romfs`).

## Code map

| Path | Role |
|---|---|
| `ootrr/__main__.py` | Command line, test options, `build_mod` (JSON patch -> ModBuilder) |
| `ootrr/settings.py` | Settings: values, validation, description |
| `ootrr/settings_ui.py` | Settings as the Longshot app shows them (pages, texts from the in-game menu, native-only list) |
| `ootrr/world.py` | Data loading, settings -> locations, start flags, removed actors, expressions, etc. |
| `ootrr/rules.py` | Rule compiler (vocabulary at the top of the file) |
| `ootrr/search.py` | Child / adult reachability, spheres (the child only uses adult items after going back) |
| `ootrr/fill.py` | "Assumed fill" placement, shuffled boss rewards, dungeon keys first |
| `ootrr/keys.py` | Dungeon keys (`small_keys`, `boss_keys`, data in `data/keys.json`): names, chest changes, key events |
| `ootrr/plando.py` | Plandomizer files: chosen placements (pool, shuffled rewards / songs), start point, settings; used by `fill` through `World.plando` |
| `ootrr/multiworld.py` | Multiworld: one world per player, shared fill, multiworld file; `mw_protocol.py` + `tools/mw_server.py` relay the items, `mw_log.py` logs who sent what to whom; `mw_code.py` room codes, `mw_session.py` + `upnp.py` hosting / joining (waiting room: each player's settings), `tools/mw_app.py` the app's window (see `docs/MULTIWORLD.md`) |
| `ootrr/longshot_control.py` | Longshot's control pipe (`HOS_CONTROL`): JSON commands, GameData events, guest memory, GameData Int lookup |
| `ootrr/patch.py` | Result -> JSON patch (everything the builder must apply) |
| `ootrr/race.py` | Races: settings string (format 2, frozen field order: bump `FORMAT` when the shown settings change) and the 5 hash symbols; `tools/seed_icons.py` draws them |
| `ootrr/updates.py` | Update check of the desktop app: latest GitHub release vs `__version__` (bump it for every release) |
| `ootrr/modbuild.py` | Mod building: maps, GameData, scripts, RSDB, actor archives, messages, AINB modules |
| `ootrr/ainb_graph.py` | Nodes added to actor AI modules (fast Bunny Hood, Ice Arrows as Blue Fire); inner RESTBL entries, see GAME_KNOWLEDGE |
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
