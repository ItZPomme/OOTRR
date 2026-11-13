"""Placement des objets (« assumed fill », le même principe que OoTR).

Les lieux fixes (PNJ, chants, boss, coffres non mélangés) gardent leur objet
d'origine. Le contenu des coffres mélangés forme le pool. Pour chaque objet
de progression du pool, on suppose que le joueur possède tous les objets de
progression *pas encore placés*, on calcule les coffres encore vides
atteignables avec cet inventaire, et on y place l'objet au hasard : la seed
est donc toujours finissable. Le reste est placé au hasard ensuite.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from .search import State
from .world import Location, World


class FillError(RuntimeError):
    pass


@dataclass
class Result:
    seed: int
    attempts: int
    placements: dict[str, str]
    starting_items: list[str] = field(default_factory=list)
    unreachable: list[str] = field(default_factory=list)


def _candidates(world: World, item: str, locations: list[Location], placements: dict[str, str],
                assumed: list[str]) -> list[Location]:
    without = list(assumed)
    without.remove(item)
    state = State(world, without).sweep(placements)
    return [l for l in locations
            if l.name not in placements and world.can_place(item, l) and state.can_reach(l)]


def _assumed_fill(world: World, rng: random.Random, items: list[str], locations: list[Location],
                  placements: dict[str, str]) -> None:
    """Place les objets de progression, en commençant à chaque étape par celui
    qui a le moins de lieux possibles (évite les impasses)."""
    items = list(items)
    rng.shuffle(items)
    assumed = list(items)
    while items:
        options = {name: _candidates(world, name, locations, placements, assumed)
                   for name in dict.fromkeys(items)}
        item = min(options, key=lambda n: len(options[n]))
        candidates = options[item]
        if not candidates:
            raise FillError(f"aucun lieu possible pour {item}")
        items.remove(item)
        assumed.remove(item)
        placements[rng.choice(candidates).name] = item


def _attempt(world: World, rng: random.Random) -> dict[str, str]:
    # logic = none: random placement, no reachability check (same random draws as generator.cpp)
    no_logic = world.settings.get("logic") == "none"
    placements = {l.name: l.vanilla for l in world.fixed_locations()}
    if world.settings.get("shuffle_rewards") == "shuffled":
        # pierres et médaillons mélangés entre les boss et la poche de Link
        rewards = world.reward_locations()
        items = [l.vanilla for l in rewards]
        # tirage refait tant qu'il rend la partie infinissable même avec tous les autres objets
        everything = [item for item, _ in world.pool()]
        for _ in range(200):
            rng.shuffle(items)
            trial = dict(placements)
            trial.update({loc.name: item for loc, item in zip(rewards, items)})
            if no_logic or State(world, everything).sweep(trial).beaten():
                break
        for loc, item in zip(rewards, items):
            placements[loc.name] = item
    if world.settings.get("shuffle_songs") == "shuffle":
        # chants mélangés entre les emplacements de chants (même méthode ; même ordre dans generator.cpp)
        songs = world.song_locations()
        items = [l.vanilla for l in songs]
        everything = [item for item, _ in world.pool()]
        for _ in range(200):
            rng.shuffle(items)
            trial = dict(placements)
            trial.update({loc.name: item for loc, item in zip(songs, items)})
            if no_logic or State(world, everything).sweep(trial).beaten():
                break
        for loc, item in zip(songs, items):
            placements[loc.name] = item
    shuffled = world.shuffled_locations()
    pool = world.pool()

    # 1. objets liés à un donjon (cartes, boussoles) : dans un coffre de ce donjon
    for item, dungeon in pool:
        if dungeon is None:
            continue
        free = [l for l in shuffled if l.dungeon == dungeon and l.name not in placements and world.can_place(item, l)]
        if not free:
            raise FillError(f"plus de coffre libre dans {dungeon} pour {item}")
        placements[rng.choice(free).name] = item

    free_pool = [item for item, dungeon in pool if dungeon is None]
    progression = [] if no_logic else [i for i in free_pool if world.is_progression(i)]
    rest = list(free_pool) if no_logic else [i for i in free_pool if not world.is_progression(i)]

    # 2. objets de progression, 3. le reste
    _assumed_fill(world, rng, progression, shuffled, placements)

    # 3. le reste : d'abord les objets qui ont le moins de lieux possibles (pas au sol)
    empty = [l for l in shuffled if l.name not in placements]
    if len(empty) != len(rest):
        raise FillError(f"incohérence du pool : {len(rest)} objets pour {len(empty)} lieux")
    rng.shuffle(rest)
    rest.sort(key=lambda item: sum(world.can_place(item, l) for l in empty))
    for item in rest:
        free = [l for l in empty if l.name not in placements and world.can_place(item, l)]
        if not free:
            raise FillError(f"aucun lieu restant pour {item}")
        placements[rng.choice(free).name] = item
    return placements


def check(world: World, placements: dict[str, str]) -> tuple[bool, list[str]]:
    state = State(world).sweep(placements)
    return state.beaten(), sorted(set(world.locations) - state.collected)


def generate(world: World, seed: int, max_attempts: int = 20) -> Result:
    rng = random.Random(seed)
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            placements = _attempt(world, rng)
        except FillError as exc:
            last_error = exc
            continue
        beaten, unreachable = check(world, placements)
        if world.settings.get("logic") == "none":
            return Result(seed, attempt, placements, [], unreachable)
        if not beaten:
            last_error = FillError("seed non finissable")
            continue
        if world.settings["accessibility"] == "all" and unreachable:
            last_error = FillError(f"{len(unreachable)} lieux inaccessibles, ex. {unreachable[0]}")
            continue
        return Result(seed, attempt, placements, [], unreachable)
    raise FillError(f"échec après {max_attempts} tentatives : {last_error}")
