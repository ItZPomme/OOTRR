"""The Forest Temple clear event controls the Prelude and return-to-child logic."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ootrr import settings as settings_mod  # noqa: E402
from ootrr.search import RETURN_TO_CHILD, State  # noqa: E402
from ootrr.world import (LIGHT_ARROW_MEDALLIONS_EXP, NOCTURNE_MEDALLIONS_EXP, World)  # noqa: E402


class PreludeTest(unittest.TestCase):
    def test_prelude_runtime_trigger_uses_forest_medallion(self):
        for options in ({}, {"shuffle_rewards": "shuffled"}):
            world = World(settings_mod.build(options))
            self.assertEqual(
                world.logic_patches()["Market_Adult_Prefab_edc2"]["SageOfForest_IsCompleted_Exp"],
                "OoTRR_HasForestMedallion_Exp",
            )
            self.assertEqual(
                world.bool_exps()["OoTRR_HasForestMedallion_Exp"],
                [("Bool", "IsGet.Item_Medal_Forest")],
            )

    def test_sheik_reward_runtime_gates_use_medallions(self):
        world = World(settings_mod.build({}))
        expressions = world.bool_exps()
        self.assertEqual(
            expressions[LIGHT_ARROW_MEDALLIONS_EXP],
            [
                ("Bool", "IsGet.Item_Medal_Shadow"),
                ("Bool", "IsGet.Item_Medal_Spirit"),
                ("AND",),
                ("Bool", "HavePlayedEvent.Dm_TimeTemple_0130"),
                ("NOT",),
                ("AND",),
            ],
        )
        self.assertEqual(
            expressions[NOCTURNE_MEDALLIONS_EXP],
            [
                ("Bool", "IsGet.Item_Medal_Forest"),
                ("Bool", "IsGet.Item_Medal_Fire"),
                ("AND",),
                ("Bool", "IsGet.Item_Medal_Water"),
                ("AND",),
                ("Bool", "Sequence_IsChildhood"),
                ("NOT",),
                ("AND",),
                ("Bool", "HavePlayedEvent.Dm_Kakariko_0040"),
                ("AND",),
                ("Bool", "HavePlayedEvent.Dm_MelodyGet_Shadow"),
                ("NOT",),
                ("AND",),
            ],
        )
        arrival_gates = world.event_entry_gates()["Dm_SY_BancChangeArrive"]
        self.assertEqual(
            {name: arrival_gates[name] for name in (
                "Dm_SY_BancChangeArrive_KakarikoVillage_01",
                "Dm_SY_BancChangeArrive_KakarikoVillage_02",
            )},
            {
                "Dm_SY_BancChangeArrive_KakarikoVillage_01": {
                    "condition": NOCTURNE_MEDALLIONS_EXP,
                    "entry": "KakarikoVillage_MelodyGet_Shadow",
                },
                "Dm_SY_BancChangeArrive_KakarikoVillage_02": {
                    "condition": NOCTURNE_MEDALLIONS_EXP,
                    "entry": "KakarikoVillage_MelodyGet_Shadow",
                },
            },
        )
        light_arrow_edit = world.logic_graph_edits()["Market_Adult_Prefab_c668"]
        self.assertEqual(light_arrow_edit["expected"], "HoldChallengeCurrentStepCheckOrder")
        self.assertEqual(light_arrow_edit["expected_inputs"]["ChallengeStepName"], "Step02")
        self.assertEqual(light_arrow_edit["output"], "Bool")

    def test_return_to_child_needs_phantom_ganon(self):
        # the Master Sword reads SageOfForest_IsCompleted_Exp: a Forest Medallion from another boss is not enough
        self.assertEqual(RETURN_TO_CHILD, "Forest_Temple_Clear")
        world = World(settings_mod.build({"shuffle_rewards": "shuffled", "free_time_travel": False}))
        self.assertIn("Forest_Temple_Clear", {ev.name for ev in world.events})
        state = State(world, ["Forest_Medallion", "Time_Travel"])
        state.reached["adult"].add("Temple of Time")
        state.update_return()
        self.assertFalse(state.can_return)
        state.receive("Forest_Temple_Clear", False)
        state.update_return()
        self.assertTrue(state.can_return)


if __name__ == "__main__":
    unittest.main()
