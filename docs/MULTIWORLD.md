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
| Per-player mod (`ootrr/tools/mw_mod.py`, `multiworld.slot_patch`) | PC-built mod; another player's item only in a plain chest: placeholder (one per chest, the item's model, "You found Bot's Hookshot!") + chest event raising `OoTRR.MW.L<n>`: **validated in game** (Longshot) |
| Eden: native module client (socket, items given in game) | to do, **nothing validated in game** |
| Longshot: control pipe client (`ootrr/longshot_control.py`) | events, GameData reads, queued writes: **used live** |
| Longshot: PC bridge (`ootrr/tools/mw_longshot.py`, items: `ootrr/mw_items.py`) | **validated in game** (Longshot v3.0.0, 2026-11-20): found chest -> CHECK, 5 received items given and kept after save + reload; Heart Containers do not work yet (see below) |
| Desktop app: Multiworld window (`ootrr/tools/mw_app.py`), room codes (`mw_code.py`), hosting / joining (`mw_session.py`, `upnp.py`) | **partly validated** (2026-11-21): hosting from the window, UPnP opening the port on a home router, code, joining with the code (player data fetched), items received in Longshot; waiting room with each player's settings, then *Install and play* (one PC); to validate: a player on another network |

## Joining with a room code (desktop app)

The app's **Multiworld** button (footer, "+") opens the Multiworld window (`ootrr/tools/mw_app.py`):
- **Host**: your name -> *Open the waiting room*: starts the server inside the app, asks the router to open the
  port by UPnP (`ootrr/upnp.py`) and shows the **room code** to share. The players who join appear in the list
  with their settings (*Remove player* takes one out); *Generate and start* (seed: empty = random) generates the
  multiworld, **each player with their own settings** (the host: the app's), into
  `APPDATA/OoTRR/multiworld/mw_<hash>.json` + spoiler; the code does not change. *Host a file...* serves a
  multiworld generated before (to resume: the same code works, the file keeps the waiting room's id).
- **Join / Play** (also for the host): code -> *Look up*. While the room waits: your name -> *Join with my
  settings* (your app's settings, set before opening the window, sent as a settings string, `ootrr.race`: the same
  OoTRR version as the host is needed; joining again under the same name replaces them); the window then watches
  the room and says when the host has started. Then: your name -> *Install and play*: the app fetches **your
  player's data only** (`GETSLOT`: your world, never the others', no spoiler), builds your mod into Longshot's
  `mods/OoTRR`, starts Longshot with its control pipe (`HOS_CONTROL=ootrr-mw`, `HOS_CONTROL_MEM=rw`) and runs the
  bridge in the app; the log shows who sent what to whom. Longshot only for now.
- Waiting room (`tools.mw_server.Lobby`, `mw_session.Host.open_room` / `generate`, `join_room`, `room_state`):
  **validated** with the desktop app on one PC (2026-11-21): the host opened the room, a test player joined with
  other settings, *Generate and start* then *Install and play* worked (mod built, Longshot started).

The code (`ootrr/mw_code.py`, 20 characters, `K7QM-29XD-...`) holds the host's IPv4 address, the port and the room
id (the room hash, or the id of the waiting room the multiworld comes from), with a check character (a typo is caught; I/L/O read as 1/0). The address in it:
1. the router's internet address when UPnP opened the port (most home routers allow UPnP; the app says if not);
2. otherwise this PC's local address: works on the same network only; for players elsewhere, open the port
   (TCP 38300) on the router by hand and type the internet address, or use a VPN (Tailscale, ZeroTier) and type its
   address (the *Address for the code* field).
Seen on 2026-11-21: UPnP opened the port on the developer's box (a first test from the command line found no
gateway: the SSDP search is now sent on every network interface). The host cannot use the internet-address code
on their own network (the box refused the connection to its own public address, "hairpinning"): the host's app
uses its own server directly, and the window also gives a **local-network code** for players at the host's place. A public relay (always reachable) would remove these cases; not done (needs
hosting).

Command line equivalents: `python -m ootrr.tools.mw_host FILE` (server + code), `python -m ootrr.tools.mw_join CODE
[--player NAME]` (names, or the player data file), then `tools.mw_mod` and `tools.mw_longshot` accept that file
instead of the whole multiworld file (`multiworld.load_slot`).

## Usage (what exists today)

```bash
python -m ootrr.multiworld --players 2 --names Alice,Bob --seed 1234 -o output/mw.json
python -m ootrr.multiworld --config players.json --seed 1234 -o output/mw.json
python -m ootrr.tools.mw_server output/mw.json --port 38300
python -m ootrr.tools.mw_mod output/mw.json --slot 2 --romfs "<Longshot>/romfs" --mod-out "<Longshot>/mods"
python -m ootrr.tools.mw_longshot output/mw.json --slot 2 --server HOST:38300   # Longshot started with HOS_CONTROL=1, HOS_CONTROL_MEM=rw
```

**Log of the exchanges** (`ootrr/mw_log.py`): the server writes every exchange to `<file>.log` and sends it to every
game; each bridge writes them to `<file>_p<slot>.log` (`--log` for another path), plus a line when an item has really
been given in its game. Items are named as the game writes them (`ActorMsg/PouchContent`, from Longshot's RomFS or
`--romfs`; actor name otherwise):

```
[2026-11-20 23:42:14] Bot -> Pomme: Deku Shield (Bottom of the Well Lens of Truth Chest)
[2026-11-20 23:42:15] Pomme -> Bot: Din's Fire (Bottom of the Well Red Rupee Chest 2)
[2026-11-20 23:42:31]   given in game: Deku Shield (from Bot, Bottom of the Well Lens of Truth Chest)
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
- **Progressive chains** with a logic item (Hookshot, bow, slingshot, bomb bags, strength, scales; `strict_chains`):
  in chests, gifts and on the ground, where the PC-built mod gives the next step (GAME_KNOWLEDGE, "Progressive ground
  items"). Exception: shuffled Deku Scrubs may sell quivers and bullet bags as placed (they accept little else). Copies of a chain may be split between worlds: own
  chests / gifts and the bridge all give the next step (`patch.progressive_chains` with `progressive_remote`). The
  game's pouch count reads `PouchData.<item>.StockNum` (decompiled, main 0x17a580), which the bridge writes.
  **Verified in the files and by tests** (every order of chests, gifts and received copies: level >= copies found);
  **to validate in game**. A chain whose logic matters with a copy sold by a Deku Scrub stays as placed, received
  copies too (`multiworld.fixed_chains`). A multiworld in progress: reinstall the mod (*Install and play*);
  the multiworld file keeps the version that made it, so its hash does not change with an update.
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

## Game side

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

The **PC bridge** (`ootrr/tools/mw_longshot.py`): Longshot pipe <-> multiworld server.
- **Found locations** (validated in game, 2026-11-20): another player's item only goes into a plain chest
  (`multiworld.can_hold_remote`: no event of its own kept, not conditional, not a gift; 96 of 161 shuffled
  locations). The chest gives its own copy of `Obj_MiniGame_SmallKey` ("door key", not put in the pouch),
  `OoTRR_MW_A<rank>` (`multiworld.remote_actor`, `ModBuilder._write_mw_actors`), whose get texts name the owner:
  "You found Bot's Purple Rupee!" / "It is on its way to Bot's game." (`_mw_texts`, English in every language,
  the item's name as the game writes it; **validated in game**, Longshot, 2026-11-21), and the model of the owner's
  item (`_use_item_model`, rupees included; Link holds Bot's Hookshot: **validated in game**, 2026-11-21; a rupee's
  model not seen in game yet). Its `GetEventName` runs
  a copy of the boss key chest script whose added action is "`OoTRR.MW.L<rank>` + 1" (saved Int,
  `ModBuilder._write_key_flows`). The bridge sees the Int in the `changed` values of the `oot` events -> `CHECK`;
  at connection and after each loading it reads every watched Int again.
- **A copied chest script must be renamed**: with its template's name (`ForestTemple_Gimmick`, the file and
  flowchart names inside the `.bfevfl`) the chest never opened, no error; renamed (`replace_strings`), it opens and
  runs **[game]**. Same code for the small / boss keys of another dungeon (`keys.py`), which had never been tested:
  they should now work too (to validate).
- **Received items** (`mw_items.ItemGiver`): queued GameData writes, given when Link is in play (no scene, no
  loading), counted in the saved Int `OoTRR.MW.Received` (`SYNC`). Validated **[game]**: Hookshot, progressive bomb
  bag (Large -> Small) + 20 bombs, Bow + small quiver + 30 arrows, rupees, all kept after save + reload.
  - **Only queued writes count**: writing a value's entry directly (+0x1c, even with its +0x0c "written" flag) is
    shown for a while but lost after save + reload, and leaves a stale entry (the rupees and the pouch live in other
    objects, which only queued writes reach).
  - **The queue append must be atomic**: the game queues its own writes every frame (`PlayerStatus.Life` / `MaxLife`
    sit in the Int queue), so an entry and a count written in two frames lost writes (seen: rupees, a Piece of
    Heart). Pipelined requests are served within one frame (six reads, one frame number): `Longshot._queue` sends
    read count / write entry / write the count's two low bytes / read back in one batch and checks them.
  - **Ammunition needs its own flag**: 20 bombs written with the bag stayed invisible until `IsGet.Item_Bomb` was set
    (the real bomb bag chest sets it, hash 0x2bb00768) **[game]**.
  - **Heart Containers: not working**. `PlayerStatus.MaxLife` + 4 plays the sound but goes back to 12: the game
    rewrites `Life` / `MaxLife` into GameData from Link's data every frame. The native module's note says max life
    is recomputed at an age change; there is no Heart Container counter (`PouchData.Obj_Heart_Container.StockNum`
    does not exist). To find.
  - **Items logged "nothing given"** (seen in game, 2026-11-24: Deku Shield, bottle), now written as the game does,
    **verified in the files, to validate in game**: shields (`TBox_Shield_*` counted as `Weapon_Shield_*`); bottles (no
    counter: first slot `PlayerStatus.AssignableItem.BottleInfo.Bottle<A-E>` whose `IsValid` is false, content in its
    Enum `BottleItem`, as `PouchAdd` 0x110d570 does; first use of the Enum write queue); songs (`IsGet.Item_Melody_*`
    only, no counter); Ruto's letter also sets `Get_StoneOfWater_GetRutoLetter` (the quest step itself is not
    advanced: reading the letter should do it). Magic jars still give nothing.
  - **Received items and derived values** (2026-11-25, **to validate in game**): strength, magic and double defense also
    write what the game derives (`PlayerStatus.LiftGrade`, `MPMax` / `MP`, an unnamed Bool); the first magic upgrade
    received is the single magic; rupees stop at the wallet's limit (200 / 500 / 1000).
  - An item logged "nothing given" is counted as received: it is not sent again unless an older save is loaded.
  - Not seen in game yet: Pieces of Heart (same problem expected), seeds with the Slingshot
    (`PouchData.Item_DekuSeed.StockNum` exists, not filled yet), swords, magic. No get-item window: the bridge prints
    the received item.
- No `GOAL` yet: the end of the game is not watched, so a Longshot player who finishes does not release items.
- The pipe and its JSON may change with Longshot versions (seen: rc.6 -> v3.0.0 kept them); the bridge warns when
  `status` is not `"protocol": 1`. Longshot now installs to `Games/Longshot/<channel>/<version>` (`stable/v3.0.0`,
  `rc/v3.0.0-rc.7`).

#### Tried and removed: received items given by a game scene (2026-11-20)

To get the chest's get-item animation, received items were given by a scene of our own: the bridge wrote the item's
number into a mailbox Int, a node added to Link's walk AI (`OneShotEventMemberRequestEventByEventName`, copied
from `EventProxyRequestActor`) requested an event, and the event gave the item with the game's pouch action
`EventTriggerAddOrRemovePouchContent` (Longshot v3.0.0). What was learnt (see also GAME_KNOWLEDGE, pitfalls):
- the request works, but only when Link **starts walking** (the walk module is entered); each run hides the HUD and
  stops Link for an instant, and an item the scene cannot give (a chest bundle such as `TBox_DekuNutBundle`) made it
  start again at every step;
- the get window (`GetPouchContent:GetPouchContentByActorName`) blocked inside the call (softlock) whatever the
  steps before it, the kind of event row or its `SubFlowList`; `IsGetEvent` = true on the pouch action showed nothing;
- GameData written inside a scene is queued too: a branch right after it reads the old value.
No animation came out of it and the scene disturbed play, so it was removed (user's decision): received items are
given by GameData writes (`mw_items.ItemGiver`), invisible in game, and the logs say what was received.

The same pipe-and-memory approach cannot drive Eden (no such pipe), so Eden keeps the native client.

## Coop (after the multiworld)

Same server, a room kind "coop": every player runs the same seed; a location found by one player gives its item to
all the others and is marked found for everyone (`CHECKED <location>`, new message), so that opening it again gives
nothing.
