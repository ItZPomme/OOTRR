"""skip_trials: Ganon's Castle trials completed from the new game."""

import unittest

from ootrr import settings
from ootrr.fill import generate
from ootrr.patch import build_patch
from ootrr.search import State
from ootrr.world import TRIAL_FLAGS, World

SHUFFLED_KEYS = {"small_keys": "any_dungeon", "boss_keys": "any_dungeon"}
KEY = "OoTRR_SmallKey_InsideGanonCastle"
LIGHT_ARROWS = "Item_Arrow_Light"


class SkipTrialsTest(unittest.TestCase):
    def test_off_by_default(self):
        world = World(settings.build({}))
        self.assertFalse(set(TRIAL_FLAGS) & set(world.start_flags()))
        self.assertEqual(world.trial_event_changes(), {})

    def test_start_flags(self):
        flags = World(settings.build({"skip_trials": True})).start_flags()
        for trial in ("Forest", "Water", "Shadow", "Fire", "Light", "Spirit"):
            self.assertIs(flags[f"InsideGanonCastle_Dungeon_BarrierRemove_{trial}"], True)
        self.assertEqual(flags["InsideGanonCastle_Dungeon_Barrier_Count"], 0)
        self.assertIs(flags["InsideGanonCastle_IsAllBarrierClear"], True)

    def test_quest_step(self):
        world = World(settings.build({"skip_trials": True, "shuffle_rewards": "shuffled"}))
        changes = build_patch(world, generate(world, 1), "TEST")["event_changes"]
        self.assertEqual(changes["Defeat_Ganon"], {"Step02": "Step04"})
        self.assertGreater(len(changes), 1)  # the boss rewards' changes are kept

    def beaten_without(self, values: dict, *missing: str) -> bool:
        """Is Ganon reachable with every item except `missing` (key settings: any)?"""
        world = World(settings.build(values))
        items = [name for name in world.items if name not in missing] * 9
        state = State(world, items)
        state.can_return = True
        return state.sweep({}).beaten()

    def test_trials_not_needed(self):
        # castle small key (Light Trial), Hover Boots (Forest, Shadow, Fire), Megaton Hammer (Water), Mirror Shield
        # (Spirit)
        values = {**SHUFFLED_KEYS, "bridge": "open"}
        for missing in (KEY, "Item_HoverBoot", "Item_Hammer", "Item_Shield_Mirror"):
            with self.subTest(missing=missing):
                self.assertFalse(self.beaten_without(values, missing))
                self.assertTrue(self.beaten_without({**values, "skip_trials": True}, missing))

    def test_light_arrows_still_needed(self):
        for keys in (SHUFFLED_KEYS, {}):
            self.assertFalse(self.beaten_without({**keys, "bridge": "open", "skip_trials": True}, LIGHT_ARROWS))


if __name__ == "__main__":
    unittest.main()
