# Multiworld (and later coop)

Several players, each in their own game, each with their own seed (their own world, possibly their own settings).
The items of all worlds are shuffled together: a chest of Alice's world may hold Bob's Hookshot. When Alice opens it,
the server sends the Hookshot to Bob's game.

Coop (everyone on the same seed, an item found by one is given to all) comes after, on the same server and protocol.

## Status

| Part | State |
|---|---|
| Shared fill, multiworld file, spoiler (`ootrr/multiworld.py`) | done, unit tests (`tests/test_multiworld.py`) |
| Protocol (`ootrr/mw_protocol.py`) and server (`ootrr/tools/mw_server.py`) | done, unit tests with fake games |
| Per-player mod (items of other players in our locations) | to do |
| Eden: native module client (socket, items given in game) | to do, **nothing validated in game** |
| Longshot: control pipe client (`ootrr/longshot_control.py`) | events, GameData reads, queued writes: **used live** |
| Longshot: PC bridge | to do; detecting checks and giving an item (saved) both work through the pipe |
| Desktop app (create / join a multiworld) | to do |

## Usage (what exists today)

```bash
python -m ootrr.multiworld --players 2 --names Alice,Bob --seed 1234 -o output/mw.json
python -m ootrr.multiworld --config players.json --seed 1234 -o output/mw.json
python -m ootrr.tools.mw_server output/mw.json --port 38300
```

`players.json`: `{"players": [{"name": "Alice", "settings": {"shuffle_songs": "shuffle"}}, {"name": "Bob"}]}`.
The generator writes the multiworld file (placements of every world, as `[owner, item]` pairs; `owner` = index of
the receiving player, from 0) and a text spoiler next to it (`.txt`). The server keeps its progress in
`<file>.state.json` (written after every change, atomically): it can be stopped and started again.

## Generation

- Per world (`fill.prefill`, the start of the single-world fill, same random draws): fixed locations, shuffled
  rewards and songs, plando, dungeon keys, maps and compasses. **They stay in their own world.**
- Progression of every world: assumed fill over the locations of every world at once. Reachability sweeps every world
  together (`MultiState`): an item found in world A for player B goes into B's inventory.
- Items placed in random order with one sweep each (as Archipelago does). The single-world order (fewest possible
  locations first) costs one sweep per remaining item per step: N^3 with N players, minutes for 4.
  Measured: 0.2 s for 2 players, 1.3 s for 4, ~6 s for 8 (default settings).
- **Child / adult**: in this remake Link only goes back to child after the Forest Medallion, so the logic only lets
  the child use items found as child (`search.State`). A received item comes whenever the other player finds it,
  whatever the receiver's age: it counts **for the receiver's adult only** (both ages once he can go back). Sound but
  conservative.
- Not supported yet: plando, `logic = none`. Up to 16 players.
- The native in-game generator is not involved: a multiworld is always generated on the PC.

## Protocol

TCP, one message per line, UTF-8, tab-separated fields (location names hold spaces); see the docstring of
`ootrr/mw_protocol.py`. Port 38300 by default.

- The game says `HELLO 1 <room hash> <slot>`; the server checks the hash (the game must run this multiworld's seed),
  answers `WELCOME`.
- The game sends `CHECK <location>` when it finds a location of its world (any location: the server knows which
  items belong to others; sending all of them also lets a tracker follow the game later).
- Received items are numbered per player (`ITEM <index> <from> <item> <location>`). The game saves how many it has
  applied (GameData integer, saved with the game) and sends `SYNC <count>` after connecting and after applying items:
  the server sends again everything from `<count>`. A lost connection, a crash or a reloaded save never loses or
  duplicates an item (an index already applied is ignored).
- `GOAL` when the player beats the game: the server sends the items of that world that the other players still need
  ("release"; `--no-release` keeps them).
- A game reconnecting as the same player replaces its old connection.

## Game side (to do)

What the games need, the same for Eden and Longshot:
1. **A location holding another player's item** gives nothing to our player. Shown item: the real item model (all
   worlds are this game), text "<item> for <player>" if possible.
2. **Sending**: when such a location (or any location) is found, `CHECK` to the server.
3. **Receiving**: items arrive at any time, from another thread; they must be given **on the game thread**, at a safe
   moment (not during a cutscene, a menu or a loading), with the usual adjustments (`ingame::AdjustItem`:
   progressive items, ocarinas, bombs without a bag, rupees to the wallet, heart containers).
4. **Saved counter** of applied items (`OoTRR.MW.Received`, saved integer) and the connection settings (address,
   slot) in the save.

### Eden (and its forks): native module

- `nn::socket` is exported by the **sdk** module (446 symbols, verified in the files: `Socket`, `Connect`, `Send`,
  `Recv`, `Poll`, `GetAddrInfo`, `InetPton`...) and the game already initializes it (`main` imports
  `nn::socket::Initialize(Config)` and `IsInitialized`): our module imports them by name like `nn::swkbd`.
  Eden passes guest sockets to the host network (same approach as Super Mario Odyssey Online, exlaunch). **To
  validate in game**: connecting to 127.0.0.1 and to a LAN address from Eden.
- A network thread (like `rando/coords.cpp`) connects, reads and queues the items; a hook called every frame on the
  game thread gives them (the hook is still to be found: a node or update function run each frame in play).
- Placement of a multiworld: the module receives its world's table instead of generating it (from the mod files, or
  sent by the server after `WELCOME`); remote items: tokens whose `PouchAdd` gives nothing and sends `CHECK`.
- Address and slot: menu row + virtual keyboard (`rando/keyboard.cpp`).

### Longshot: no native code

Longshot is a static recompilation of the game (`hos` layer, log `logs/longshot_log.txt`): it loads **RomFS mods
only** (`mods/<name>/romfs`, no exefs / subsdk) and does **not** implement `nn::socket` (its log:
`unimplemented import _ZN2nn6socket10InitializeERKNS0_6ConfigE`). The game itself cannot reach the server there.

**But Longshot has a control pipe** (found in the strings of `bin/longshot.exe`, then used live on 2026-11-17,
Longshot v3.0.0-rc.6, a save in play in Goron City): started with `HOS_CONTROL=<name>` (environment, or
`longshot_env.txt` in its folder, which only takes `HOS_` / `LONGSHOT_` switches), it serves a JSON API on
`\\.\pipe\<name>`, this Windows user only, no TCP. `HOS_CONTROL_MEM=ro` / `rw` opens guest memory reads / writes
(Longshot warns that writes can corrupt the game: throwaway save). Client: `ootrr/longshot_control.py` (its
docstring has the details), `python -m ootrr.longshot_control PlayerStatus.MaxLife`.

Verified live:
- `status`, `subscribe`, `mem_read` work. Commands also include press / stick / sequence (input), saves, teleport,
  wait, option_get / option_set, mem_write, mem_read_many, quit, relaunch.
- **Same code as Eden**: `.longshot_exefs/main` is build E0F3CCFA, and main is loaded at guest **0x80020000** (rtld
  at 0x80000000) with the same bytes as `output/native/main.bin`: every offset of the native module applies.
- **Watching the game without memory access**: `subscribe {events: ["oot"], flags: [names], changes: true}` sends, in
  play, every N frames: map, position, age, life, rupees, the watched GameData values **by name** (up to 64), and every
  changed Bool / Int / Enum / UInt value by hash. That is enough to detect found locations (a flag per location set
  by the mod, matched by its hash).
- **Reading any GameData Int / Bool from the PC**: the lookups of the game's `GetInt` (0x163d20) and `GetBool`
  (0x3744460), decompiled and re-implemented over `mem_read`: values equal to those of the event stream.

Plan: a **PC bridge** (Python, part of the desktop app): Longshot pipe <-> multiworld server.
- Found locations: the per-player mod sets a saved flag per location (`OoTRR.MW.L<n>`, or the location's existing
  flag) -> `changed` in the `oot` events -> `CHECK`.
- Received items: **solved for a simple item** (`HOS_CONTROL_MEM=rw`, throwaway save, 2026-11-17): the bridge
  appends writes to the game's own GameData write queues (`Longshot.set_bool` / `set_int`), which the game applies at
  its next frame, as if it had written them itself. Hookshot given with `IsGet.Item_Hookshot` = true and
  `PouchData.Item_Hookshot.StockNum` = 1: shown in the menu, equipped, **fires, and is still there after save and
  reload** **[game]**. Same for rupees (`PlayerStatus.CurrentRupee`, also as an "add") and a Deku Nut count.
- Writing a value's entry directly instead (+0x1c) is shown in game (HUD rupees, menu counts, even a new Hookshot)
  but **not saved**: after save + reload everything was back **[game]**. The queued write also sets the entry's
  +0x18 copy (probably what the save reads). Always go through the queues.
- Still to handle per item kind, as the native module's `ingame::AdjustItem` does: progressive items (read `IsGet.*`
  first), bags and quivers (capacity), ammunition counts, Heart Containers / Pieces (`PlayerStatus.MaxLife`, the
  pieces counter), songs, bottles, swords and shields (equipment), keys (dungeon counters). There is no get-item
  window: the bridge can show the received item itself (or later a mailbox Int read by a node of Link's AI, to let
  the game play its own get-item event).
- A queued write takes two `mem_write` calls (the entry, then the count); a game write landing between them could
  collide. Not seen; to keep in mind (write when `event` is false in the `oot` stream, few writes per frame).
- Longshot is a release candidate: the pipe and its JSON may change; the bridge checks `"protocol": 1` of `status`.

The same pipe-and-memory approach cannot drive Eden (no such pipe), so Eden keeps the native client.

## Coop (after the multiworld)

Same server, a room kind "coop": every player runs the same seed; a location found by one player gives its item to
all the others and is marked found for everyone (`CHECKED <location>`, new message), so that opening it again gives
nothing.
