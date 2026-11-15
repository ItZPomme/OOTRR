"""adult_trade_sequence: Biggoron's gift is never needed without it, and follows the trade quest with it."""

import unittest

from ootrr import settings
from ootrr.fill import generate
from ootrr.world import World

BIGGORON = "DMT Biggoron"
SWORD = "Item_Sword_Biggoron"


class TradeSequenceTest(unittest.TestCase):
    def test_off_biggoron_never_needed(self):
        world = World(settings.build({}))
        self.assertTrue(world.locations[BIGGORON].no_progression)
        self.assertFalse(world.is_progression("Item_PocketEgg"))
        for seed in range(10):
            placements = generate(world, seed).placements
            self.assertFalse(world.is_progression(placements[BIGGORON]))
            self.assertEqual(list(placements.values()).count(SWORD), 1)  # the sword is in the pool

    def test_on_trade_quest_in_logic(self):
        world = World(settings.build({"adult_trade_sequence": True}))
        self.assertFalse(world.locations[BIGGORON].no_progression)
        self.assertTrue(world.is_progression("Item_PocketEgg"))
        self.assertIn("Trade_Eyedrops", world.locations[BIGGORON].rule_src)
        for seed in range(10):
            self.assertEqual(list(generate(world, seed).placements.values()).count(SWORD), 1)


if __name__ == "__main__":
    unittest.main()
