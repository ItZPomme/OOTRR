"""Départ de la partie : âge et point d'apparition tirés par la seed.

Les réglages « random » (starting_age = random, random_spawn) sont résolus **avant** de construire le
monde, à partir de la seed (pas du générateur aléatoire du placement) : même calcul dans le module natif
(ingame.cpp, ResolveStart), pour que la logique, le spoiler et le jeu voient le même départ.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "spawns.json"
MASK = 0xFFFFFFFFFFFFFFFF
# Départ aléatoire désactivé (retour de test : la logique et le jeu ne démarraient pas au même endroit) ;
# même interrupteur dans ingame.cpp (kRandomSpawnEnabled). Le départ adulte reste au Temple du Temps.
RANDOM_SPAWN_ENABLED = False


@lru_cache(maxsize=1)
def spawns() -> list[dict]:
    with DATA.open(encoding="utf-8") as fh:
        return json.load(fh)["spawns"]


@lru_cache(maxsize=1)
def adult_default() -> int:
    """spawn_point du départ adulte sans random_spawn (Temple du Temps)."""
    with DATA.open(encoding="utf-8") as fh:
        region = json.load(fh)["adult_default"]
    return next(i for i, s in enumerate(spawns()) if s["age"] == "adult" and s["region"] == region) + 1


def mix(seed: int, salt: int) -> int:
    """SplitMix64 de (seed, salt) ; même calcul que ingame.cpp (StartHash)."""
    h = (seed * 0x9E3779B97F4A7C15 + salt * 0xBF58476D1CE4E5B9) & MASK
    h ^= h >> 30
    h = (h * 0xBF58476D1CE4E5B9) & MASK
    h ^= h >> 27
    h = (h * 0x94D049BB133111EB) & MASK
    h ^= h >> 31
    return h


def resolve(settings: dict, seed: int) -> dict:
    """Réglages avec l'âge et le point d'apparition décidés (copie)."""
    s = dict(settings)
    if s.get("starting_age") == "random":
        s["starting_age"] = "adult" if mix(seed, 1) & 1 else "child"
    adult = s.get("starting_age") == "adult"
    if adult:
        # l'adulte doit pouvoir redevenir enfant tout de suite : Porte du Temps ouverte (épée atteignable) et
        # voyage temporel libre (sinon il faut le Temple de la Forêt, inaccessible sans le Chant de Saria
        # appris enfant)
        s["open_door_of_time"] = True
        s["free_time_travel"] = True
    if RANDOM_SPAWN_ENABLED and s.get("random_spawn"):
        age = "adult" if adult else "child"
        options = [i + 1 for i, sp in enumerate(spawns()) if sp["age"] == age]
        s["spawn_point"] = options[mix(seed, 2) % len(options)]
    elif adult:
        s["spawn_point"] = adult_default()
    else:
        s["spawn_point"] = 0
    return s


def spawn(settings: dict) -> dict | None:
    k = settings.get("spawn_point", 0)
    return spawns()[k - 1] if k else None


def add_spawn_exits(regions_raw: dict) -> dict:
    """Sorties de Root vers chaque point d'apparition (« is_<âge> and spawn_point == k »), fusionnées
    (or) avec les sorties existantes. Utilisé par world.World et native_logic.Exporter."""
    import copy

    regions = copy.deepcopy(regions_raw)
    exits = regions["Root"].setdefault("exits", {})
    by_region: dict[str, list[str]] = {}
    for k, sp in enumerate(spawns(), 1):
        by_region.setdefault(sp["region"], []).append(f"(is_{sp['age']} and setting_value(spawn_point) == {k})")
    for region, rules in by_region.items():
        if region not in regions:
            raise ValueError(f"spawns.json : région inconnue « {region} »")
        old = exits.get(region)
        exits[region] = " or ".join(([f"({old})"] if old else []) + rules)
    return regions
