"""Room graph of the key dungeons (data/key_graph.json) and the small keys each location needs in the worst case.

    python -m ootrr.tools.key_graph propose --romfs ROMFS        # proposes the links of the unchecked dungeons
    python -m ootrr.tools.key_graph counts --romfs ROMFS         # worst-case keys per location (checked dungeons)
    python -m ootrr.tools.key_graph counts --romfs ROMFS --write # ... and writes them in the rules

Rooms are the maps' `DefaultDungeonRoomIndex`. A link joins two rooms: "open" (both ways, no key), "locked" (a door
with chain locks: one small key, both ways once open), "boss" (the boss door: boss key, no small key) or "oneway"
(rooms[0] -> rooms[1] only, e.g. a hole). The
game does not store which rooms a door joins, so `propose` guesses them from the maps (door position and
orientation, rooms that touch); every guess must be checked by hand, then the dungeon set to "checked": true.

Worst case, for a location in room R: the player may open every locked door reachable without entering R before
the door that leads to R. So R needs 0 keys when it is reachable from the entrance by open links; otherwise
(locked doors reachable without entering R) + 1 when R itself is behind a locked door, at most the dungeon's keys.
A missing link makes this count too low (unsafe): that is why only checked graphs are used.
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import re
import sys
from pathlib import Path

from .. import keys as keys_mod

DATA = Path(__file__).resolve().parents[1] / "data"
GRAPH = DATA / "key_graph.json"
TOUCH = 5.0  # rooms whose actors come this close (metres, same height band) are proposed as an open link
# chain locks of the boss doors (boss key); every other chain lock is a small key door (one lock per side)
BOSS_LOCKS = {"Obj_DoorChainLock_A_02", "Dm_Obj_DoorChainLock_A_01"}
SAME_LEVEL = 4.0


def load_maps(romfs: Path, game: str) -> list[dict]:
    from ..formats.byml import read_byml
    from ..formats.zs import ZsCodec
    codec = ZsCodec(romfs)
    actors: list[dict] = []
    for path in sorted((romfs / "Banc" / game).glob(f"{game}_*.bcett.byml.zs")):
        actors += read_byml(codec.decompress(path)).get("Actors") or []
    return actors


def room_of(actor: dict) -> int | None:
    room = (actor.get("Dynamic") or {}).get("DefaultDungeonRoomIndex")
    return None if room is None else int(room)


# ---------------------------------------------------------------------------------------------------------- propose
def propose_links(actors: list[dict]) -> list[dict]:
    by_hash = {a["Hash"]: a for a in actors}
    points: dict[int, list] = collections.defaultdict(list)
    for a in actors:
        r = room_of(a)
        if r is not None and a.get("Translate") and "Door" not in a.get("Gyaml", ""):
            points[r].append(a["Translate"])

    def nearest(p, exclude) -> tuple[float, int] | None:
        best = None
        for r, pts in points.items():
            if r == exclude:
                continue
            for q in pts:
                if abs(q[1] - p[1]) <= SAME_LEVEL + 2:
                    d = math.dist((p[0], p[2]), (q[0], q[2]))
                    if best is None or d < best[0]:
                        best = (d, r)
        return best

    links: dict[tuple, dict] = {}
    rank = {"open": 0, "boss": 1, "locked": 2}
    for a in actors:
        gyaml = a.get("Gyaml", "")
        locks = [by_hash.get(l["Dst"], {}).get("Gyaml", "") for l in a.get("Links", [])]
        locks = [g for g in locks if "DoorChainLock" in g]
        is_door = (a.get("Name") in ("DungeonDoor", "SwitchShutterWithChainLock") or bool(locks)
                   or (gyaml.startswith("Obj_") and ("SwitchShutter" in gyaml or "_Door_" in gyaml)
                       and "Hinge" not in gyaml))  # Obj_Door_Hinge: a part of a door, not a door
        if not is_door or not a.get("Translate"):
            continue
        kind = "open"
        if locks:
            kind = "boss" if any(g in BOSS_LOCKS for g in locks) else "locked"
        room = room_of(a)
        first = (0.0, room) if room is not None else nearest(a["Translate"], None)
        if first is None:
            continue
        other = nearest(a["Translate"], first[1])
        if other is None:
            continue
        key = tuple(sorted((first[1], other[1])))
        if kind == "locked":  # each locked door is one key, even between the same two rooms
            key = key + (a["Hash"],)
        if key not in links or rank[kind] > rank[links[key]["door"]]:
            links[key] = {"rooms": list(key[:2]), "door": kind,
                          "why": f"{gyaml} {a['Hash']} in room {first[1]}, nearest other room {other[1]} at "
                                 f"{other[0]:.0f} m"}
    rooms = sorted(points)
    joined = {tuple(sorted(l["rooms"])) for l in links.values()}  # a door already joins them: no open link beside
    for i, r1 in enumerate(rooms):
        for r2 in rooms[i + 1:]:
            key = (r1, r2)
            if key in joined:
                continue
            best = min((math.dist((p[0], p[2]), (q[0], q[2])) for p in points[r1] for q in points[r2]
                        if abs(p[1] - q[1]) <= SAME_LEVEL), default=None)
            if best is not None and best <= TOUCH:
                links[key] = {"rooms": [r1, r2], "door": "open", "why": f"actors {best:.1f} m apart (no door found)"}
    locked_pairs = {tuple(sorted(l["rooms"])) for l in links.values() if l["door"] == "locked"}
    for l in links.values():
        if l["door"] == "open" and tuple(sorted(l["rooms"])) in locked_pairs:
            l["why"] = ("CHECK FIRST: a locked door joins the same rooms, this open link would bypass it; "
                        + l["why"])
    return sorted(links.values(), key=lambda l: (l["rooms"], l["door"]))


def write_graph(graph: dict) -> None:
    """key_graph.json with one link per line (easy to edit by hand)."""
    out = ["{", '  "_doc": ' + json.dumps(graph["_doc"], ensure_ascii=False, indent=4).replace("\n", "\n  ") + ",",
           '  "dungeons": {']
    names = list(graph["dungeons"])
    for i, name in enumerate(names):
        d = graph["dungeons"][name]
        out.append(f"    {json.dumps(name)}: {{")
        out.append(f'      "checked": {json.dumps(d["checked"])}, "entrance": {json.dumps(d["entrance"])},')
        out.append('      "links": [')
        for j, link in enumerate(d["links"]):
            out.append("        " + json.dumps(link, ensure_ascii=False) + ("," if j < len(d["links"]) - 1 else ""))
        out.append("      ]")
        out.append("    }" + ("," if i < len(names) - 1 else ""))
    out += ["  }", "}", ""]
    text = "\n".join(out)
    json.loads(text)
    GRAPH.write_text(text, encoding="utf-8", newline="\n")


DOC = [
    "Room graph of the key dungeons, for the worst-case small key counts (python -m ootrr.tools.key_graph).",
    "Rooms = DefaultDungeonRoomIndex of the maps (see the room plans). entrance = room where the player enters.",
    "links: rooms = [a, b]; door = open (both ways, no key), locked (chain-locked door: one small key), boss (the "
    "boss door: boss key, no small key) or oneway (from a to b only, e.g. a hole); why = how it was found (edit "
    "it freely).",
    "propose guesses the links from the maps (doors, rooms that touch): every guess must be checked by hand, missing "
    "links added (open passages, ladders, elevators, holes have no door), wrong ones removed. A missing link makes "
    "the counts too low. Then set checked to true: only checked dungeons get counts.",
]


def cmd_propose(romfs: Path) -> int:
    keys = keys_mod.load(DATA)
    graph = json.loads(GRAPH.read_text(encoding="utf-8")) if GRAPH.exists() else {"dungeons": {}}
    graph["_doc"] = DOC
    for name, kd in keys.items():
        old = graph["dungeons"].get(name)
        if old and old.get("checked"):
            print(f"{name}: checked, kept")
            continue
        links = propose_links(load_maps(romfs, kd.game))
        graph["dungeons"][name] = {"checked": False, "entrance": (old or {}).get("entrance", 0), "links": links}
        locked = sum(1 for l in links if l["door"] == "locked")
        print(f"{name}: {len(links)} links proposed, {locked} locked (the dungeon has "
              f"{len(kd.small) + len(kd.freestanding)} small keys)")
    graph["dungeons"] = {n: graph["dungeons"][n] for n in keys if n in graph["dungeons"]}
    write_graph(graph)
    print(f"written {GRAPH}")
    return 0


# ----------------------------------------------------------------------------------------------------------- counts
def worst_case(entrance: int, links: list[dict], room: int, total: int) -> int:
    """Small keys needed to surely reach room `room` (see the module doc)."""
    def reach(allow_locked: bool, forbid: int | None) -> set[int]:
        seen, todo = {entrance}, [entrance]
        while todo:
            r = todo.pop()
            for l in links:
                a, b = l["rooms"]
                if l["door"] == "locked" and not allow_locked:
                    continue
                for src, dst in ((a, b), (b, a)) if l["door"] != "oneway" else ((a, b),):
                    if src == r and dst not in seen and dst != forbid:
                        seen.add(dst)
                        todo.append(dst)
        return seen

    if room == entrance or room in reach(False, None):
        return 0
    if room not in reach(True, None):
        return total  # not joined to the entrance in the graph: a link is missing, stay prudent
    seen = reach(True, room)
    doors = [l for l in links if l["door"] == "locked" and room not in l["rooms"]
             and any(r in seen for r in l["rooms"])]
    open_into = any(l["door"] != "locked" and room in l["rooms"] and
                    (l["rooms"][0] in seen if l["door"] == "oneway" else any(r in seen for r in l["rooms"] if r != room))
                    for l in links)
    return min(total, len(doors) + (0 if open_into else 1))


def location_rooms(romfs: Path, kd) -> dict[str, int | None]:
    """{location or key chest: room} for the locations of a key dungeon (rooms read in the maps by actor hash)."""
    from ..world import World
    from .. import settings
    world = World(settings.build({"small_keys": "any_dungeon", "boss_keys": "any_dungeon"}))
    rooms = {a["Hash"]: room_of(a) for a in load_maps(romfs, kd.game)}
    out = {}
    for loc in world.locations.values():
        if loc.key_dungeon == kd.name:
            found = [rooms.get(h) for h in loc.hashes if rooms.get(h) is not None]
            out[loc.name] = found[0] if found else None
    return out


def set_count(text: str, line_key: str, dungeon: str, n: int) -> tuple[str, bool]:
    """Sets has(Small_Key_<dungeon>, N) on the line holding line_key (a "name": or a hash)."""
    name = keys_mod.logic_name(keys_mod.SMALL, dungeon)
    lines = text.split("\n")
    hits = [i for i, l in enumerate(lines) if line_key in l]
    if len(hits) != 1:
        return text, False
    i = hits[0]
    new = re.sub(rf"has\(\s*{name}\s*,\s*\d+\s*\)", f"has({name}, {n})", lines[i])
    changed = new != lines[i]
    lines[i] = new
    return "\n".join(lines), changed


def cmd_counts(romfs: Path, write: bool) -> int:
    keys = keys_mod.load(DATA)
    graph = json.loads(GRAPH.read_text(encoding="utf-8"))["dungeons"]
    files = {p: p.read_text(encoding="utf-8") for p in [DATA / "keys.json", *sorted((DATA / "world").glob("*.json"))]}
    changes = 0
    for name, kd in keys.items():
        g = graph.get(name)
        if not g or not g.get("checked"):
            print(f"{name}: graph not checked, skipped")
            continue
        total = len(kd.small) + len(kd.freestanding)
        locked = sum(1 for l in g["links"] if l["door"] == "locked")
        if locked != total:
            print(f"{name}: warning, {locked} locked doors in the graph for {total} small keys")
        print(f"== {name} (entrance room {g['entrance']}, {total} keys)")
        hash_of = {kd.small_location(i): k["hash"] for i, k in enumerate(kd.small)}
        if kd.boss_key:
            hash_of[kd.boss_location] = kd.boss_key["hash"]
        joined = {r for l in g["links"] for r in l["rooms"]} | {g["entrance"]}
        for loc, room in sorted(location_rooms(romfs, kd).items(), key=lambda x: (x[1] is None, x[1] or 0, x[0])):
            n = total if room is None else worst_case(g["entrance"], g["links"], room, total)
            why = ("no room in the maps: all the keys" if room is None else
                   "room not in the graph: all the keys" if room not in joined else "")
            print(f"  {n}  room {room if room is not None else '?':>3}  {loc}" + (f"  ({why})" if why else ""))
            if not write:
                continue
            key = str(hash_of[loc]) if loc in hash_of else json.dumps(loc) + ":"
            for path, text in files.items():
                if key in text:
                    files[path], changed = set_count(text, key, name, n)
                    changes += changed
                    break
    if write:
        for path, text in files.items():
            if text != path.read_text(encoding="utf-8"):
                json.loads(text)
                path.write_text(text, encoding="utf-8", newline="\n")
        print(f"{changes} counts changed")
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("command", choices=["propose", "counts"])
    p.add_argument("--romfs", required=True, type=Path)
    p.add_argument("--write", action="store_true", help="counts: write them in the rules")
    a = p.parse_args(argv)
    return cmd_propose(a.romfs) if a.command == "propose" else cmd_counts(a.romfs, a.write)


if __name__ == "__main__":
    sys.exit(main())
