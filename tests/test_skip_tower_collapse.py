"""skip_tower_collapse: from Ganondorf straight to Ganon's arena."""

import unittest

from ootrr import settings
from ootrr.fill import generate
from ootrr.patch import build_patch
from ootrr.world import World


class SkipTowerCollapseTest(unittest.TestCase):
    def patch(self, values):
        world = World(settings.build(values))
        result = generate(world, 1)
        return build_patch(world, result, "TEST"), result.placements

    def test_patch(self):
        off, placed_off = self.patch({})
        on, placed_on = self.patch({"skip_tower_collapse": True})
        self.assertIs(off["skip_tower_collapse"], False)
        self.assertIs(on["skip_tower_collapse"], True)
        self.assertEqual(placed_off, placed_on)  # outside the logic


if __name__ == "__main__":
    unittest.main()
