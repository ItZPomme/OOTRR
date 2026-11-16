"""Setting gerudo_card: random = the card is in the item pool, vanilla = the Gerudo gives it (fixed location)."""

import unittest

from ootrr import settings
from ootrr.fill import check, generate
from ootrr.world import GERUDO_CARD_LOCATION, World

CARD = "Item_Token_Gerudo"


class GerudoCardTest(unittest.TestCase):
    def test_random_is_the_default(self):
        world = World(settings.build({}))
        self.assertTrue(world.locations[GERUDO_CARD_LOCATION].shuffle)

    def test_vanilla_keeps_the_card(self):
        world = World(settings.build({"gerudo_card": "vanilla"}))
        loc = world.locations[GERUDO_CARD_LOCATION]
        self.assertFalse(loc.shuffle)
        self.assertNotIn(CARD, [item for item, _ in world.pool()])
        for seed in range(10):
            result = generate(world, seed)
            self.assertEqual(result.placements[GERUDO_CARD_LOCATION], CARD)
            self.assertEqual(list(result.placements.values()).count(CARD), 1)
            beaten, unreachable = check(world, result.placements)
            self.assertTrue(beaten)
            self.assertEqual(unreachable, [])


if __name__ == "__main__":
    unittest.main()
