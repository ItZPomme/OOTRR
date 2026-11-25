"""Patch JSON (lieu -> objet, avec les hash des coffres) et conversion en modifications du jeu."""

from __future__ import annotations

from typing import Any

from . import __version__
from .fill import Result
from . import keys as keys_mod
from .world import Location, World

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


def build_patch(world: World, result: Result, seed_hash: str, remote_chains: bool = False) -> dict[str, Any]:
    """remote_chains (multiworld): copies of the progressive chains may come from other worlds."""
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
    patch = {
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
        "start_items": world.start_items(result.placements) + result.starting_items,
        "rewards": {l.name: result.placements[l.name] for l in world.reward_locations()},
        "event_changes": _merge_events(world.reward_event_changes(result.placements),
                                       world.ocarina_event_changes(result.placements),
                                       world.trial_event_changes()),
        "gift_changes": {f: [list(e) for e in v] for f, v in world.gift_event_changes(result.placements).items()},
        "gift_progressive": {},  # filled below (needs the chests)
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
        "skip_tower_collapse": bool(world.settings.get("skip_tower_collapse")),
        "ground_native": world.ground_native,
        "progressive": world.progressive,
        "progressive_pouch": world.progressive_pouch,
        "progressive_kept": world.progressive_kept,
        "progressive_logic": world.progressive_logic,
        "progressive_whole": world.progressive_whole,
        "ground_chains": ground_chains(chests, world),
        "progressive_remote": remote_chains,
        "chests": chests,
    }
    # progressive gifts (PC-built mod): their events get questions instead of a plain text change
    patch["gift_progressive"] = progressive_gifts(patch, world.gift_edits)
    for flow, entries in patch["gift_progressive"].items():
        events = {e[0] for e in entries}
        kept = [e for e in patch["gift_changes"].get(flow, []) if e[0] not in events]
        if kept:
            patch["gift_changes"][flow] = kept
        else:
            patch["gift_changes"].pop(flow, None)
    return patch


# Ground items (pickups, Gold Skulltula drops) of a PC-built mod: a chain item always gives the last step of its chain,
# and the pickup script (Dm_SY_Get) brings it back to the step Link has reached (ModBuilder._progressive_ground).
# If the script did nothing, Link would have more than the logic counts, never less.
def ground_chain(item: str, chains: list[list[str]], ground: set[str] | list[str]) -> list[str] | None:
    return next((c for c in chains if item in c and c[-1] in ground), None)


def ground_chains(chests: list[dict], world: World) -> list[list[list[str]]]:
    """[[[step, pouch name], ...]] of the chains with a copy on the ground."""
    items = {c["item"] for c in chests if c.get("pickup") or c.get("skulltula")}
    return [[[s, world.progressive_pouch.get(s, s)] for s in c] for c in world.progressive
            if c[-1] in world.ground and items & set(c)]


# Progressive items in a PC-built mod (chests only): the chest becomes an Obj_TBox_A_06 ("if Link owns
# Drop__CheckActor, give Drop__DropActor_Substitute"; a plain A_01 chest ignores the condition, validated in game
# 2026-11-15). The builder picks Obj_TBox_A_06 or Obj_TBox_A_06_NoBake from the chest's own type.
PROGRESSIVE_CHEST = "__progressive_chest"
OCARINA_FAIRY, OCARINA_TIME = "Item_Ocarina_Fairy", "Item_Ocarina_Time"


def progressive_chest(item: str, chains: list[list[str]], pouch: dict[str, str] | None = None,
                      kept: list[str] | tuple[str, ...] = (), skip_middle: bool = False) -> dict[str, Any] | None:
    """Chest fields for an item of a progressive chain, or None. A chest has one condition ("if Link owns
    CheckActor, give Substitute, else DropActor") and every copy must give step 1 when nothing is owned, so a
    3-step chain cannot be exact; what the game does (validated in game, Longshot 2026-11-15): a smaller
    upgrade received after a bigger one changes nothing, and the pouch only counts the biggest bag.
    - 2 steps: step 1, or step 2 if Link owns step 1 (exact).
    - 3 steps whose step 1 stays in the pouch (`kept`: the bow and slingshot, the upgrades are bags): the copy
      of step 2 gives step 2 after step 1, the two others step 3. Step 1 always comes first and step 3 is always
      reached; step 2 shows up only when its copy is the second one found.
    - 3 steps whose step 1 is replaced (bomb bags): step 1, then step 3; the third copy gives step 1 (no effect).
    skip_middle: every copy gives step 1, then the last step (3-step logic chains mixed with gifts, _skip_middle).
    pouch = name of a step in Link's pouch when it differs (Weapon_Range_Bow for Item_Range_Bow)."""
    for chain in chains:
        if item not in chain:
            continue
        check, give = chain[0], chain[1]
        if len(chain) > 2 and (skip_middle or not (chain[0] in kept and item == chain[1])):
            give = chain[2]
        return {"Drop__DropActor": chain[0], "Drop__CheckActor": (pouch or {}).get(check, check), "Drop__DropActor_Substitute": give,
                PROGRESSIVE_CHEST: True}
    return None


def _source(chest: dict) -> str | None:
    """How a PC-built mod makes this location progressive: "gift" (questions before the gift in its script,
    exact), "chest" (conditional chest), "ground" (pickup script, exact) or None (the item is given as placed)."""
    if chest.get("gift"):
        return "gift"
    if chest.get("hashes") and not any(chest.get(k) for k in ("pickup", "scrub", "skulltula", "shop", "ocarina")):
        return "chest"
    if chest.get("pickup") or chest.get("skulltula"):
        return "ground"
    return None


def progressive_location(loc: Location) -> bool:
    """`_source` of a Location is not None: a chain item placed there is given as the next step."""
    return loc.gift or bool(loc.pickup) or loc.skulltula or (loc.is_chest and not loc.ocarina)


def _sources(patch: dict[str, Any], chain: list[str]) -> list[str | None]:
    return [_source(c) for c in patch["chests"] if c["item"] in chain]


def progressive_chains(patch: dict[str, Any]) -> list[list[str]]:
    """Chains made progressive in a PC-built mod. A chain whose level the logic needs (`progressive_logic`:
    Hookshot, strength) only when every copy is in a chest, a gift or on the ground: others give it as placed,
    and a chest opened first would give step 1 again before such a location's step 1 (Hookshot twice, the logic
    counting a Longshot). With fixed items the logic's count never exceeds the real level.
    Multiworld (`progressive_remote`): the copies found in other worlds are given as the next step by the bridge
    (`mw_items.ItemGiver`), so only the copies of this world matter (`multiworld.fixed_chains`: the same rule)."""
    logic = set(patch.get("progressive_logic") or ()) | set(patch.get("progressive_whole") or ())
    out = []
    for chain in patch.get("progressive") or []:
        if chain[0] in logic:
            where = _sources(patch, chain)
            if not all(where) or (len(where) != len(chain) and not patch.get("progressive_remote")):
                continue
        out.append(chain)
    return out


def _skip_middle(patch: dict[str, Any], chain: list[str]) -> bool:
    """Chests of a 3-step logic chain mixed with gifts give step 1, then the last step: a gift gives the exact
    next step, so a chest that gives step 2 after a gift's step 2 would add nothing while the logic counts it.
    Same with copies received from other worlds (exact too)."""
    where = _sources(patch, chain)
    return (len(chain) > 2 and chain[0] in set(patch.get("progressive_logic") or ())
            and ("gift" in where or bool(patch.get("progressive_remote") and len(where) < len(chain))))


def progressive_gifts(patch: dict[str, Any], gift_edits: dict[str, list]) -> dict[str, list]:
    """{flow: [[event, parameter, vanilla text, [[item, pouch name], ...]]]}: gift steps of a PC-built mod that
    become questions ("does Link own the last step? ... the first one?") leading to copies of the step that give
    the next step (ModBuilder._progressive_gift). gift_edits = World.gift_edits ({location: [(flow, event,
    parameter, vanilla text)]}); every variant of the gift gets its questions, whatever its vanilla item."""
    pouch = patch.get("progressive_pouch") or {}
    # bow / slingshot with a copy given as placed (scrub): the gifts too. Link may own the big quiver without the bow,
    # and the questions (from the last step down) would never give it
    kept = set(patch.get("progressive_kept") or ())
    chains = {item: chain for chain in progressive_chains(patch) for item in chain
              if chain[0] not in kept or all(_sources(patch, chain))}
    out: dict[str, list] = {}
    for chest in patch["chests"]:
        chain = chains.get(chest["item"])
        if not chain or _source(chest) != "gift":
            continue
        for flow, event, param, old in gift_edits.get(chest["location"], []):
            out.setdefault(flow, []).append([event, param, old, [[s, pouch.get(s, s)] for s in chain]])
    return out


def chest_changes(patch: dict[str, Any]) -> dict[int, dict]:
    """Modifications d'acteurs pour le ModBuilder : {hash: {champ: valeur ou None}}.

    Un coffre qui garde son objet d'origine n'est pas touché. Sinon on change
    Drop__DropActor, et on retire l'événement s'il appartenait à l'objet
    d'origine (sinon l'animation de l'ancien objet se joue, ex. l'épée dans le dos)."""
    changes: dict[int, dict] = {}
    chains = progressive_chains(patch)
    for chest in patch["chests"]:
        if chest.get("pickup") or chest.get("scrub") or chest.get("skulltula") or chest.get("shop"):
            continue
        if chest.get("remote"):  # multiworld: another player's item (multiworld.slot_patch)
            for h in chest["hashes"]:
                changes[int(h)] = {"Drop__DropActor": chest["remote"].get("actor", chest["item"]),
                                   "GetEventName": chest["remote"]["event"]}
            continue
        chain = next((c for c in chains if chest["item"] in c), None)
        progressive = chain and progressive_chest(chest["item"], chains, patch.get("progressive_pouch"),
                                                  patch.get("progressive_kept") or (), _skip_middle(patch, chain))
        if chest["item"] == chest["vanilla"] and not progressive:
            continue
        change = {"Drop__DropActor": chest["item"]}
        # a progressive chest may give another item than the placed one: no item event (drop) either way
        if chest["event"] == "drop" and (chest["item"] != chest["vanilla"] or progressive):
            change["GetEventName"] = None
        key = keys_mod.chest_change(chest["item"], chest.get("key_dungeon"), chest["event"])
        if key:  # dungeon key: the game's key in its own dungeon, otherwise a "door key" + the chest event
            change.update(key)
        if chest.get("conditional"):
            # sinon le jeu donnerait l'objet de remplacement d'origine si le joueur a déjà l'objet testé
            change["Drop__CheckActor"] = None
            change["Drop__DropActor_Substitute"] = None
        if progressive:
            change.update(progressive)
        elif chest["item"] == OCARINA_FAIRY:  # never back from the Ocarina of Time to the Fairy Ocarina
            change.update({"Drop__DropActor": OCARINA_FAIRY, "Drop__CheckActor": OCARINA_TIME,
                           "Drop__DropActor_Substitute": OCARINA_TIME, PROGRESSIVE_CHEST: True})
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
        item = ground_item(loc, patch)
        if item in native:
            actor = native[item]
        elif item in made:
            actor = made[item]
        else:
            actor = f"{PICKUP_PREFIX}{len(pickups):03d}"
            pickups[actor] = item
            made[item] = actor
        for h in loc["hashes"]:
            changes[int(h)] = {"Drop__DropActor": actor}
    return changes


PICKUP_PREFIX = "Obj_OoTRR_Pickup_"


def ground_item(loc: dict[str, Any], patch: dict[str, Any] | None = None) -> str:
    """Item given by a ground item (pickup, Gold Skulltula drop): a small key is the game's key item, added by the
    game to the dungeon of the current map (World.ground_key only puts a key in its own dungeon) [game]. An item of
    a progressive chain: the chain's last step (`ground_chains`)."""
    key = keys_mod.parse_item(loc["item"])
    if key is None:
        for chain in (patch or {}).get("ground_chains") or []:
            if loc["item"] in [step for step, _ in chain]:
                return chain[-1][0]
        return loc["item"]
    if key[0] != keys_mod.SMALL or loc.get("key_dungeon") != key[1]:
        raise ValueError(f"{loc['location']}: {loc['item']} cannot be given by a ground item")
    return keys_mod.GAME_ITEM[keys_mod.SMALL]


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
        item = ground_item(loc, patch)
        if item in native:
            actor = native[item]
        else:
            actor = f"{PICKUP_PREFIX}{len(pickups):03d}"
            pickups[actor] = item
        for h in loc["hashes"]:
            changes[int(h)] = {"Gyaml": actor}
    return changes, pickups
