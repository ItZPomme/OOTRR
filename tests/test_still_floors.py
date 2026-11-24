"""Falling floors that stay up (Deku Tree, Slingshot room): in every mod."""

import unittest

from ootrr import settings
from ootrr.fill import generate
from ootrr.patch import build_patch
from ootrr.world import STILL_FLOORS, World


class StillFloorsTest(unittest.TestCase):
    def test_every_seed(self):
        world = World(settings.build({}))
        edit = build_patch(world, generate(world, 1), "TEST")["ainb_edits"]["still_floors"]
        self.assertEqual(set(edit), set(STILL_FLOORS))
        actors = [a for spec in edit.values() for a in spec[3]]
        self.assertIn("Obj_InsideTheDekuTree_FallingFloor_A_01", actors)
        self.assertIn("Obj_InsideTheDekuTree_FallingFloor_A_02", actors)
        self.assertEqual(len(actors), len(set(actors)))  # each pack is written once


if __name__ == "__main__":
    unittest.main()
