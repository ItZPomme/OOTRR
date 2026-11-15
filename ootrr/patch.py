"""Patch JSON (lieu -> objet, avec les hash des coffres) et conversion en modifications du jeu."""

from __future__ import annotations

from typing import Any

from . import __version__
from .fill import Result
from . import keys as keys_mod
from .world import World

PATCH_FORMAT = "ootrr-patch"
PATCH_VERSION = 2


def _merge_events(*parts: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for part in parts:
        for flow, mapping in part.items():
            out.setdefault(flow, {}).update(mapping)
    return out


def _start_warp(world: World) -> list[str] | None:
    from .starting import spawn
    sp = spawn(world.settings)
    return [sp["banc"], sp["pos"]] if sp else None


def build_patch(world: World, result: Result, seed_hash: str) -> dict[str, Any]:
    chests = []
    rank = {name: i for i, name in enumerate(world.locations)}  # same order as the native kLocations
    for loc in sorted(world.shuffled_locations(), key=lambda l: l.name):
        item = result.placements[loc.name]
        chests.append({
            "location": loc.name,
            "index": rank[loc.name],
            "hashes": loc.hashes,
            "vanilla": loc.vanilla,
            "item": item,
            "event": loc.event,
            "conditional": loc.conditional,
            "pickup": loc.pickup,
            "scrub": loc.scrub,
            "skulltula": loc.skulltula,
            "shop": loc.shop,
            "shop_actor": loc.shop_actor,
            "price": loc.price,
            "ocarina": loc.ocarina,
            "gift": loc.gift,
            "key_dungeon": world.location_game_dungeon(loc),
        })
    key_events = keys_mod.foreign_events(chests)
    rsdb = world.rsdb_changes()
    for table, rows in keys_mod.rsdb_rows(key_events).items():
        rsdb.setdefault(table, {}).update(rows)
    return {
        "format": PATCH_FORMAT,
        "format_version": PATCH_VERSION,
        "generator_version": __version__,
        "target": "zelda-oot-remake-switch2",
        "seed": result.seed,
        "hash": seed_hash,
        "settings": world.settings,
        "start_flags": world.start_flags(),
        "event_skips": world.event_skips(),
        "timeline_skips": world.timeline_skips()[0],
        "timeline_fade_in": world.timeline_skips()[1],
        "rsdb_changes": rsdb,
        "key_events": {event: list(key) for event, key in key_events.items()},
        "pack_changes": world.pack_changes(),
        "start_items": world.start_items(result.placements),
        "rewards": {l.name: result.placements[l.name] for l in world.reward_locations()},
        "event_changes": _merge_events(world.reward_event_changes(result.placements),
                                       world.ocarina_event_changes(result.placements)),
        "gift_changes": {f: [list(e) for e in v] for f, v in world.gift_event_changes(result.placements).items()},
        "moat_items": list(world.moat_items(result.placements)),
        "song_gives": world.song_gives(result.placements),
        "ocarina_guard": not world.settings.get("shuffle_ocarinas"),
        "start_warp": _start_warp(world),
        "logic_patches": world.logic_patches(),
        "logic_ints": {m: [list(e) for e in v] for m, v in world.logic_ints().items()},
        "event_ints": {f: [list(e) for e in v] for f, v in world.event_ints().items()},
        "ingame_questions": world.ingame_questions(),
        "bool_exps": {k: [list(x) for x in v] for k, v in world.bool_exps().items()},
        "ainb_edits": world.ainb_edits(),
        "actor_changes": {str(h): c for h, c in world.actor_changes().items()},
        "extra_pickups": world.extra_pickups(),
        "ocarina_moat_gate": bool(world.settings.get("open_door_of_time")),
        "removed_actors": world.removed_actors(),
        "ground_native": world.ground_native,
        "chests": chests,
    }


def chest_changes(patch: dict[str, Any]) -> dict[int, dict]:
    """Modifications d'acteurs pour le ModBuilder : {hash: {champ: valeur ou None}}.

    Un coffre qui garde son objet d'origine n'est pas touché. Sinon on change
    Drop__DropActor, et on retire l'événement s'il appartenait à l'objet
    d'origine (sinon l'animation de l'ancien objet se joue, ex. l'épée dans le dos)."""
    changes: dict[int, dict] = {}
    for chest in patch["chests"]:
        if chest["item"] == chest["vanilla"] or chest.get("pickup") or chest.get("scrub") or chest.get("skulltula") or chest.get("shop"):
            continue
        change: dict[str, Any] = {"Drop__DropActor": chest["item"]}
        if chest["event"] == "drop":
            change["GetEventName"] = None
        key = keys_mod.chest_change(chest["item"], chest.get("key_dungeon"))
        if key:  # dungeon key: the game's key in its own dungeon, otherwise a "door key" + the chest event
            change.update(key)
        if chest.get("conditional"):
            # sinon le jeu donnerait l'objet de remplacement d'origine si le joueur a déjà l'objet testé
            change["Drop__CheckActor"] = None
            change["Drop__DropActor_Substitute"] = None
        for h in chest["hashes"]:
            changes[int(h)] = change
    return changes


SCRUB_FIELDS = ("ScrubBusiness_ShopItemActorName0", "ScrubBusiness_ShopItemActorName1",
                "ScrubBusiness_ShopItemActorName2")


def scrub_changes(patch: dict[str, Any], price: int | None = None) -> tuple[dict[int, dict], dict[str, int]]:
    """Peste Mojo mélangées : ({hash: champs de l'acteur}, {objet vendu: prix}). L'acteur garde son
    script (TalkEventName) ; le premier article devient l'objet placé, les autres disparaissent."""
    from .world import SCRUB_PRICE, shop_price

    changes: dict[int, dict] = {}
    sales: dict[str, int] = {}
    settings = patch.get("settings") or {}
    for loc in patch["chests"]:
        if not loc.get("scrub"):
            continue
        # scrub_prices: same price as the native module would compute for this seed and location
        sales[loc["item"]] = price or (shop_price(settings, int(patch.get("seed", 0)), loc["index"], SCRUB_PRICE,
                                                  "scrub_prices") if "index" in loc else SCRUB_PRICE)
        for h in loc["hashes"]:
            changes[int(h)] = {SCRUB_FIELDS[0]: loc["item"], SCRUB_FIELDS[1]: None, SCRUB_FIELDS[2]: None}
    return changes, sales


def skulltula_changes(patch: dict[str, Any], pickups: dict[str, str]) -> dict[int, dict]:
    """Skulltulas d'or : {hash: {"Drop__DropActor": acteur lâché}}. Objet qui a sa version au sol
    (cœur, rubis, jeton) : cette version ; sinon un objet ramassable sur mesure, ajouté à `pickups`
    (même numérotation que pickup_changes)."""
    native = patch.get("ground_native", {})
    changes: dict[int, dict] = {}
    made: dict[str, str] = {v: k for k, v in pickups.items()}
    for loc in patch["chests"]:
        if not loc.get("skulltula") or loc["item"] == loc["vanilla"]:
            continue
        if loc["item"] in native:
            actor = native[loc["item"]]
        elif loc["item"] in made:
            actor = made[loc["item"]]
        else:
            actor = f"{PICKUP_PREFIX}{len(pickups):03d}"
            pickups[actor] = loc["item"]
            made[loc["item"]] = actor
        for h in loc["hashes"]:
            changes[int(h)] = {"Drop__DropActor": actor}
    return changes


PICKUP_PREFIX = "Obj_OoTRR_Pickup_"


def pickup_changes(patch: dict[str, Any]) -> tuple[dict[int, dict], dict[str, str]]:
    """Cœurs posés au sol : (changements de type d'acteur {hash: {"Gyaml": ...}}, objets sur mesure {nom: objet}).

    Cœur, réceptacle ou rubis : on remet le vrai objet au sol du jeu. Autre objet : un objet
    ramassable sur mesure (copie du réceptacle) qui porte le nom de l'objet à donner."""
    native = patch.get("ground_native", {})
    changes: dict[int, dict] = {}
    pickups: dict[str, str] = {}
    for loc in patch["chests"]:
        if not loc.get("pickup") or loc["item"] == loc["vanilla"]:
            continue
        if loc["item"] in native:
            actor = native[loc["item"]]
        else:
            actor = f"{PICKUP_PREFIX}{len(pickups):03d}"
            pickups[actor] = loc["item"]
        for h in loc["hashes"]:
            changes[int(h)] = {"Gyaml": actor}
    return changes, pickups
