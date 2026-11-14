"""cucco_count and big_poe_count: validation and the integer edits the generator asks for."""

import unittest

from ootrr import settings, settings_ui
from ootrr.world import World


class MinigameCountsTest(unittest.TestCase):
    def test_defaults_change_nothing(self):
        world = World(settings.build())
        self.assertEqual(world.logic_ints(), {})
        self.assertEqual(world.event_ints(), {})

    def test_ranges(self):
        for name, (lo, hi) in settings.INT_RANGES.items():
            settings.build({name: lo})
            settings.build({name: hi})
            for bad in (lo - 1, hi + 1):
                with self.assertRaises(settings.SettingsError):
                    settings.build({name: bad})
            self.assertEqual(settings_ui.int_range(name, settings.defaults()), (lo, hi))

    def test_edits(self):
        world = World(settings.build({"cucco_count": 3, "big_poe_count": 2}))
        self.assertEqual(world.logic_ints(), {"MiniGame_CatchCucco_c69b": [(17, "Int_A", 7, 3)]})
        events = world.event_ints()
        self.assertEqual(events["Minigame_CatchCucco"], [(30, "Value", 7, 3), (17, "Value", 7, 3)])
        # points before the sale that reaches the count: 100 per Big Poe
        self.assertTrue(all(e[2:] == (400, 100) for e in events["Npc_Hylia_048_BottleShop"]))
        self.assertEqual(len(events["Npc_Hylia_048_BottleShop"]), 7)


if __name__ == "__main__":
    unittest.main()
