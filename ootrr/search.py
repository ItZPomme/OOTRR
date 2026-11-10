"""Recherche d'accessibilité : quelles régions et quels lieux sont atteignables
avec un inventaire donné, pour Link enfant et Link adulte."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from .rules import AGES
from .world import Location, World

EVENT_PREFIX = "[événement] "


# Dans le remake, l'épée de légende ne renvoie Link enfant qu'une fois le Temple de la
# Forêt terminé (module Market_Adult_Prefab_89da : SageOfForest_IsCompleted_Exp).
RETURN_TO_CHILD = "Forest_Medallion"


class State:
    """Inventaire et régions atteintes.

    L'enfant n'utilise que les objets trouvés en enfant (child_items) tant que Link
    ne peut pas redevenir enfant ; ensuite, tout l'inventaire."""

    def __init__(self, world: World, items: Iterable[str] = ()) -> None:
        self.world = world
        self.items: Counter[str] = Counter()
        self.child_items: Counter[str] = Counter()
        for item in items:
            world.collect(self.items, item)
            world.collect(self.child_items, item)
        self.reached: dict[str, set[str]] = {age: {world.ROOT} for age in AGES}
        self.collected: set[str] = set()
        self.events: set[str] = set()
        self.can_return = world.free_return_to_child()
        self._age = "adult"

    # Interface utilisée par les règles compilées
    def has(self, item: str, n: int = 1) -> bool:
        if self._age == "child" and not self.can_return:
            return self.child_items[item] >= n
        return self.items[item] >= n

    def _check(self, rule, age: str) -> bool:
        self._age = age
        try:
            return rule(self, age)
        finally:
            self._age = "adult"

    # ------------------------------------------------------------------
    def expand(self) -> None:
        """Étend les régions atteintes jusqu'au point fixe pour l'inventaire actuel."""
        regions = self.world.regions
        for age in AGES:
            reached = self.reached[age]
            stack = list(reached)
            while stack:
                for ex in regions[stack.pop()].exits:
                    if ex.target not in reached and self._check(ex.rule, age):
                        reached.add(ex.target)
                        stack.append(ex.target)

    def _reach_as(self, region: str, rule, age: str) -> bool:
        return region in self.reached[age] and self._check(rule, age)

    def can_reach(self, loc: Location) -> bool:
        return any(self._reach_as(loc.region, loc.rule, age) for age in AGES)

    def _event_ready(self, ev) -> bool:
        return any(self._reach_as(ev.region, ev.rule, age) for age in AGES)

    def step(self, placements: Mapping[str, str]) -> list[tuple[str, str]]:
        """Une « sphère » : collecte d'un coup tout ce qui est atteignable maintenant.

        Retourne la liste (lieu ou événement, objet) collectée ; vide = point fixe."""
        self.expand()
        found: list[tuple[str, str]] = []
        as_child: list[bool] = []
        for ev in self.world.events:
            if ev.name not in self.events and self._event_ready(ev):
                found.append((EVENT_PREFIX + ev.region, ev.name))
                as_child.append(self._reach_as(ev.region, ev.rule, "child"))
        for name, item in placements.items():
            loc = self.world.locations[name]
            if name not in self.collected and self.can_reach(loc):
                found.append((name, item))
                as_child.append(self._reach_as(loc.region, loc.rule, "child"))
        for (where, item), child in zip(found, as_child):
            if where.startswith(EVENT_PREFIX):
                self.events.add(item)
            else:
                self.collected.add(where)
            self.world.collect(self.items, item)
            if child:
                self.world.collect(self.child_items, item)
        if not self.can_return and self.items[RETURN_TO_CHILD] and "Temple of Time" in self.reached["adult"]:
            self.can_return = True
            self.reached["child"] = {self.world.ROOT}  # l'enfant profite maintenant de tout l'inventaire
        return found

    def sweep(self, placements: Mapping[str, str]) -> "State":
        while self.step(placements):
            pass
        return self

    def beaten(self) -> bool:
        return World.GOAL_EVENT in self.events


def is_beatable(world: World, placements: Mapping[str, str], starting: Iterable[str] = ()) -> bool:
    return State(world, starting).sweep(placements).beaten()
