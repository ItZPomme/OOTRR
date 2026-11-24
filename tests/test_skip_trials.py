"""skip_trials: Ganon's Castle trials completed from the new game."""

import unittest

from ootrr import settings
from ootrr.fill import generate
from ootrr.patch import build_patch
from ootrr.search import State
from ootrr.world import TRIAL_FLAGS, World

OFF = {"small_keys": "any_dungeon"}
ON = {**OFF, "skip_trials": True}
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

    def test_castle_key_not_needed(self):
        for values, needed in ((OFF, True), (ON, False)):
            world = World(settings.build(values))
            rule = next(e.rule for e in world.events if e.name == "Triforce")
            items = [item for item, _ in world.pool()] + [loc.vanilla for loc in world.locations.values()]
            with_key, without = State(world, items), State(world, [i for i in items if i != KEY])
            self.assertTrue(rule(with_key, "adult"))
            self.assertEqual(rule(without, "adult"), not needed)
            # the Light Arrows are still needed for Ganondorf
            unarmed = State(world, [i for i in items if i != LIGHT_ARROWS])
            self.assertFalse(rule(unarmed, "adult"))


if __name__ == "__main__":
    unittest.main()
