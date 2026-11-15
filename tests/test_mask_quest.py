"""complete_mask_quest: the Happy Mask Shop quest Enum starts at Complete."""

import unittest

from ootrr import settings
from ootrr.world import MASK_QUEST, World


class MaskQuestTest(unittest.TestCase):
    def test_off_by_default(self):
        flags = World(settings.build({})).start_flags()
        self.assertNotIn(f"#{MASK_QUEST[1]}", flags)

    def test_start_flag(self):
        flags = World(settings.build({"complete_mask_quest": True})).start_flags()
        self.assertEqual(flags[f"#{MASK_QUEST[1]}"], "Complete")


if __name__ == "__main__":
    unittest.main()
