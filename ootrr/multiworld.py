"""Multiworld generation: one world per player, one shared fill.

Each player has their own World (their own settings) and their own seed in the game; an item placed in a location
of world A may belong to player B: when A finds it, the server sends it to B (see docs/MULTIWORLD.md). Placements
are therefore (owner, item) pairs, `owner` = index of the player who receives the item.

    python -m ootrr.multiworld --players 2 --seed 1234 -o output/mw.json
    python -m ootrr.multiworld --config players.json --seed 1234 -o output/mw.json

Fill: same method as `ootrr.fill` (assumed fill), over every world at once.
- Per world first (`fill.prefill`): fixed locations, shuffled rewards and songs, dungeon keys, maps and compasses.
  These stay in their own world.
- Progression items of every world: assumed fill over the locations of every world. The reachability check sweeps
  all worlds together (`MultiState`): an item found in world A for player B is added to B's inventory.
- The rest: anywhere that accepts it.

Child / adult (`search.State`): until Link can go back in time, the child only uses the items found as child. An item
received from another world comes whenever the other player finds it, whatever the receiver's age: it only counts
for the receiver's adult (and for both once he can go back). This is conservative (never a seed that needs a child
to use an item he may receive too late).

Not supported yet: plando and `logic = none` (refused by `generate`).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from . import __version__, settings as settings_mod
from .fill import FillError, prefill
from .patch import progressive_location
from .search import EVENT_PREFIX, State
from .world import DATA_DIR, Location, World

FORMAT = 1  # multiworld file format; bump it when the file changes
MAX_PLAYERS = 16

Placed = tuple[int, str]  # (owner = index of the receiving player, item)

# ---- game side (PC-built mod, see docs/MULTIWORLD.md) ----
# A chest holding another player's item gives this placeholder (not put in the pouch, "door key" text) and runs its
# own chest event (copy of the boss key chest script, like a key of another dungeon) that adds 1 to a saved Int per
# location: the bridge sees the Int change and tells the server.
REMOTE_PLACEHOLDER = "Obj_MiniGame_SmallKey"
RECEIVED_COUNTER = "OoTRR.MW.Received"  # saved Int: received items applied by the bridge (protocol SYNC)


def location_counter(rank: int) -> str:
    """Saved Int raised when the location of rank `rank` (index in World.locations) holding a remote item is found."""
    return f"OoTRR.MW.L{rank:04d}"


def remote_event(rank: int) -> str:
    """Chest event (RSDB EventSetting row and script name) of that location."""
    return f"OoTRR_MW_L{rank:04d}"


def remote_actor(rank: int) -> str:
    """Item dropped by that location's chest: a copy of the placeholder with its own get texts
    ("You found Pomme's Hookshot!", `ModBuilder._write_mw_actors`)."""
    return f"OoTRR_MW_A{rank:04d}"


def can_hold_remote(loc: Location) -> bool:
    """Locations that may hold another player's item: plain chests whose event can be replaced, as for a key of
    another dungeon (`World._can_hold_key`), not conditional (their AI picks the item)."""
    return (loc.is_chest and loc.kind == "general" and not loc.gift and not loc.ocarina and not loc.conditional
            and loc.event != "keep")


@dataclass
class Player:
    name: str
    settings: dict[str, Any]


@dataclass
class MultiResult:
    seed: int
    attempts: int
    players: list[Player]
    placements: list[dict[str, Placed]]  # per world: location -> (owner, item)
    unreachable: list[list[str]] = field(default_factory=list)
    version: str = __version__  # version that made it (part of the hash: a running game survives an update)

    def own_items(self, world: int) -> dict[str, str]:
        """Locations of `world` whose item stays in it (the rest goes to other players)."""
        return {loc: item for loc, (owner, item) in self.placements[world].items() if owner == world}

    def sent(self, world: int) -> dict[str, Placed]:
        """Locations of `world` whose item goes to another player."""
        return {loc: p for loc, p in self.placements[world].items() if p[0] != world}

    def received(self, world: int) -> list[tuple[int, str, str]]:
        """Items of player `world` placed in other worlds: (finder, location, item)."""
        return [(k, loc, item) for k, places in enumerate(self.placements) if k != world
                for loc, (owner, item) in places.items() if owner == world]


class MultiState:
    """One `search.State` per world, swept together: an item found anywhere goes to its owner."""

    def __init__(self, worlds: list[World], assumed: Iterable[Placed] = ()) -> None:
        self.worlds = worlds
        self.states = [State(w) for w in worlds]
        for owner, item in assumed:
            self.states[owner].receive(item, True)  # assumed owned from the start, as in State(world, items)

    def step(self, placements: list[Mapping[str, Placed]]) -> list[tuple[int, str, Placed]]:
        """One sphere over every world: (world where it was found, location or event, (owner, item))."""
        found: list[tuple[int, str, Placed]] = []
        taken: list[tuple[int, str, Placed, bool]] = []
        for k, state in enumerate(self.states):
            for where, placed, child in state.reachable(placements[k]):
                if where.startswith(EVENT_PREFIX):
                    placed = (k, placed)  # events stay in their world
                taken.append((k, where, placed, child))
        for k, where, (owner, item), child in taken:
            self.states[k].mark(where, item)
            self.states[owner].receive(item, child and owner == k)
            found.append((k, where, (owner, item)))
        for state in self.states:
            state.update_return()
        return found

    def sweep(self, placements: list[Mapping[str, Placed]]) -> "MultiState":
        while self.step(placements):
            pass
        return self

    def can_reach(self, world: int, loc: Location) -> bool:
        return self.states[world].can_reach(loc)

    def beaten(self) -> bool:
        return all(s.beaten() for s in self.states)


def _candidates(worlds: list[World], item: Placed, locations: list[tuple[int, Location]],
                placements: list[dict[str, Placed]], assumed: list[Placed]) -> list[tuple[int, Location]]:
    without = list(assumed)
    without.remove(item)
    state = MultiState(worlds, without).sweep(placements)
    return [(k, l) for k, l in locations
            if l.name not in placements[k] and _accepts(worlds, k, l, item) and state.can_reach(k, l)]


def _accepts(worlds: list[World], k: int, loc: Location, item: Placed) -> bool:
    """Location `loc` of world `k` may hold `item`: the world's own rules, and another player's item only in a
    chest that can hold one (`can_hold_remote`). Items of a progressive chain with a logic item only go where the PC-built mod gives
    the next step (chests, gifts): a ground item gives its item as placed (seen in game, 2026-11-24: the biggest
    quiver on Gohma's heart, no bow)."""
    if not worlds[k].can_place(item[1], loc) or not (item[0] == k or can_hold_remote(loc)):
        return False
    return progressive_location(loc) or not any(item[1] in chain for chain in strict_chains(worlds[k]))


def strict_chains(world: World) -> list[list[str]]:
    """Progressive chains with an item the logic uses."""
    return [c for c in world.progressive if any(world.is_progression(i) for i in c)]


def _assumed_fill(worlds: list[World], rng: random.Random, items: list[Placed], locations: list[tuple[int, Location]],
                  placements: list[dict[str, Placed]]) -> None:
    """Assumed fill over every world. Unlike `fill._assumed_fill` (the item with the fewest possible locations
    first, one sweep per remaining item and per step), items are placed in random order with one sweep each, as
    Archipelago does: the single-world way grows as N^3 with N players (minutes for 4). A dead end raises
    FillError and `generate` starts a new attempt."""
    items = list(items)
    rng.shuffle(items)
    assumed = list(items)
    while items:
        item = items.pop()
        candidates = _candidates(worlds, item, locations, placements, assumed)
        if not candidates:
            raise FillError(f"no location left for {item[1]} (player {item[0] + 1})")
        assumed.remove(item)
        k, loc = rng.choice(candidates)
        placements[k][loc.name] = item


def _attempt(worlds: list[World], rng: random.Random) -> list[dict[str, Placed]]:
    placements: list[dict[str, Placed]] = []
    locations: list[tuple[int, Location]] = []
    progression: list[Placed] = []
    rest: list[Placed] = []
    for k, world in enumerate(worlds):
        own, shuffled, free_pool = prefill(world, rng)
        placements.append({loc: (k, item) for loc, item in own.items()})
        locations += [(k, l) for l in shuffled]
        progression += [(k, i) for i in free_pool if world.is_progression(i)]
        rest += [(k, i) for i in free_pool if not world.is_progression(i)]

    _assumed_fill(worlds, rng, progression, locations, placements)

    empty = [(k, l) for k, l in locations if l.name not in placements[k]]
    if len(empty) != len(rest):
        raise FillError(f"pool mismatch: {len(rest)} items for {len(empty)} locations")
    rng.shuffle(rest)
    # locations that only take their own world's items (not plain chests) first, from their world's rest:
    # otherwise the last ones may only find other players' items left
    for k in range(len(worlds)):
        own_only = [l for kk, l in empty if kk == k and not can_hold_remote(l)]
        own_only.sort(key=lambda l: sum(p[0] == k and _accepts(worlds, k, l, p) for p in rest))
        for loc in own_only:
            # shuffled Deku Scrubs accept little else than quivers and bullet bags: as placed rather than no seed
            # (the bow and the slingshot themselves are progression, placed above)
            fits = ([p for p in rest if p[0] == k and _accepts(worlds, k, loc, p)]
                    or [p for p in rest if p[0] == k and worlds[k].can_place(p[1], loc)])
            if not fits:
                raise FillError(f"no item of player {k + 1} left for {loc.name}")
            p = rng.choice(fits)
            rest.remove(p)
            placements[k][loc.name] = p
    empty = [(k, l) for k, l in empty if l.name not in placements[k]]
    rest.sort(key=lambda p: sum(_accepts(worlds, k, l, p) for k, l in empty))
    for p in rest:
        free = [(k, l) for k, l in empty if l.name not in placements[k] and _accepts(worlds, k, l, p)]
        if not free:
            raise FillError(f"no location left for {p[1]} (player {p[0] + 1})")
        k, loc = rng.choice(free)
        placements[k][loc.name] = p
    return placements


def check(worlds: list[World], placements: list[dict[str, Placed]]) -> tuple[bool, list[list[str]]]:
    state = MultiState(worlds).sweep(placements)
    unreachable = [sorted(set(w.locations) - s.collected) for w, s in zip(worlds, state.states)]
    return state.beaten(), unreachable


def build_worlds(players: list[Player], data_dir: Path | str = DATA_DIR) -> list[World]:
    if not 2 <= len(players) <= MAX_PLAYERS:
        raise ValueError(f"a multiworld needs 2 to {MAX_PLAYERS} players")
    names = [p.name for p in players]
    if len(set(names)) != len(names) or any(not n.strip() for n in names):
        raise ValueError("player names must be unique and not empty")
    worlds = []
    for p in players:
        if p.settings.get("logic") == "none":
            raise ValueError(f"{p.name}: logic = none is not supported in a multiworld")
        worlds.append(World(p.settings, data_dir))
    return worlds


def generate(players: list[Player], seed: int, max_attempts: int = 20,
             data_dir: Path | str = DATA_DIR, worlds: list[World] | None = None) -> MultiResult:
    worlds = worlds or build_worlds(players, data_dir)
    rng = random.Random(seed)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            placements = _attempt(worlds, rng)
        except FillError as exc:
            last_error = exc
            continue
        beaten, unreachable = check(worlds, placements)
        if not beaten:
            last_error = FillError("multiworld not beatable")
            continue
        bad = [(p.name, u) for p, w, u in zip(players, worlds, unreachable)
               if w.settings["accessibility"] == "all" and u]
        if bad:
            last_error = FillError(f"{bad[0][0]}: {len(bad[0][1])} unreachable locations, e.g. {bad[0][1][0]}")
            continue
        return MultiResult(seed, attempt, players, placements, unreachable)
    raise FillError(f"failed after {max_attempts} attempts: {last_error}")


# ---- file -------------------------------------------------------------------------------------------------------

def room_hash(result: MultiResult) -> str:
    """Identifies the multiworld: the server refuses a game whose seed has another hash."""
    blob = json.dumps({"p": [[p.name, p.settings] for p in result.players],
                       "l": [sorted(([loc, o, i] for loc, (o, i) in places.items())) for places in result.placements],
                       "v": result.version}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10].upper()


def playthrough(worlds: list[World], result: MultiResult) -> list[list[dict[str, Any]]]:
    """Spheres over every world (progression items and events only)."""
    state = MultiState(worlds)
    spheres = []
    while not state.beaten():
        found = state.step(result.placements)
        if not found:
            break
        spheres.append([{"world": k, "location": where, "owner": owner, "item": item}
                        for k, where, (owner, item) in found
                        if worlds[owner].is_progression(item) or where.startswith(EVENT_PREFIX)])
    return spheres


def to_json(result: MultiResult, worlds: list[World] | None = None) -> dict[str, Any]:
    worlds = worlds or [World(p.settings) for p in result.players]
    return {
        "format": FORMAT,
        "version": result.version,
        "seed": result.seed,
        "hash": room_hash(result),
        "attempts": result.attempts,
        "players": [{"name": p.name, "settings": p.settings,
                     "placements": {loc: [owner, item] for loc, (owner, item) in sorted(places.items())}}
                    for p, places in zip(result.players, result.placements)],
        "playthrough": playthrough(worlds, result),
    }


def from_json(data: dict[str, Any]) -> MultiResult:
    if data.get("format") != FORMAT:
        raise ValueError(f"multiworld file format {data.get('format')}, expected {FORMAT}")
    players = [Player(p["name"], p["settings"]) for p in data["players"]]
    placements = [{loc: (int(o), item) for loc, (o, item) in p["placements"].items()} for p in data["players"]]
    return MultiResult(int(data["seed"]), int(data.get("attempts", 1)), players, placements,
                       version=str(data.get("version", __version__)))


def load(path: str | Path) -> MultiResult:
    with Path(path).open(encoding="utf-8") as fh:
        return from_json(json.load(fh))


def to_text(data: dict[str, Any]) -> str:
    names = [p["name"] for p in data["players"]]
    out = [f"Ocarina of Time Remake Randomizer v{data['version']} - multiworld",
           f"Seed: {data['seed']}    Hash: {data['hash']}    Players: {', '.join(names)}", ""]
    width = max(len(n) for n in names) + 2
    for i, sphere in enumerate(data["playthrough"], 1):
        out.append(f"Sphere {i}")
        for e in sphere:
            to = "" if e["owner"] == e["world"] else f" -> {names[e['owner']]}"
            out.append(f"  {'[' + names[e['world']] + ']':<{width}} {e['location']:<46} {e['item']}{to}")
    for k, p in enumerate(data["players"]):
        out += ["", f"== {p['name']}'s world =="]
        for loc, (owner, item) in p["placements"].items():
            to = "" if owner == k else f"   -> {names[owner]}"
            out.append(f"  {loc:<46} {item}{to}")
    return "\n".join(out) + "\n"


# ---- per-player mod ---------------------------------------------------------------------------------------------

SLOT_FORMAT = 1  # slot data file format (what a joiner receives); bump it when it changes


@dataclass
class SlotData:
    """What one player needs, without the other worlds (no spoiler of the others): their mod (`slot_patch`) and
    their bridge (`remote_watch`) are built from it. The server sends it to a joiner (`tools.mw_server`)."""
    room_hash: str
    slot: int  # index from 0
    names: list[str]
    settings: dict[str, Any]
    seed: int
    attempts: int
    placements: dict[str, Placed]  # this player's world: location -> (owner, item)

    def sent(self) -> dict[str, Placed]:
        return {loc: p for loc, p in self.placements.items() if p[0] != self.slot}


def slot_data(result: MultiResult, slot: int) -> SlotData:
    return SlotData(room_hash(result), slot, [p.name for p in result.players], result.players[slot].settings,
                    result.seed, result.attempts, dict(result.placements[slot]))


def slot_to_json(data: SlotData) -> dict[str, Any]:
    return {"slot_format": SLOT_FORMAT, "version": __version__, "hash": data.room_hash, "slot": data.slot + 1,
            "names": data.names, "settings": data.settings, "seed": data.seed, "attempts": data.attempts,
            "placements": {loc: [o, i] for loc, (o, i) in sorted(data.placements.items())}}


def slot_from_json(raw: dict[str, Any]) -> SlotData:
    if raw.get("slot_format") != SLOT_FORMAT:
        raise ValueError(f"player data format {raw.get('slot_format')}, expected {SLOT_FORMAT}")
    return SlotData(str(raw["hash"]), int(raw["slot"]) - 1, [str(n) for n in raw["names"]], dict(raw["settings"]),
                    int(raw["seed"]), int(raw.get("attempts", 1)),
                    {loc: (int(o), str(i)) for loc, (o, i) in raw["placements"].items()})


def load_slot(path: str | Path, slot: int | None = None) -> SlotData:
    """A player's data from either file: a player data file (from joining), or the whole multiworld file and the
    player number (from 1)."""
    with Path(path).open(encoding="utf-8") as fh:
        raw = json.load(fh)
    if "slot_format" in raw:
        data = slot_from_json(raw)
        if slot is not None and slot - 1 != data.slot:
            raise ValueError(f"this file is player {data.slot + 1}'s, not player {slot}'s")
        return data
    if slot is None:
        raise ValueError("a multiworld file needs the player number (--slot)")
    result = from_json(raw)
    if not 1 <= slot <= len(result.players):
        raise ValueError(f"player 1 to {len(result.players)}")
    return slot_data(result, slot - 1)


def slot_patch(source: MultiResult | SlotData, slot: int | None = None, world: World | None = None) -> dict[str, Any]:
    """The build patch (`patch.build_patch`) of one player's world: own items as in a solo seed; a location
    holding another player's item gets the placeholder and its own chest event (`chests[i]["remote"]`,
    `patch["mw_events"]`); `patch["multiworld"]` tells the bridge what to watch. `source`: the whole result and
    the player's index, or the player's data."""
    from .fill import Result
    from .patch import build_patch

    data = source if isinstance(source, SlotData) else slot_data(source, slot)
    world = world or World(data.settings)
    placements = {loc: (item if owner == data.slot else REMOTE_PLACEHOLDER)
                  for loc, (owner, item) in data.placements.items()}
    patch = build_patch(world, Result(data.seed, data.attempts, placements), f"{data.room_hash}-{data.slot + 1}",
                        remote_chains=True)
    remote = data.sent()
    events: dict[str, str] = {}
    actors: dict[str, dict[str, str]] = {}
    watch = remote_watch(data, world=world)
    for chest in patch["chests"]:
        placed = remote.get(chest["location"])
        if placed is None:
            continue
        rank = chest["index"]
        chest["remote"] = {"owner": placed[0], "item": placed[1], "event": remote_event(rank),
                           "actor": remote_actor(rank)}
        events[remote_event(rank)] = location_counter(rank)
        actors[remote_actor(rank)] = {"owner": data.names[placed[0]], "item": placed[1]}
    if len(events) != len(remote):
        raise ValueError(f"player {data.slot + 1}: {len(remote) - len(events)} remote items outside the chests")
    patch["mw_events"] = events
    patch["mw_actors"] = actors
    for table, rows in mw_rsdb_rows(events).items():
        patch["rsdb_changes"].setdefault(table, {}).update(rows)
    patch["multiworld"] = {"hash": data.room_hash, "slot": data.slot + 1, "players": data.names,
                           "received_counter": RECEIVED_COUNTER, "locations": watch}
    return patch


def fixed_chains(data: SlotData, world: World | None = None) -> list[str]:
    """First steps of the chains whose items this player's mod gives as placed (`patch.progressive_chains`): the
    bridge must do the same with the received copies. Otherwise: Longshot received first (given as a Hookshot),
    then the Hookshot chest, and the logic counts a Longshot. Multiworlds generated since 2026-11-24 have none."""
    world = world or World(data.settings)
    chains = {c[0]: c for c in world.progressive if c[0] in world.progressive_logic}
    return [first for first, chain in chains.items()
            if any(owner == data.slot and item in chain and not progressive_location(world.locations[name])
                   for name, (owner, item) in data.placements.items()
                   if world.locations[name].shuffle)]


def remote_watch(source: MultiResult | SlotData, slot: int | None = None,
                 world: World | None = None) -> dict[str, str]:
    """{saved Int raised by the mod: location} for the locations of one player's world holding another player's
    item (rank = index in World.locations, as patch.build_patch)."""
    data = source if isinstance(source, SlotData) else slot_data(source, slot)
    world = world or World(data.settings)
    rank = {name: i for i, name in enumerate(world.locations)}
    return {location_counter(rank[loc]): loc for loc in sorted(data.sent())}


def mw_rsdb_rows(events: dict[str, str]) -> dict[str, dict[str, dict]]:
    """RSDB rows of the remote chest events: copies of the boss key chest event, own script (as `keys.rsdb_rows`)."""
    from . import keys as keys_mod
    if not events:
        return {}
    setting = {e: {"__new": True, "__copy_from": keys_mod.TEMPLATE_EVENT,
                   "FlowchartFileName": f"Work/Event/EventFlow/{e}.evfc"} for e in events}
    analyzed = {e: {"__new": True, "__copy_from": keys_mod.TEMPLATE_EVENT} for e in events}
    return {"EventSetting": setting, "GameAnalyzedEventInfo": analyzed}


# ---- command line -----------------------------------------------------------------------------------------------

def _players_from_args(args) -> list[Player]:
    if args.config:
        with Path(args.config).open(encoding="utf-8") as fh:
            raw = json.load(fh)
        return [Player(str(p["name"]), settings_mod.build(p.get("settings") or {})) for p in raw["players"]]
    names = args.names.split(",") if args.names else [f"Player {i + 1}" for i in range(args.players)]
    if args.names and args.players and len(names) != args.players:
        raise ValueError("--names must give one name per player")
    return [Player(n.strip(), settings_mod.build({})) for n in names]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m ootrr.multiworld", description="Generate a multiworld seed.")
    ap.add_argument("--players", type=int, default=2, help="number of players (default settings for everyone)")
    ap.add_argument("--names", help="player names, comma separated")
    ap.add_argument("--config", help='JSON file: {"players": [{"name": ..., "settings": {...}}, ...]}')
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("-o", "--output", default=None, help="multiworld file to write (default output/mw_<seed>.json)")
    args = ap.parse_args(argv)
    seed = args.seed if args.seed is not None else random.SystemRandom().randrange(1, 10**9)
    try:
        players = _players_from_args(args)
        worlds = build_worlds(players)
        result = generate(players, seed, worlds=worlds)
    except (ValueError, FillError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    data = to_json(result, worlds)
    out = Path(args.output or f"output/mw_{seed}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    out.with_suffix(".txt").write_text(to_text(data), encoding="utf-8")
    sent = [len(result.sent(k)) for k in range(len(players))]
    print(f"multiworld {data['hash']} (seed {seed}, attempt {result.attempts}): "
          + ", ".join(f"{p.name} sends {n}" for p, n in zip(players, sent)))
    print(f"written: {out} (+ .txt spoiler)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
