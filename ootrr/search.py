"""Recherche d'accessibilité : quelles régions et quels lieux sont atteignables
avec un inventaire donné, pour Link enfant et Link adulte."""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Mapping

from .rules import AGES
from .world import Location, World

EVENT_PREFIX = "[événement] "


# In the remake, the Master Sword only sends Link back to childhood once the Forest Temple is done (module
# Market_Adult_Prefab_89da: SageOfForest_IsCompleted_Exp, i.e. Phantom Ganon beaten and his blue warp taken). The
# Forest Medallion does not count: with shuffled rewards it may come from another boss.
RETURN_TO_CHILD = "Forest_Temple_Clear"


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

    def reachable(self, placements: Mapping[str, object]) -> list[tuple[str, object, bool]]:
        """Events and placed locations reachable now and not collected yet: (event or location, item, reached as
        child). The placed value is passed through as is (the multiworld fill places (owner, item) pairs)."""
        self.expand()
        found: list[tuple[str, object, bool]] = []
        for ev in self.world.events:
            if ev.name not in self.events and self._event_ready(ev):
                found.append((EVENT_PREFIX + ev.region, ev.name, self._reach_as(ev.region, ev.rule, "child")))
        for name, item in placements.items():
            loc = self.world.locations[name]
            if name not in self.collected and self.can_reach(loc):
                found.append((name, item, self._reach_as(loc.region, loc.rule, "child")))
        return found

    def mark(self, where: str, item: str) -> None:
        """Records a found event or location (its item may go to another world, see `receive`)."""
        if where.startswith(EVENT_PREFIX):
            self.events.add(item)
        else:
            self.collected.add(where)

    def receive(self, item: str, child: bool) -> None:
        """Adds an item to the inventory; `child`: usable by the child before he can go back in time."""
        self.world.collect(self.items, item)
        if child:
            self.world.collect(self.child_items, item)

    def update_return(self) -> None:
        if not self.can_return and self.items[RETURN_TO_CHILD] and "Temple of Time" in self.reached["adult"]:
            self.can_return = True
            self.reached["child"] = {self.world.ROOT}  # l'enfant profite maintenant de tout l'inventaire

    def step(self, placements: Mapping[str, str]) -> list[tuple[str, str]]:
        """Une « sphère » : collecte d'un coup tout ce qui est atteignable maintenant.

        Retourne la liste (lieu ou événement, objet) collectée ; vide = point fixe."""
        found = self.reachable(placements)
        for where, item, child in found:
            self.mark(where, item)
            self.receive(item, child)
        self.update_return()
        return [(where, item) for where, item, _ in found]

    def sweep(self, placements: Mapping[str, str]) -> "State":
        while self.step(placements):
            pass
        return self

    def beaten(self) -> bool:
        return World.GOAL_EVENT in self.events


def is_beatable(world: World, placements: Mapping[str, str], starting: Iterable[str] = ()) -> bool:
    return State(world, starting).sweep(placements).beaten()
