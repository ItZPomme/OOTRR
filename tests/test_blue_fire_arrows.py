"""blue_fire_arrows: the patch asks for the arrow / red ice AI edit only when the setting is on, and the logic
accepts Ice Arrows instead of a bottle of Blue Fire."""

import unittest

from ootrr import settings
from ootrr.world import BLUE_FIRE_TIMER, RED_ICE_PACKS, World


class BlueFireArrowsTest(unittest.TestCase):
    def test_off_by_default(self):
        world = World(settings.build({}))
        self.assertNotIn("blue_fire_arrows", world.ainb_edits())

    def test_on(self):
        world = World(settings.build({"blue_fire_arrows": True}))
        edit = world.ainb_edits()["blue_fire_arrows"]
        self.assertEqual(edit["timer"], BLUE_FIRE_TIMER)
        self.assertEqual(edit["arrow"]["actor"], "NormalArrow")
        self.assertIn("Obj_RedIce_A_02", edit["red_ice"])  # King Zora's ice
        self.assertEqual(tuple(edit["red_ice"]), RED_ICE_PACKS)

    def test_ice_arrows_are_a_logic_item(self):
        world = World(settings.build({}))
        self.assertEqual(world.items["Item_Arrow_Ice"].logic, "Ice_Arrows")


if __name__ == "__main__":
    unittest.main()
