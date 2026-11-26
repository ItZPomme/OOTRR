import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ootrr import settings as settings_mod  # noqa: E402
from ootrr.fill import Result  # noqa: E402
from ootrr.patch import build_patch  # noqa: E402
from ootrr.search import State  # noqa: E402
from ootrr.world import (
    CHILD_BRIDGE_DOWN_ACTOR,
    CHILD_BRIDGE_FLAG,
    CHILD_BRIDGE_FLOW,
    CHILD_BRIDGE_UP_ACTOR,
    CRATER_SHEIK_EVENT_ACTOR,
    CRATER_SHEIK_EXP,
    DARUNIA_JOY_PENDING_EXP,
    World,
)  # noqa: E402


class StoryGateTests(unittest.TestCase):
    def setUp(self):
        self.world = World(settings_mod.build())

    def can_access(self, location, age, items):
        state = State(self.world, items)
        return state._check(self.world.locations[location].rule, age)

    def test_sheik_locations_use_temple_clears(self):
        self.assertFalse(self.can_access("Sheik at Temple", "adult", ["Forest_Medallion"]))
        self.assertTrue(self.can_access("Sheik at Temple", "adult", ["Forest_Temple_Clear"]))

        medallions = ["Forest_Medallion", "Fire_Medallion", "Water_Medallion"]
        clears = ["Forest_Temple_Clear", "Fire_Temple_Clear", "Water_Temple_Clear"]
        self.assertFalse(self.can_access("Sheik in Kakariko", "adult", medallions))
        self.assertTrue(self.can_access("Sheik in Kakariko", "adult", clears))

    def test_light_arrow_cutscene_uses_shadow_and_spirit_medallions(self):
        temple_clears = ["Shadow_Temple_Clear", "Spirit_Temple_Clear"]
        medallions = ["Shadow_Medallion", "Spirit_Medallion"]
        self.assertFalse(self.can_access("ToT Light Arrows Cutscene", "adult", temple_clears))
        self.assertTrue(self.can_access("ToT Light Arrows Cutscene", "adult", medallions))

    def test_sheik_in_crater_is_available_on_adult_arrival(self):
        self.assertFalse(self.can_access("Sheik in Crater", "child", []))
        self.assertTrue(self.can_access("Sheik in Crater", "adult", []))

    def test_sheik_in_crater_is_started_by_arrival_flow(self):
        gates = self.world.event_entry_gates()["Dm_SY_BancChangeArrive"]
        self.assertEqual(gates["GoTo_DeathMountainCrater"]["condition"], CRATER_SHEIK_EXP)
        self.assertEqual(gates["GoTo_DeathMountainCrater"]["before"], "94")
        self.assertEqual(gates["DeathMountainCrater_Arrive"]["before"], "96")
        self.assertEqual(gates["Dm_SY_BancChangeArrive_DeathMountainCrater_02"]["before"], "258")
        self.assertEqual(self.world.bool_exps()[CRATER_SHEIK_EXP], [
            ("Bool", "Sequence_IsChildhood"),
            ("NOT",),
            ("Bool", "HavePlayedEvent.Dm_MelodyGet_Fire"),
            ("NOT",),
            ("AND",),
        ])
        self.assertIsNone(self.world.actor_changes()[CRATER_SHEIK_EVENT_ACTOR]["RequestEventName"])

    def test_post_clear_darunia_flow_replays_unclaimed_reward(self):
        gate = self.world.event_entry_gates()["Dm_Goron_0030"]["C11"]
        self.assertEqual(gate, {
            "condition": DARUNIA_JOY_PENDING_EXP,
            "entry": "C10",
            "before": "129",
        })
        self.assertEqual(self.world.bool_exps()[DARUNIA_JOY_PENDING_EXP], [
            ("Bool", "HavePlayedEvent.Dm_Goron_0030"),
            ("NOT",),
        ])
        placements = {name: loc.vanilla for name, loc in self.world.locations.items()}
        patch = build_patch(self.world, Result(1, 1, placements), "test")
        self.assertEqual(patch["event_entry_gates"]["Dm_Goron_0030"]["C11"], gate)

    def test_ocarina_checks_use_child_dungeon_clears(self):
        stones = ["Kokiri_Emerald", "Goron_Ruby", "Zora_Sapphire"]
        clears = ["Deku_Tree_Clear", "Dodongos_Cavern_Clear", "Jabu_Jabus_Belly_Clear"]
        for location in ("HF Ocarina of Time Item", "Song from Ocarina of Time"):
            self.assertFalse(self.can_access(location, "child", stones), location)
            self.assertTrue(self.can_access(location, "child", clears), location)

        event_names = {event.name for event in self.world.events}
        self.assertTrue(set(clears) <= event_names)

    def test_child_market_bridge_stays_down(self):
        self.assertFalse(self.world.start_flags()[CHILD_BRIDGE_FLAG])
        self.assertEqual(self.world.event_bools()[CHILD_BRIDGE_FLOW], [(30, "Value", True, False)])
        changes = self.world.actor_changes()
        self.assertIsNone(changes[CHILD_BRIDGE_DOWN_ACTOR]["Presence"])
        self.assertTrue(changes[CHILD_BRIDGE_UP_ACTOR]["__delete"])
        placements = {name: loc.vanilla for name, loc in self.world.locations.items()}
        patch = build_patch(self.world, Result(1, 1, placements), "test")
        self.assertEqual(patch["event_bools"][CHILD_BRIDGE_FLOW], [[30, "Value", True, False]])


if __name__ == "__main__":
    unittest.main()
