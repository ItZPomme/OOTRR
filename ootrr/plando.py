"""Plandomizer: a seed where the player chooses some placements, the start and the settings.

A plando file is JSON:

    {
      "format": 1,
      "seed": "1234",                                   # optional: placement of the other items
      "settings": {"starting_age": "adult", ...},       # optional: same names as settings.py
      "spawn": {"age": "adult", "region": "Hyrule Field"},   # optional: one of data/spawns.json
      "placements": {"HF Grotto Chest 1": "Item_Hookshot", ...}
    }

`python -m ootrr --plando FILE [--romfs ROMFS --install]`; `python -m ootrr.tools.plando_app` edits these files.

Placements may target the shuffled locations of these settings (the pool), and, when they are shuffled, the boss
rewards (`shuffle_rewards = shuffled`: a stone or a medallion) and the song locations (`shuffle_songs = shuffle`: a
song). An item taken from the pool leaves it; an item that is not in the pool (a second Hookshot...) replaces a rupee
of the pool. The rest is placed by the normal generator, with the logic: a plando that makes the seed impossible
fails like any seed. PC mod only: the in-game menu generates its own seed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import starting

FORMAT = 1


class PlandoError(ValueError):
    pass


def load(path: str | Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))  # files saved by Windows editors may have a BOM
    except (OSError, json.JSONDecodeError) as exc:
        raise PlandoError(f"plando file {path}: {exc}") from None
    if not isinstance(data, dict) or data.get("format", FORMAT) != FORMAT:
        raise PlandoError(f"plando file {path}: not a plando (format {FORMAT})")
    for key, kind in (("settings", dict), ("placements", dict)):
        if not isinstance(data.get(key, {}), kind):
            raise PlandoError(f"plando file {path}: \"{key}\" must be an object")
    return data


def spawn_choices(age: str) -> list[dict]:
    """Start points of an age (data/spawns.json), each with its spawn_point value."""
    return [dict(sp, spawn_point=k) for k, sp in enumerate(starting.spawns(), 1) if sp["age"] == age]


def spawn_point(spawn: dict | None, age: str) -> int | None:
    """spawn_point of a plando "spawn" entry, or None (the normal start of that age)."""
    if not spawn:
        return None
    if spawn.get("age", age) != age:
        raise PlandoError(f"spawn {spawn.get('region')}: {spawn.get('age')} start point, but Link starts {age}")
    for sp in spawn_choices(age):
        if sp["region"] == spawn.get("region") and (not spawn.get("pos") or sp["pos"] == spawn["pos"]):
            return sp["spawn_point"]
    raise PlandoError(f"spawn {spawn.get('region')}: no {age} start point there (data/spawns.json)")


def apply_start(settings: dict[str, Any], spawn: dict | None) -> dict[str, Any]:
    """Settings already resolved by starting.resolve, with the plando start point."""
    k = spawn_point(spawn, settings.get("starting_age", "child"))
    if k is None:
        return settings
    return dict(settings, spawn_point=k)


def placeable(world) -> dict[str, str]:
    """Locations a plando can fill with these settings: name -> "pool" | "reward" | "song"."""
    out = {l.name: "pool" for l in world.shuffled_locations()}
    if world.settings.get("shuffle_rewards") == "shuffled":
        out.update({l.name: "reward" for l in world.reward_locations()})
    if world.settings.get("shuffle_songs") == "shuffle":
        out.update({l.name: "song" for l in world.song_locations()})
    return out


def validate(world, placements: dict[str, str]) -> list[str]:
    """Problems of a plando with these settings (empty = valid)."""
    errors = []
    kinds = placeable(world)
    rewards = [l.vanilla for l in world.reward_locations()]
    songs = [l.vanilla for l in world.song_locations()]
    for kind, allowed in (("reward", rewards), ("song", songs)):
        chosen = [item for name, item in placements.items() if kinds.get(name) == kind]
        for item in set(chosen) & set(allowed):  # a wrong item is reported below, location by location
            if chosen.count(item) > allowed.count(item):
                errors.append(f"{item} placed {chosen.count(item)} times on {kind} locations")
    for name, item in placements.items():
        loc = world.locations.get(name)
        if loc is None:
            errors.append(f"{name}: unknown location")
        elif name not in kinds:
            errors.append(f"{name}: not shuffled with these settings (it keeps {loc.vanilla})")
        elif item not in world.items:
            errors.append(f"{name}: unknown item {item}")
        elif kinds[name] == "reward" and item not in rewards:
            errors.append(f"{name}: a boss reward location only takes a stone or a medallion, not {item}")
        elif kinds[name] == "song" and item not in songs:
            errors.append(f"{name}: with shuffle_songs = shuffle, a song location only takes a song, not {item}")
        elif kinds[name] == "pool" and not world.can_place(item, loc):
            errors.append(f"{name}: {item} cannot be placed there (placement rules: ground item, scrub, "
                          "dungeon item...)")
    return errors


def take_from_pool(pool: list[tuple[str, str | None]], item: str) -> bool:
    """Removes the item from the pool, or a rupee in its place (an extra copy); False if neither is there."""
    for i, (name, _) in enumerate(pool):
        if name == item:
            del pool[i]
            return True
    for i, (name, dungeon) in enumerate(pool):
        if dungeon is None and name.startswith("TBox_Rupee_"):
            del pool[i]
            return True
    return False


def save(path: str | Path, seed: str | None, settings: dict[str, Any], spawn: dict | None,
         placements: dict[str, str]) -> None:
    data: dict[str, Any] = {"format": FORMAT}
    if seed:
        data["seed"] = str(seed)
    data["settings"] = settings
    if spawn:
        data["spawn"] = spawn
    data["placements"] = dict(sorted(placements.items()))
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
