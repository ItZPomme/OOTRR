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


class GraphFileTest(unittest.TestCase):
    def test_graph_matches_keys(self):
        graph = json.loads(GRAPH.read_text(encoding="utf-8"))["dungeons"]
        keys = keys_mod.load(DATA)
        self.assertEqual(set(graph), set(keys))
        for name, g in graph.items():
            kd = keys[name]
            for l in g["links"]:
                self.assertIn(l["door"], ("open", "locked", "boss", "oneway"), name)
                self.assertEqual(len(l["rooms"]), 2, name)
            locked = sum(1 for l in g["links"] if l["door"] == "locked")
            # one locked door per key: chests, ground and keys owned from the start
            self.assertEqual(locked, len(kd.small) + len(kd.freestanding) + kd.start_keys, name)


if __name__ == "__main__":
    unittest.main()
