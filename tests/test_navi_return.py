"""Way back asked by Navi (World.navi_return): one question per dungeon, one per age outside."""

from __future__ import annotations

import unittest

from ootrr import settings
from ootrr.modbuild import ModBuilder
from ootrr.world import ADULT_MAP_FLAG, NIGHT_FLAG, GAME_DUNGEONS, World


class NaviReturnTest(unittest.TestCase):
    def test_every_dungeon_has_its_entrance(self):
        edit = World(settings.build({})).ainb_edits()["navi_return"]
        self.assertLessEqual(set(GAME_DUNGEONS.values()), set(edit["dungeons"]))
        self.assertLessEqual(len(edit["dungeons"]) + len(edit["outside"]), 14)  # entry points of WarpEvent
        maps = list(edit["dungeons"]) + [m for maps in edit["outside"].values() for m in maps]
        self.assertEqual(len(maps), len(set(maps)))

    def test_starting_points(self):
        points = World(settings.build({})).navi_return()["points"]
        self.assertEqual(points["child"], ["KokiriForest_Child", "ReturnFromDreamWorld"])
        self.assertEqual(points["adult"], ["Market_Adult", "LightPrelude"])

    def test_texts(self):
        for texts in ModBuilder.RETURN_TEXTS.values():
            self.assertEqual(set(texts), {"dungeon", "outside", *ModBuilder.RETURN_LABELS})

    def test_adult_map_and_night(self):
        for options in ({}, {"skip_child_zelda": "on", "starting_age": "adult"}):
            flags = World(settings.build(options)).start_flags()
            self.assertTrue(flags[ADULT_MAP_FLAG])
            self.assertTrue(flags[NIGHT_FLAG])


if __name__ == "__main__":
    unittest.main()
