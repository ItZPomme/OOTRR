"""Multiworld game side: per-player patch (multiworld.slot_patch), item giver (mw_items), Longshot bridge logic
(tools.mw_longshot.Bridge) with a fake game and the server's Room."""

from __future__ import annotations

import itertools
import unittest

from ootrr import multiworld as mw
from ootrr import mw_protocol as P
from ootrr import settings
from ootrr.formats.gamedata import flag_hash
from ootrr.longshot_control import ControlError
from ootrr.mw_items import (BOTTLE_SLOTS, POUCH_ACTION_ACK, POUCH_ACTION_CODES, POUCH_ACTION_REQUEST, ItemGiver,
                            JABU_FED_FLAG, LETTER_QUEST_ENUM, LETTER_QUEST_STEP, LETTER_READ_FLAG)
from ootrr.patch import chest_changes, progressive_chains, progressive_location, progressive_scrubs
from ootrr.tools.mw_longshot import Bridge, BridgeError
from ootrr.tools.mw_server import Room
from ootrr.world import World


class FakeGame:
    """GameData of a game: only the names given exist (like the game: unknown names read None)."""

    def __init__(self, ints: dict[str, int] | None = None, bools: dict[str, bool] | None = None) -> None:
        self.ints = dict(ints or {})
        self.bools = dict(bools or {})
        self.enums: dict[str, str] = {}

    def get_int(self, name):
        return self.ints.get(name)

    def get_bool(self, name):
        return self.bools.get(name)

    def set_int(self, name, value, add=False):
        assert name in self.ints, f"no Int {name}"
        self.ints[name] = self.ints[name] + value if add else value

    def set_bool(self, name, value):
        assert name in self.bools, f"no Bool {name}"
        self.bools[name] = value

    def set_enum(self, name, value):
        assert name in self.enums, f"no Enum {name}"
        self.enums[name] = value


def _pouch(*names: str, owned: tuple[str, ...] = ()) -> FakeGame:
    g = FakeGame({"PlayerStatus.CurrentRupee": 0, "PlayerStatus.MaxLife": 12, "PlayerStatus.Life": 12,
                  "PouchData.Obj_Heart_Piece.StockNum": 0, "PlayerStatus.MPMax": 0, "PlayerStatus.MP": 0},
                 {})
    g.enums["PlayerStatus.LiftGrade"] = "None"
    for n in names:
        g.ints[f"PouchData.{n}.StockNum"] = 1 if n in owned else 0
        g.bools[f"IsGet.{n}"] = n in owned
    return g


class ItemGiverTest(unittest.TestCase):
    def test_simple_item(self):
        g = _pouch("Item_Hookshot", "Item_Longshot")
        ItemGiver(g).give("Item_Hookshot")
        self.assertTrue(g.bools["IsGet.Item_Hookshot"])
        self.assertEqual(g.ints["PouchData.Item_Hookshot.StockNum"], 1)

    def test_progressive(self):
        g = _pouch("Item_Hookshot", "Item_Longshot", owned=("Item_Hookshot",))
        log = ItemGiver(g).give("Item_Hookshot")
        self.assertTrue(g.bools["IsGet.Item_Longshot"])
        self.assertIn("Item_Hookshot -> Item_Longshot", log)
        g = _pouch("Armor_Child_Gauntlet_Goron", "Armor_Adult_Gauntlet_Silver", "Armor_Adult_Gauntlet_Gold",
                   owned=("Armor_Child_Gauntlet_Goron",))
        ItemGiver(g).give("Item_Gauntlet_Gold")
        self.assertTrue(g.bools["IsGet.Armor_Adult_Gauntlet_Silver"])
        self.assertFalse(g.bools["IsGet.Armor_Adult_Gauntlet_Gold"])

    def test_bow_after_a_big_quiver(self):
        """The biggest quiver taken on the ground first: the next copy received is the bow, the quiver stays."""
        g = _pouch("Weapon_Range_Bow", "Item_Quiver_Small", "Item_Quiver_Medium", "Item_Quiver_Large",
                   "Item_Arrow_Normal", owned=("Item_Quiver_Large",))
        g.ints["PouchData.Item_Arrow_Normal.StockNum"] = 50
        ItemGiver(g).give("Item_Quiver_Medium")
        self.assertTrue(g.bools["IsGet.Weapon_Range_Bow"])
        self.assertTrue(g.bools["IsGet.Item_Quiver_Small"])
        self.assertEqual(g.ints["PouchData.Item_Quiver_Small.StockNum"], 1)
        self.assertEqual(g.ints["PouchData.Item_Arrow_Normal.StockNum"], 50)

    def test_strength_and_magic_status(self):
        """The game reads the strength and the magic from PlayerStatus, not from the pouch (2026-11-24)."""
        g = _pouch("Armor_Child_Gauntlet_Goron", "Armor_Adult_Gauntlet_Silver", "Armor_Adult_Gauntlet_Gold",
                   "Item_FairyBless_MP", "Item_FairyBless_MPDouble", "Item_DinFire")
        giver = ItemGiver(g)
        for grade in ("Low", "Middle", "High"):
            giver.give("Item_Gauntlet_Gold")
            self.assertEqual(g.enums["PlayerStatus.LiftGrade"], grade)
        giver.give("Item_FairyBless_MPDouble")  # first copy: the single magic
        self.assertEqual((g.ints["PlayerStatus.MPMax"], g.bools["IsGet.Item_FairyBless_MPDouble"]), (240, False))
        giver.give("Item_FairyBless_MP")
        self.assertEqual((g.ints["PlayerStatus.MPMax"], g.ints["PlayerStatus.MP"]), (480, 480))
        giver.give("Item_DinFire")
        self.assertEqual(g.ints["PlayerStatus.MPMax"], 480)

    def test_rupees_stop_at_the_wallet(self):
        g = _pouch("Item_Wallet_Medium", "Item_Wallet_Large")
        g.ints["PlayerStatus.CurrentRupee"] = 190
        giver = ItemGiver(g)
        giver.give("TBox_Rupee_Purple")
        self.assertEqual(g.ints["PlayerStatus.CurrentRupee"], 200)
        g.bools["IsGet.Item_Wallet_Medium"] = True
        giver.give("TBox_Rupee_Gold")
        self.assertEqual(g.ints["PlayerStatus.CurrentRupee"], 400)

    def test_fixed_chain_given_as_placed(self):
        g = _pouch("Item_Hookshot", "Item_Longshot")
        giver = ItemGiver(g, fixed=["Item_Hookshot"])
        giver.give("Item_Longshot")
        self.assertTrue(g.bools["IsGet.Item_Longshot"])
        giver.give("Item_Hookshot")  # never below what Link owns
        self.assertFalse(g.bools["IsGet.Item_Hookshot"])

    def test_first_bow_includes_small_quiver(self):
        g = _pouch("Weapon_Range_Bow", "Item_Quiver_Small", "Item_Quiver_Medium", "Item_Arrow_Normal")
        ItemGiver(g).give("Item_Range_Bow")
        self.assertTrue(g.bools["IsGet.Weapon_Range_Bow"] and g.bools["IsGet.Item_Quiver_Small"])
        self.assertEqual(g.ints["PouchData.Item_Arrow_Normal.StockNum"], 30)

    def test_bags_fill_ammo(self):
        g = _pouch("Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large", "Item_Bomb")
        ItemGiver(g).give("Item_BombBag_Large")  # progressive: the small one first
        self.assertTrue(g.bools["IsGet.Item_BombBag_Small"])
        self.assertEqual(g.ints["PouchData.Item_Bomb.StockNum"], 20)
        self.assertTrue(g.bools["IsGet.Item_Bomb"])  # without it the menu shows no bombs (seen in game)

    def test_rupees_hearts_bundles(self):
        g = _pouch("Item_Bomb", "Item_Bombchu", "Item_BombBag_Small")
        giver = ItemGiver(g)
        giver.give("TBox_Rupee_Red")
        self.assertEqual(g.ints["PlayerStatus.CurrentRupee"], 20)
        giver.give("Item_BombBundle_Small")  # no bag: 5 rupees
        self.assertEqual(g.ints["PlayerStatus.CurrentRupee"], 25)
        giver.give("Item_BombchuBundle_Small")  # same bag as the bombs (seen: 5 bombchus without a bag)
        self.assertEqual((g.ints["PlayerStatus.CurrentRupee"], g.ints["PouchData.Item_Bombchu.StockNum"]), (30, 0))
        g.bools["IsGet.Item_BombBag_Small"] = True
        giver.give("Item_BombchuBundle_Small")
        self.assertEqual(g.ints["PouchData.Item_Bombchu.StockNum"], 5)
        giver.give("Obj_Heart_Container")
        self.assertEqual((g.ints["PlayerStatus.MaxLife"], g.ints["PlayerStatus.Life"]), (16, 16))
        for _ in range(4):
            giver.give("Obj_Heart_Piece")
        self.assertEqual((g.ints["PlayerStatus.MaxLife"], g.ints["PouchData.Obj_Heart_Piece.StockNum"]), (20, 0))

    def test_bottles(self):
        """No counter: the first free slot of the five (main 0x110d570)."""
        g = FakeGame(bools={f"{s}.IsValid": False for s in BOTTLE_SLOTS})
        g.bools.update({f"{BOTTLE_SLOTS[0]}.IsValid": True, "IsGet.Item_Bottle": False, "IsGet.Item_Bottle_Milk": False,
                        "IsGet.Item_Bottle_Letter": False, "Get_StoneOfWater_GetRutoLetter": False,
                        LETTER_READ_FLAG: False, JABU_FED_FLAG: False})
        g.enums = {f"{s}.BottleItem": "Empty" for s in BOTTLE_SLOTS}
        g.enums[LETTER_QUEST_ENUM] = "Step03"
        giver = ItemGiver(g)
        for item in ("Item_Bottle", "Item_Bottle", "Item_Bottle_Milk", "Item_Bottle_Letter"):
            self.assertNotIn("nothing given", giver.give(item)[-1])
        self.assertTrue(g.bools["Get_StoneOfWater_GetRutoLetter"])
        self.assertEqual([g.enums[f"{s}.BottleItem"] for s in BOTTLE_SLOTS],
                         ["Empty", "Empty", "Empty", "MaxMilk", "Letter"])
        self.assertEqual(g.enums[LETTER_QUEST_ENUM], LETTER_QUEST_STEP)
        self.assertIn("nothing given", giver.give("Item_Bottle")[-1])  # five bottles already

    def test_letter_does_not_regress_a_later_quest_state(self):
        for read, fed in ((True, False), (False, True)):
            with self.subTest(read=read, fed=fed):
                g = FakeGame(bools={f"{s}.IsValid": False for s in BOTTLE_SLOTS})
                g.bools.update({"IsGet.Item_Bottle_Letter": False, "Get_StoneOfWater_GetRutoLetter": False,
                                LETTER_READ_FLAG: read, JABU_FED_FLAG: fed})
                g.enums = {f"{s}.BottleItem": "Empty" for s in BOTTLE_SLOTS}
                g.enums[LETTER_QUEST_ENUM] = "Step10"

                ItemGiver(g).give("Item_Bottle_Letter")

                self.assertEqual(g.enums[LETTER_QUEST_ENUM], "Step10")

    def test_shields_and_songs(self):
        g = _pouch("Weapon_Shield_Deku")
        ItemGiver(g).give("TBox_Shield_Deku")
        self.assertTrue(g.bools["IsGet.Weapon_Shield_Deku"])
        self.assertEqual(g.ints["PouchData.Weapon_Shield_Deku.StockNum"], 1)
        g.bools["IsGet.Item_Melody_SariaSong"] = False
        ItemGiver(g).give("Item_Melody_SariaSong")
        self.assertTrue(g.bools["IsGet.Item_Melody_SariaSong"])

    def test_bottle_hashes(self):
        self.assertEqual(flag_hash("Empty"), 0xbe69de49)  # the value the game writes when it clears a slot
        self.assertEqual(flag_hash(f"{BOTTLE_SLOTS[0]}.BottleItem"), 2101927798)
        self.assertEqual(flag_hash(f"{BOTTLE_SLOTS[0]}.IsValid"), 4087145488)

    def test_pouch_name_of_another_actor(self):
        """The Lens of Truth's counter is Armor_GlassTruth's (seen in game, 2026-11-21)."""
        g = _pouch("Armor_GlassTruth")
        ItemGiver(g).give("Item_GlassTruth")
        self.assertTrue(g.bools["IsGet.Armor_GlassTruth"])
        self.assertEqual(g.ints["PouchData.Armor_GlassTruth.StockNum"], 1)

    def test_unknown_item_writes_nothing(self):
        g = _pouch()
        log = ItemGiver(g).give("Item_Nothing_Like_This")
        self.assertIn("nothing given", log[-1])

    def test_ocarinas(self):
        g = _pouch("Item_Ocarina_Fairy", "Item_Ocarina_Time")
        giver = ItemGiver(g)
        giver.give("Item_Ocarina_Time")
        self.assertTrue(g.bools["IsGet.Item_Ocarina_Fairy"])
        giver.give("Item_Ocarina_Fairy")
        self.assertTrue(g.bools["IsGet.Item_Ocarina_Time"])

    def test_native_flag_hashes(self):
        """The flags of the chains are the native module's (ingame.cpp kChains)."""
        self.assertEqual(flag_hash("IsGet.Weapon_Range_Bow"), 0x69ec28be)
        self.assertEqual(flag_hash("IsGet.Armor_Adult_Gauntlet_Silver"), 0x87e58de3)
        self.assertEqual(flag_hash("IsGet.Item_Hookshot"), 0xff98ed58)


class ProgressiveMixTest(unittest.TestCase):
    """Chain copies split between one's own chests / gifts and other worlds."""

    def test_fill_keeps_chains_progressive(self):
        players = [mw.Player("A", settings.build({})), mw.Player("B", settings.build({}))]
        worlds = mw.build_worlds(players)
        self.assertEqual([c[0] for c in mw.strict_chains(worlds[0])],
                         ["Item_Hookshot", "Item_Range_Bow", "Item_Range_SlingShot", "Item_BombBag_Small",
                          "Item_Gauntlet_Goron", "Item_Scale_Silver", "Item_FairyBless_MP", "Item_Ocarina_Fairy"])
        for seed in range(6):
            result = mw.generate(players, seed, worlds=worlds)
            for k, world in enumerate(worlds):
                data = mw.slot_data(result, k)
                self.assertEqual(mw.fixed_chains(data, world), [])
                self.assertEqual(progressive_chains(mw.slot_patch(result, k, world)), world.progressive)
                for name, (_, item) in result.placements[k].items():
                    loc = world.locations[name]
                    if loc.shuffle and any(item in c for c in mw.strict_chains(world)):
                        self.assertTrue(progressive_location(loc), (seed, name, item))

    def test_fill_with_shuffled_scrubs(self):
        """Deku Scrubs accept few items: the chain rule must leave some."""
        players = [mw.Player(n, settings.build({"shuffle_scrubs": True, "shuffle_songs": "random"})) for n in "AB"]
        worlds = mw.build_worlds(players)
        for seed in range(6):
            result = mw.generate(players, seed, worlds=worlds)
            self.assertLessEqual(result.attempts, 5)
            for k, world in enumerate(worlds):  # quivers and bullet bags may be sold, never the logic's chains
                self.assertEqual(mw.fixed_chains(mw.slot_data(result, k), world), [])

    def test_scrub_chain_is_progressive_in_the_mod_and_bridge(self):
        """A chain copy sold by a Deku Scrub uses the progressive path in both the mod and bridge."""
        players = [mw.Player(n, settings.build({"shuffle_scrubs": True})) for n in "AB"]
        worlds = mw.build_worlds(players)
        result = mw.generate(players, 2, worlds=worlds)
        places = result.placements[0]
        ground = next(n for n, l in worlds[0].locations.items() if l.shuffle and l.scrub and places[n][0] == 0)
        here = next((n for n, p in places.items() if p == (0, "Item_Hookshot")), None)
        if here:
            places[here] = places[ground]
        places[ground] = (0, "Item_Hookshot")
        patch = mw.slot_patch(result, 0, worlds[0])
        self.assertEqual(mw.fixed_chains(mw.slot_data(result, 0), worlds[0]), [])
        done = [c[0] for c in progressive_chains(patch)]
        self.assertIn("Item_Hookshot", done)
        self.assertIn("Item_Hookshot", progressive_scrubs(patch))
        self.assertIn("Item_Scale_Silver", done)

    def test_level_never_below_the_logic(self):
        """Any mix of chests, gifts and received copies, any order: the real level >= the number of copies."""
        data = World(settings.build({}))
        for chain in (c for c in data.progressive if c[0] in data.progressive_logic):
            for kinds in itertools.product(("chest", "gift", "remote"), repeat=len(chain)):
                chests = [{"location": f"L{i}", "hashes": [i + 1], "vanilla": "TBox_Rupee_Green", "item": item,
                           "event": "keep", "gift": kind == "gift"}
                          for i, (item, kind) in enumerate(zip(chain, kinds)) if kind != "remote"]
                patch = {"chests": chests, "progressive": data.progressive, "progressive_pouch": {},
                         "progressive_kept": data.progressive_kept, "progressive_logic": data.progressive_logic,
                         "progressive_remote": True}
                self.assertIn(chain, progressive_chains(patch))
                changes = chest_changes(patch)
                for order in itertools.permutations(range(len(chain))):
                    owned: set[str] = set()
                    for n, i in enumerate(order, 1):
                        if kinds[i] == "chest":
                            c = changes[i + 1]
                            owned.add(c["Drop__DropActor_Substitute"] if chain[0] in owned else c["Drop__DropActor"])
                        else:  # gifts and the bridge: the step after the highest one
                            top = max((chain.index(x) for x in owned), default=-1)
                            owned.add(chain[min(top + 1, len(chain) - 1)])
                        self.assertGreaterEqual(max(chain.index(x) for x in owned) + 1, n, (kinds, order, owned))


class SlotPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = mw.generate([mw.Player("A", settings.build({})), mw.Player("B", settings.build({}))], 4)

    def test_remote_chests(self):
        for slot in range(2):
            patch = mw.slot_patch(self.result, slot)
            self.assertTrue(patch["mw_item_actions"])
            sent = self.result.sent(slot)
            remote = [c for c in patch["chests"] if c.get("remote")]
            self.assertEqual({c["location"] for c in remote}, set(sent))
            changes = chest_changes(patch)
            for c in remote:
                self.assertEqual(c["item"], mw.REMOTE_PLACEHOLDER)
                for h in c["hashes"]:
                    self.assertEqual(changes[int(h)], {"Drop__DropActor": mw.remote_actor(c["index"]),
                                                       "GetEventName": c["remote"]["event"]})
                self.assertEqual(patch["mw_events"][c["remote"]["event"]], mw.location_counter(c["index"]))
                owner, item = sent[c["location"]]
                self.assertEqual(patch["mw_actors"][mw.remote_actor(c["index"])],
                                 {"owner": "AB"[owner], "item": item})
                self.assertIn(c["remote"]["event"], patch["rsdb_changes"]["EventSetting"])
            # own items stay as placed
            for c in patch["chests"]:
                if not c.get("remote"):
                    owner, item = self.result.placements[slot][c["location"]]
                    self.assertEqual((owner, c["item"]), (slot, item))
            self.assertEqual(patch["multiworld"]["locations"], mw.remote_watch(self.result, slot))

    def test_chest_item_texts(self):
        """Each remote chest's item names its owner and the item ("You found B's Hookshot!"); a missing text blocks
        the game, so all three labels are there; control characters of a name are dropped."""
        from ootrr.modbuild import ModBuilder
        builder = ModBuilder.__new__(ModBuilder)
        builder.romfs = None
        texts = builder._mw_texts({"OoTRR_MW_A0001": {"owner": "B", "item": "Item_Hookshot"},
                                   "OoTRR_MW_A0002": {"owner": "Ev\x0eil\n", "item": "Item_Hookshot"}})
        self.assertEqual(set(texts), {f"OoTRR_MW_A000{i}_{k}" for i in (1, 2) for k in ("Name", "GetMessage", "GetCaption")})
        self.assertTrue(texts["OoTRR_MW_A0001_GetMessage"].startswith(b"You found B's "))
        self.assertTrue(texts["OoTRR_MW_A0002_GetMessage"].startswith(b"You found Evil's "))
        self.assertFalse(any(b"\x0e" in t or b"\n" in t for t in texts.values()))

    def test_remote_items_only_in_plain_chests(self):
        from ootrr.world import World
        world = World(settings.build({}))
        for slot in range(2):
            for loc in self.result.sent(slot):
                self.assertTrue(mw.can_hold_remote(world.locations[loc]), loc)


class BridgeTest(unittest.TestCase):
    """Bridge <-> Room (the server's state) with a fake game; messages relayed by hand."""

    def setUp(self):
        players = [mw.Player("A", settings.build({})), mw.Player("B", settings.build({}))]
        self.result = mw.generate(players, 4)
        self.room = Room(self.result)
        self.watch = mw.remote_watch(self.result, 1)  # we are player 2 (B)
        ints = {name: 0 for name in self.watch}
        ints.update({mw.RECEIVED_COUNTER: 0, "PlayerStatus.CurrentRupee": 0, "PlayerStatus.MaxLife": 12,
                     "PlayerStatus.Life": 12, "PouchData.Obj_Heart_Piece.StockNum": 0,
                     POUCH_ACTION_REQUEST: 0, POUCH_ACTION_ACK: 0})
        bools = {"IsGet.Armor_Child_Gauntlet_Goron": True, "IsGet.Armor_Adult_Gauntlet_Silver": False,
                 "IsGet.Armor_Adult_Gauntlet_Gold": False, "IsGet.Item_Ocarina_Fairy": False,
                 "IsGet.Item_Ocarina_Time": False}
        self.game = FakeGame(ints, bools)
        self.out: list[tuple] = []
        self.said: list[str] = []
        self.bridge = Bridge(self.game, self.watch, self.room.hash, 2, ["A", "B"],
                             lambda *f: self.out.append(tuple(str(x) for x in f)), self.said.append)

    def _server(self):
        """Plays the server for the bridge's messages: CHECK -> Room, returns ITEMs for player 2."""
        msgs = []
        for m in self.out:
            if m[0] == P.CHECK:
                self.room.check(1, m[1])
        self.out.clear()
        for i, (finder, item, loc) in enumerate(self.room.received[1]):
            msgs.append([P.ITEM, str(i), str(finder + 1), item, loc])
        return msgs

    def test_found_location_is_sent(self):
        self.bridge.hello()
        self.assertEqual(self.out[0][:3], (P.HELLO, str(P.PROTOCOL), self.room.hash))
        self.bridge.on_server([P.WELCOME, "2", "2", "A", "B"])
        self.assertIn((P.SYNC, "0"), self.out)
        name, loc = next(iter(self.watch.items()))
        self.bridge.on_game({"changed": {f"0x{flag_hash(name):08x}": 1}, "event": False, "loading": False})
        self.assertIn((P.CHECK, loc), self.out)
        self.out.clear()
        self.bridge.on_game({"changed": {f"0x{flag_hash(name):08x}": 1}})
        self.assertEqual(self.out, [])  # once

    def test_scan_after_connect(self):
        name, loc = sorted(self.watch.items())[-1]
        self.game.ints[name] = 1  # found while the bridge was off
        self.bridge.on_server([P.WELCOME, "2", "2", "A", "B"])
        self.assertIn((P.CHECK, loc), self.out)

    def test_received_items_applied_once(self):
        self.bridge.on_server([P.WELCOME, "2", "2", "A", "B"])
        for loc in sorted(self.result.sent(0))[:3]:  # A finds three locations; some hold B's items
            self.room.check(0, loc)
        items = self._server()
        for m in items:
            self.bridge.on_server(m)
        self.bridge.on_game({"event": True})  # in a scene: wait
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], 0)
        self.bridge.on_game({"event": False, "loading": False})
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], len(items))
        # the server sends them again (SYNC from an older save would): nothing is given twice
        for m in items:
            self.bridge.on_server(m)
        self.assertEqual(self.bridge.apply(), 0)
        # an older save reloaded: the counter goes back, the items are given again
        self.game.ints[mw.RECEIVED_COUNTER] = 0
        self.bridge.reloaded()
        for m in items:
            self.bridge.on_server(m)
        self.assertEqual(self.bridge.apply(), len(items))

    def test_pouch_actions_wait_for_ack_and_clear_stale_ack(self):
        self.bridge.on_server([P.ITEM, "0", "1", "Item_Gauntlet_Silver", "Silver Check"])
        self.bridge.on_server([P.ITEM, "1", "1", "Item_Ocarina_Fairy", "Ocarina Check"])

        self.assertEqual(self.bridge.apply(), 0)  # stage the first action, do not count it yet
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], 0)
        self.assertFalse(self.game.bools["IsGet.Armor_Adult_Gauntlet_Silver"])
        self.assertEqual(self.bridge.apply(), 0)  # request the silver gauntlets
        self.assertEqual(self.game.ints[POUCH_ACTION_REQUEST], POUCH_ACTION_CODES["Item_Gauntlet_Silver"])
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], 0)

        self.game.ints[POUCH_ACTION_REQUEST] = 0  # EventFlow cleared the request and ran PouchAdd
        self.game.ints[POUCH_ACTION_ACK] = POUCH_ACTION_CODES["Item_Gauntlet_Silver"]
        self.game.bools["IsGet.Armor_Adult_Gauntlet_Silver"] = True
        self.assertEqual(self.bridge.apply(), 1)
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], 1)

        self.assertEqual(self.bridge.apply(), 0)  # clear the old acknowledgement before the next request
        self.assertEqual(self.game.ints[POUCH_ACTION_ACK], 0)
        self.assertEqual(self.game.ints[POUCH_ACTION_REQUEST], 0)
        self.assertEqual(self.bridge.apply(), 0)
        self.assertEqual(self.game.ints[POUCH_ACTION_REQUEST], POUCH_ACTION_CODES["Item_Ocarina_Fairy"])
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], 1)

        self.game.ints[POUCH_ACTION_REQUEST] = 0
        self.game.ints[POUCH_ACTION_ACK] = POUCH_ACTION_CODES["Item_Ocarina_Fairy"]
        self.game.bools["IsGet.Item_Ocarina_Fairy"] = True
        self.assertEqual(self.bridge.apply(), 1)
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], 2)

    def test_busy_write_queue_keeps_the_item(self):
        """A failed queued write (ControlError) is not a reconnection: the item stays pending, given later."""
        self.bridge.on_server([P.WELCOME, "2", "2", "A", "B"])
        self.bridge.on_server([P.ITEM, "0", "1", "TBox_Rupee_Red", "Somewhere"])
        real = self.game.set_int

        def busy(name, value, add=False):
            raise ControlError("GameData queue append failed: count moving 1 -> 2")
        self.game.set_int = busy
        self.bridge.on_game({"event": False, "loading": False})  # no exception
        self.assertEqual(self.game.ints[mw.RECEIVED_COUNTER], 0)
        self.assertEqual(len([s for s in self.said if "retrying" in s]), 1)
        self.bridge.on_game({"event": False, "loading": False})
        self.assertEqual(len([s for s in self.said if "retrying" in s]), 1)  # said once
        self.game.set_int = real
        self.bridge.on_game({"event": False, "loading": False})
        self.assertEqual((self.game.ints[mw.RECEIVED_COUNTER], self.game.ints["PlayerStatus.CurrentRupee"]), (1, 20))

    def test_not_a_multiworld_mod(self):
        del self.game.ints[mw.RECEIVED_COUNTER]
        with self.assertRaises(BridgeError):
            self.bridge.on_server([P.WELCOME, "2", "2", "A", "B"])


if __name__ == "__main__":
    unittest.main()


class LogTest(unittest.TestCase):
    """Who sent what to whom: server INFO lines, log files, readable names (ootrr.mw_log)."""

    def test_plain_names_and_line(self):
        from ootrr.mw_log import exchange, plain_label
        self.assertEqual(plain_label("Item_Gauntlet_Silver"), "Gauntlet Silver")
        self.assertEqual(plain_label("TBox_Rupee_Purple"), "Rupee Purple")
        self.assertEqual(exchange("Bot", "Pomme", "Hookshot", "GF Rupee Chest"), "Bot -> Pomme: Hookshot (GF Rupee Chest)")

    def test_log_file(self):
        import tempfile
        from pathlib import Path
        from ootrr.mw_log import Log
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "mw.log"
            shown = []
            log = Log(path, echo=shown.append)
            log("first")
            log("second")
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(lines[0].endswith("] first") and lines[0].startswith("["))
            self.assertEqual(shown, lines)

    def test_server_and_bridge_lines(self):
        result = mw.generate([mw.Player("A", settings.build({})), mw.Player("B", settings.build({}))], 4)
        room = Room(result, label=lambda item: f"<{item}>")
        loc, (owner, item) = next((l, p) for l, p in sorted(result.sent(0).items()) if p[0] == 1)
        ev = room.check(0, loc)
        self.assertEqual(ev.info, [f"A -> B: <{item}> ({loc})"])
        # B's bridge logs the server's line, then the item once given in its game
        said: list[str] = []
        game = FakeGame({mw.RECEIVED_COUNTER: 0, "PlayerStatus.CurrentRupee": 0, "PlayerStatus.MaxLife": 12,
                         "PlayerStatus.Life": 12, "PouchData.Obj_Heart_Piece.StockNum": 0}, {})
        bridge = Bridge(game, {}, room.hash, 2, ["A", "B"], lambda *f: None, said.append,
                        label=lambda it: f"<{it}>")
        bridge.on_server([P.WELCOME, "2", "2", "A", "B"])
        bridge.on_server([P.INFO, ev.info[0]])
        bridge.on_server([P.ITEM, "0", "1", item, loc])
        bridge.apply()
        self.assertIn(ev.info[0], said)
        self.assertTrue(any(s.startswith(f"  given in game: <{item}> (from A, {loc}") for s in said), said)
