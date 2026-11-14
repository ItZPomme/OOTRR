"""Shuffled Deku Scrubs: 5 different items, prices from scrub_prices (PC-built mod)."""

import os
import unittest

from ootrr import settings
from ootrr.fill import generate
from ootrr.patch import build_patch, scrub_changes
from ootrr.world import SCRUB_PRICE, World, shop_price

N_SEEDS = int(os.environ.get("OOTRR_TEST_SEEDS", "100"))


class ScrubItemsTest(unittest.TestCase):
    def test_scrubs_sell_different_items(self):
        # the PC-built mod recognises a sale by its item name in the shared scrub script: two scrubs with the same
        # item would share one sale; items sold by the other (consumable) scrubs are never placed there
        world = World(settings.build({"shuffle_scrubs": True, "logic": "none"}))
        scrubs = [n for n, loc in world.locations.items() if loc.scrub]
        self.assertEqual(len(scrubs), 5)
        for seed in range(1, N_SEEDS + 1):
            result = generate(world, seed)
            items = [result.placements[n] for n in scrubs]
            self.assertEqual(len(set(items)), len(items), f"seed {seed}: {items}")
            for item in items:
                self.assertNotIn(item, world.repeated_items)
                self.assertFalse(item.startswith(("Shop_", "TBox_")), item)


class ScrubPriceTest(unittest.TestCase):
    def _patch(self, mode):
        world = World(settings.build({"shuffle_scrubs": True, "scrub_prices": mode}))
        return world, build_patch(world, generate(world, 1234), "test")

    def test_prices_follow_setting(self):
        _, patch = self._patch("vanilla")
        self.assertEqual(set(scrub_changes(patch)[1].values()), {SCRUB_PRICE})
        _, patch = self._patch("affordable")
        self.assertEqual(set(scrub_changes(patch)[1].values()), {10})
        world, patch = self._patch("random")
        sales = scrub_changes(patch)[1]
        scrubs = [c for c in patch["chests"] if c.get("scrub")]
        self.assertEqual(len(sales), len(scrubs))  # one sale per scrub
        for c in scrubs:  # same value as the native module (ShopPrice) for this location
            price = shop_price(world.settings, patch["seed"], c["index"], SCRUB_PRICE, "scrub_prices")
            self.assertEqual(sales[c["item"]], price)
            self.assertTrue(0 <= price <= 95 and price % 5 == 0)


if __name__ == "__main__":
    unittest.main()
