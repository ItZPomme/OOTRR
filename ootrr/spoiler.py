"""Spoiler log : parcours par sphères et objets requis pour finir."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from . import __version__
from .race import hash_symbols
from .fill import Result
from .keys import VANILLA_EVENT
from .search import EVENT_PREFIX, State, is_beatable
from .world import World


def seed_hash(world: World, result: Result) -> str:
    data = {"s": world.settings, "p": result.placements, "v": __version__}
    if result.starting_items:
        data["i"] = result.starting_items
    blob = json.dumps(data, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:10].upper()


def playthrough(world: World, result: Result) -> list[list[tuple[str, str]]]:
    """Sphères : à chaque étape, tout ce qui devient atteignable avec ce qu'on a déjà."""
    state = State(world, result.starting_items)
    spheres = []
    while not state.beaten():
        found = state.step(result.placements)
        if not found:
            break
        spheres.append([(loc, item) for loc, item in found
                        if world.is_progression(item)
                        or (loc.startswith(EVENT_PREFIX) and not item.startswith(VANILLA_EVENT))])
    return spheres


def required_items(world: World, result: Result, spheres) -> list[tuple[str, str]]:
    """Objets sans lesquels la seed devient impossible (« la voie du héros »)."""
    required = []
    for sphere in spheres:
        for loc, item in sphere:
            if loc.startswith(EVENT_PREFIX):
                continue
            trimmed = dict(result.placements)
            del trimmed[loc]
            if not is_beatable(world, trimmed, result.starting_items):
                required.append((loc, item))
    return required


def build(world: World, result: Result) -> dict[str, Any]:
    seed_id = seed_hash(world, result)
    spheres = playthrough(world, result)
    # logic = none: the seed may be impossible to finish; then no item is "required"
    beatable = is_beatable(world, result.placements, result.starting_items)
    required = required_items(world, result, spheres) if beatable else []
    areas: dict[str, dict[str, str]] = {}
    listed = world.shuffled_locations()
    if world.settings.get("shuffle_songs") == "shuffle":  # chants mélangés entre eux (hors pool)
        listed = listed + world.song_locations()
    for loc in sorted(listed, key=lambda l: (l.dungeon or l.region, l.name)):
        areas.setdefault(loc.dungeon or loc.region, {})[loc.name] = result.placements[loc.name]
    return {
        "version": __version__,
        "seed": result.seed,
        "hash": seed_id,
        "hash_symbols": hash_symbols(seed_id),  # the 5 symbols the desktop app draws
        "settings": world.settings,
        "starting_items": result.starting_items,
        "attempts": result.attempts,
        "beatable": beatable,
        "required": [{"location": l, "item": i, "shuffled": world.locations[l].shuffle} for l, i in required],
        "playthrough": [[{"location": l, "item": i} for l, i in sphere] for sphere in spheres],
        "locations": areas,
    }


def to_text(spoiler: dict[str, Any]) -> str:
    out = [
        f"Ocarina of Time Remake Randomizer v{spoiler['version']}",
        f"Seed : {spoiler['seed']}    Hash : {spoiler['hash']}",
        "Hash symbols : " + "  ·  ".join(spoiler.get("hash_symbols") or hash_symbols(spoiler["hash"])),
        "",
        "== Réglages ==",
    ]
    for k, v in spoiler["settings"].items():
        out.append(f"  {k:<22} {v}")
    from .starting import spawn
    sp = spawn(spoiler["settings"])
    age = "adulte" if spoiler["settings"].get("starting_age") == "adult" else "enfant"
    out.append(f"  Départ : Link {age}, " + (f"{sp['region']} ({sp['banc']} / {sp['pos']})" if sp else "maison de Link"))
    if spoiler.get("starting_items"):
        out.append("  Objets de départ : " + ", ".join(spoiler["starting_items"]))
    if not spoiler.get("beatable", True):
        out += ["", "!! Seed not beatable according to the logic (logic = none) !!"]
    out += ["", "== Objets requis dans les coffres mélangés (voie du héros) =="]
    for entry in spoiler["required"]:
        if entry["shuffled"]:
            out.append(f"  {entry['location']:<48} {entry['item']}")
    out += ["", "== Parcours par sphères (* = coffre mélangé) =="]
    shuffled = {name for locs in spoiler["locations"].values() for name in locs}
    for i, sphere in enumerate(spoiler["playthrough"], 1):
        out.append(f"  Sphère {i}")
        for entry in sphere:
            mark = "*" if entry["location"] in shuffled else " "
            out.append(f"   {mark}{entry['location']:<46} {entry['item']}")
    out += ["", "== Contenu des coffres mélangés =="]
    for area, locs in spoiler["locations"].items():
        out.append(f"  [{area}]")
        for loc, item in locs.items():
            out.append(f"    {loc:<46} {item}")
    return "\n".join(out) + "\n"
