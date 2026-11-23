"""Worst-case small keys from a room graph (ootrr.tools.key_graph) and the graph data file."""

import json
import unittest

from ootrr import keys as keys_mod
from ootrr.tools.key_graph import DATA, GRAPH, worst_case


def link(a, b, door="open"):
    return {"rooms": [a, b], "door": door}


class WorstCaseTest(unittest.TestCase):
    # 0 entrance; 0 -locked- 1 -open- 2 ; 0 -locked- 3 -locked- 4 ; 0 -open- 5 ; 5 -oneway-> 6 ; 7 joined to nothing
    LINKS = [link(0, 1, "locked"), link(1, 2), link(0, 3, "locked"), link(3, 4, "locked"), link(0, 5),
             link(5, 6, "oneway"), link(2, 8, "boss")]

    def count(self, room, total=3):
        return worst_case(0, self.LINKS, room, total)

    def test_open_rooms_need_no_key(self):
        self.assertEqual(self.count(0), 0)
        self.assertEqual(self.count(5), 0)
        self.assertEqual(self.count(6), 0)  # one way, from an open room

    def test_worst_case(self):
        # room 1: the doors 0-3 and 3-4 may be opened first, then 0-1
        self.assertEqual(self.count(1), 3)
        self.assertEqual(self.count(2), 3)  # open from room 1: same as room 1
        # room 3: the door 0-1 may be opened first (1-2 lead nowhere locked), then 0-3
        self.assertEqual(self.count(3, total=5), 2)
        # room 4: 0-1 and 0-3 first, then 3-4
        self.assertEqual(self.count(4, total=5), 3)
        self.assertEqual(self.count(8, total=5), 3)  # behind the boss door: no small key for it

    def test_capped_and_prudent(self):
        self.assertEqual(self.count(1, total=2), 2)  # never more than the dungeon's keys
        self.assertEqual(self.count(7), 3)  # not joined to the entrance: all the keys

    def test_oneway_is_one_way(self):
        links = [link(0, 1, "locked"), link(2, 0, "oneway")]
        self.assertEqual(worst_case(0, links, 2, 1), 1)  # 2 -> 0 does not lead into 2: unreachable, all keys


class WaterLevelTest(unittest.TestCase):
    """Water Temple shape: hub 0, water high at the start. Tablets: room 9 (free) sets low, room 1 (behind the low
    door) sets mid, room 10 (behind the mid door) sets high. Doors at their level, the boss key door at any level."""
    WATER = {"start": "high", "tablets": [{"room": 9, "level": "low"}, {"room": 1, "level": "mid"},
                                          {"room": 10, "level": "high"}]}
    LINKS = [
        link(0, 9),
        dict(link(0, 1, "locked"), levels=["low"]),   # central tower: mid tablet
        dict(link(0, 1), levels=["mid"]),             # its exit at mid water (mid exists only through the tower)
        dict(link(0, 10, "locked"), levels=["mid"]),  # high tablet
        dict(link(10, 0, "oneway"), levels=["high"]),  # its way out once the water is high
        dict(link(0, 5, "locked"), levels=["high"]),  # towards the Longshot
        link(0, 12, "locked"),                        # boss key, any level
        dict(link(0, 20), levels=["mid"]),            # open, mid water only
    ]

    def count(self, room):
        return worst_case(0, self.LINKS, room, 4, self.WATER)

    def test_level_gates(self):
        self.assertEqual(self.count(9), 0)
        # mid water needs the tablet behind the tower door: the mid door cannot be opened before it
        self.assertEqual(self.count(1), 3)
        self.assertEqual(self.count(20), 3)  # open link, but mid water: behind the tower door
        # every other door can be opened before these (high back through room 10)
        self.assertEqual(self.count(10), 4)
        self.assertEqual(self.count(5), 4)
        self.assertEqual(self.count(12), 4)

    def test_water_does_not_come_back(self):
        # a ledge of room 9 only reached at high water: the player may lower the water first (tablet of room 9),
        # then high comes back only through room 10, behind the mid door, maybe after the other doors
        links = self.LINKS + [dict(link(9, 109), levels=["high"])]
        self.assertEqual(worst_case(0, links, 109, 4, self.WATER), 4)
        # without the tablet beside it, nothing lowers the water before the ledge: no key
        water = {"start": "high", "tablets": [t for t in self.WATER["tablets"] if t["room"] != 9]}
        self.assertEqual(worst_case(0, links, 109, 4, water), 0)

    def test_without_levels_all_parallel(self):
        # levels ignored: the tower's exit becomes a free way in, the other doors are parallel
        self.assertEqual(worst_case(0, self.LINKS, 1, 4), 0)
        self.assertEqual(worst_case(0, self.LINKS, 10, 4), 4)

    def test_unreachable_level(self):
        water = {"start": "high", "tablets": []}  # no tablet: low and mid never reached
        self.assertEqual(worst_case(0, self.LINKS, 1, 4, water), 4)
        self.assertEqual(worst_case(0, self.LINKS, 20, 4, water), 4)


class GraphFileTest(unittest.TestCase):
    def test_graph_matches_keys(self):
        graph = json.loads(GRAPH.read_text(encoding="utf-8"))["dungeons"]
        keys = keys_mod.load(DATA)
        self.assertEqual(set(graph), set(keys))
        for name, g in graph.items():
            kd = keys[name]
            water = g.get("water")
            levels = {water["start"]} | {t["level"] for t in water["tablets"]} if water else set()
            for l in g["links"]:
                self.assertIn(l["door"], ("open", "locked", "boss", "oneway"), name)
                self.assertEqual(len(l["rooms"]), 2, name)
                if "levels" in l:
                    self.assertTrue(water, f"{name}: levels on a link without water levels")
                    self.assertLessEqual(set(l["levels"]), levels, name)
            locked = sum(1 for l in g["links"] if l["door"] == "locked")
            # one locked door per key: chests, ground and keys owned from the start
            self.assertEqual(locked, len(kd.small) + len(kd.freestanding) + kd.start_keys, name)


if __name__ == "__main__":
    unittest.main()
