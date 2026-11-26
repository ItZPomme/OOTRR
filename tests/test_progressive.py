import itertools
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ootrr import settings as settings_mod  # noqa: E402
from ootrr.patch import (PROGRESSIVE_CHEST, chest_changes, progressive_chains, progressive_chest, progressive_gifts,
                         progressive_location, progressive_scrubs)  # noqa: E402
from ootrr.world import World  # noqa: E402


class ProgressiveChestTests(unittest.TestCase):
    def setUp(self):
        world = World(settings_mod.build())
        self.chains, self.pouch, self.kept = world.progressive, world.progressive_pouch, world.progressive_kept
        self.logic = world.progressive_logic

    def test_two_steps(self):
        for item in ("Item_Hookshot", "Item_Longshot"):
            c = progressive_chest(item, self.chains)
            self.assertEqual((c["Drop__DropActor"], c["Drop__CheckActor"], c["Drop__DropActor_Substitute"]),
                             ("Item_Hookshot", "Item_Hookshot", "Item_Longshot"))
            self.assertTrue(c[PROGRESSIVE_CHEST])

    def test_three_steps(self):
        # weapon chains: the copy of step 2 gives step 2, the others step 3, all after the weapon
        for item, give in (("Item_Range_Bow", "Item_Quiver_Large"), ("Item_Quiver_Medium", "Item_Quiver_Medium"),
                           ("Item_Quiver_Large", "Item_Quiver_Large")):
            c = progressive_chest(item, self.chains, self.pouch, self.kept)
            self.assertEqual((c["Drop__DropActor"], c["Drop__CheckActor"], c["Drop__DropActor_Substitute"]),
                             ("Item_Range_Bow", "Weapon_Range_Bow", give))
        # bomb bags replace each other: small, then large
        for item in ("Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large"):
            c = progressive_chest(item, self.chains, self.pouch, self.kept)
            self.assertEqual((c["Drop__DropActor"], c["Drop__CheckActor"], c["Drop__DropActor_Substitute"]),
                             ("Item_BombBag_Small", "Item_BombBag_Small", "Item_BombBag_Large"))

    def test_strength(self):
        for item, give in (("Item_Gauntlet_Goron", "Item_Gauntlet_Gold"), ("Item_Gauntlet_Silver", "Item_Gauntlet_Silver"),
                           ("Item_Gauntlet_Gold", "Item_Gauntlet_Gold")):
            c = progressive_chest(item, self.chains, self.pouch, self.kept)
            self.assertEqual((c["Drop__DropActor"], c["Drop__CheckActor"], c["Drop__DropActor_Substitute"]),
                             ("Item_Gauntlet_Goron", "Armor_Child_Gauntlet_Goron", give))

    def _patch(self, kinds):
        """Patch with the three gauntlets, each in a chest or a gift, and the Hookshot / Longshot in chests."""
        chests = [{"location": f"L{i}", "hashes": [i + 1], "vanilla": "TBox_Rupee_Green", "item": item,
                   "event": "keep", "gift": kind == "gift", "pickup": "freestanding" if kind == "pickup" else None,
                   "scrub": kind == "scrub"}
                  for i, (item, kind) in enumerate(zip(("Item_Gauntlet_Goron", "Item_Gauntlet_Silver",
                                                        "Item_Gauntlet_Gold"), kinds))]
        chests += [{"location": "H1", "hashes": [10], "vanilla": "TBox_Rupee_Green", "item": "Item_Hookshot",
                    "event": "keep"},
                   {"location": "H2", "hashes": [11], "vanilla": "TBox_Rupee_Green", "item": "Item_Longshot",
                    "event": "keep"}]
        return {"chests": chests, "progressive": self.chains, "progressive_pouch": self.pouch,
                "progressive_kept": self.kept, "progressive_logic": self.logic}

    def test_logic_chains_need_every_copy_progressive(self):
        strength = next(c for c in self.chains if c[0] == "Item_Gauntlet_Goron")
        self.assertIn(strength, progressive_chains(self._patch(("chest", "chest", "chest"))))
        self.assertIn(strength, progressive_chains(self._patch(("chest", "gift", "chest"))))
        patch = self._patch(("chest", "scrub", "chest"))
        self.assertIn(strength, progressive_chains(patch))
        changes = chest_changes(patch)
        self.assertEqual(changes[1]["Drop__DropActor"], "Item_Gauntlet_Goron")
        self.assertIn("Drop__CheckActor", changes[1])
        self.assertEqual(changes[3]["Drop__DropActor"], "Item_Gauntlet_Goron")
        self.assertIn("Drop__CheckActor", changes[10])  # the Hookshot chain is still progressive
        self.assertIn("Item_Gauntlet_Silver", progressive_scrubs(patch))

    def test_chests_skip_the_middle_step_next_to_gifts(self):
        changes = chest_changes(self._patch(("chest", "gift", "chest")))
        for h in (1, 3):
            self.assertEqual(changes[h]["Drop__DropActor_Substitute"], "Item_Gauntlet_Gold")
        changes = chest_changes(self._patch(("chest", "chest", "chest")))
        self.assertEqual(changes[2]["Drop__DropActor_Substitute"], "Item_Gauntlet_Silver")

    def test_gift_questions(self):
        patch = self._patch(("chest", "gift", "chest"))
        gifts = progressive_gifts(patch, {"L1": [("Dm_Goron_0030", 128, "ActorName", "Item_Gauntlet_Goron")]})
        self.assertEqual(gifts, {"Dm_Goron_0030": [[128, "ActorName", "Item_Gauntlet_Goron", [
            ["Item_Gauntlet_Goron", "Armor_Child_Gauntlet_Goron"], ["Item_Gauntlet_Silver", "Item_Gauntlet_Silver"],
            ["Item_Gauntlet_Gold", "Item_Gauntlet_Gold"]]]]})

    def test_bow_gift_next_to_a_quiver_at_a_scrub(self):
        """A quiver sold by a scrub participates in the same progressive chain as a gift."""
        patch = self._patch(("chest", "chest", "chest"))
        patch["chests"] = [
            {"location": "G", "hashes": [], "vanilla": "X", "item": "Item_Range_Bow", "event": "keep", "gift": True},
            {"location": "P", "hashes": [20], "vanilla": "X", "item": "Item_Quiver_Large", "event": "keep",
             "scrub": True}]
        edits = {"G": [("Npc", 1, "ActorName", "X")]}
        self.assertIn("Npc", progressive_gifts(patch, edits))
        self.assertIn("Item_Quiver_Large", progressive_scrubs(patch))
        patch["chests"][1].pop("scrub")  # in a chest: progressive
        self.assertIn("Npc", progressive_gifts(patch, edits))

    def test_mixed_sources_never_ahead_of_the_logic(self):
        """Chests and exact gifts mixed, any order: the real level is never below the logic's count."""
        for kinds in itertools.product(("chest", "gift"), repeat=3):
            patch = self._patch(kinds)
            chain = next(c for c in self.chains if c[0] == "Item_Gauntlet_Goron")
            chests = chest_changes(patch)
            for order in itertools.permutations(range(3)):
                owned = set()
                for n, i in enumerate(order, 1):
                    if kinds[i] == "gift":
                        top = max((chain.index(x) for x in owned), default=-1)
                        owned.add(chain[min(top + 1, 2)])
                    else:
                        c = chests[i + 1]
                        owned.add(c["Drop__DropActor_Substitute"] if chain[0] in owned else c["Drop__DropActor"])
                    self.assertGreaterEqual(max(chain.index(x) for x in owned) + 1, n, (kinds, order, owned))

    def test_logic_chains_never_ahead_of_the_logic(self):
        """All copies in chests, any order: the real level is never below the number of copies (what the logic
        counts). Game model: the bracelet stays in the pouch [hypothesis], the level is the best owned step."""
        for chain in (c for c in self.chains if c[0] in self.logic):
            chests = [progressive_chest(item, self.chains, self.pouch, self.kept) for item in chain]
            for order in itertools.permutations(chests):
                owned = set()
                for n, c in enumerate(order, 1):
                    owned.add(c["Drop__DropActor_Substitute"] if chain[0] in owned else c["Drop__DropActor"])
                    self.assertGreaterEqual(max(chain.index(x) for x in owned) + 1, n, (chain, owned))

    def test_every_opening_order(self):
        """Game model (validated in game, Longshot 2026-11-15): the chest gives Substitute if the pouch counts
        CheckActor; a smaller upgrade never replaces a bigger one; the pouch counts the kept first step and only
        the biggest of the other steps. Any order: step 1 first, last step reached."""
        reverse = {v: k for k, v in self.pouch.items()}
        for chain in self.chains:
            chests = [progressive_chest(item, self.chains, self.pouch, self.kept) for item in chain]
            for order in itertools.permutations(chests):
                owned = set()
                got = []
                for c in order:
                    counted = {i for i in owned if i == chain[0] and i in self.kept}
                    rest = [i for i in owned if i not in counted]
                    if rest:
                        counted.add(max(rest, key=chain.index))
                    check = reverse.get(c["Drop__CheckActor"], c["Drop__CheckActor"])
                    item = c["Drop__DropActor_Substitute"] if check in counted else c["Drop__DropActor"]
                    got.append(item)
                    owned.add(item)
                self.assertEqual(got[0], chain[0], (chain, got))
                self.assertIn(chain[-1], owned, (chain, got))

    def test_other_items(self):
        self.assertIsNone(progressive_chest("Item_HoverBoot", self.chains))

    def test_vanilla_chain_item_still_progressive(self):
        chest = {"location": "Water Temple Longshot Chest", "hashes": [1], "vanilla": "Item_Longshot",
                 "item": "Item_Longshot", "event": "keep"}
        changes = chest_changes({"chests": [chest], "progressive": self.chains})
        self.assertEqual(changes[1]["Drop__DropActor"], "Item_Hookshot")
        self.assertNotIn("GetEventName", changes[1])
        changes = chest_changes({"chests": [dict(chest, event="drop")], "progressive": self.chains})
        self.assertIsNone(changes[1]["GetEventName"])

    def test_ground_items_untouched(self):
        chest = {"location": "x", "hashes": [1], "vanilla": "Obj_Heart_Piece", "item": "Item_Longshot",
                 "event": "keep", "pickup": "freestanding"}
        self.assertEqual(chest_changes({"chests": [chest], "progressive": self.chains}), {})


if __name__ == "__main__":
    unittest.main()
