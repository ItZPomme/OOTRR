"""fast_bunny_hood: the patch asks for the BoolExp and the walk module edit only when the setting is on."""

import unittest

from ootrr import settings
from ootrr.world import BUNNY_WORN_EXP, PLAYER_PACKS, World


class FastBunnyHoodTest(unittest.TestCase):
    def test_off_by_default(self):
        world = World(settings.build({}))
        self.assertNotIn("fast_walk", world.ainb_edits())
        self.assertNotIn(BUNNY_WORN_EXP, world.bool_exps())

    def test_on(self):
        world = World(settings.build({"fast_bunny_hood": True}))
        edit = world.ainb_edits()["fast_walk"]
        self.assertEqual(tuple(edit["actors"]), PLAYER_PACKS)
        self.assertEqual(edit["head_actor"], "Armor_Child_Mask_Bunny")
        self.assertGreater(edit["factor"], 1.0)
        self.assertEqual(world.bool_exps()[BUNNY_WORN_EXP], [("Bool", "#3262939387")])


if __name__ == "__main__":
    unittest.main()
