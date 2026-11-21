"""Multiworld game side: per-player patch (multiworld.slot_patch), item giver (mw_items), Longshot bridge logic
(tools.mw_longshot.Bridge) with a fake game and the server's Room."""

from __future__ import annotations

import unittest

from ootrr import multiworld as mw
from ootrr import mw_protocol as P
from ootrr import settings
from ootrr.formats.gamedata import flag_hash
from ootrr.mw_items import ItemGiver
from ootrr.patch import chest_changes
from ootrr.tools.mw_longshot import Bridge, BridgeError
from ootrr.tools.mw_server import Room


class FakeGame:
    """GameData of a game: only the names given exist (like the game: unknown names read None)."""

    def __init__(self, ints: dict[str, int] | None = None, bools: dict[str, bool] | None = None) -> None:
        self.ints = dict(ints or {})
        self.bools = dict(bools or {})

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


def _pouch(*names: str, owned: tuple[str, ...] = ()) -> FakeGame:
    g = FakeGame({"PlayerStatus.CurrentRupee": 0, "PlayerStatus.MaxLife": 12, "PlayerStatus.Life": 12,
                  "PouchData.Obj_Heart_Piece.StockNum": 0},
                 {})
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

    def test_bags_fill_ammo(self):
        g = _pouch("Item_BombBag_Small", "Item_BombBag_Medium", "Item_BombBag_Large", "Item_Bomb")
        ItemGiver(g).give("Item_BombBag_Large")  # progressive: the small one first
        self.assertTrue(g.bools["IsGet.Item_BombBag_Small"])
        self.assertEqual(g.ints["PouchData.Item_Bomb.StockNum"], 20)
        self.assertTrue(g.bools["IsGet.Item_Bomb"])  # without it the menu shows no bombs (seen in game)
        g = _pouch("Weapon_Range_Bow", "Item_Quiver_Small", "Item_Quiver_Medium", "Item_Arrow_Normal")
        ItemGiver(g).give("Item_Range_Bow")
        self.assertTrue(g.bools["IsGet.Weapon_Range_Bow"] and g.bools["IsGet.Item_Quiver_Small"])
        self.assertEqual(g.ints["PouchData.Item_Arrow_Normal.StockNum"], 30)

    def test_rupees_hearts_bundles(self):
        g = _pouch("Item_Bomb", "Item_BombBag_Small", "Item_Bottle")
        giver = ItemGiver(g)
        giver.give("TBox_Rupee_Red")
        self.assertEqual(g.ints["PlayerStatus.CurrentRupee"], 20)
        giver.give("Item_BombBundle_Small")  # no bag: 5 rupees
        self.assertEqual(g.ints["PlayerStatus.CurrentRupee"], 25)
        giver.give("Obj_Heart_Container")
        self.assertEqual((g.ints["PlayerStatus.MaxLife"], g.ints["PlayerStatus.Life"]), (16, 16))
        for _ in range(4):
            giver.give("Obj_Heart_Piece")
        self.assertEqual((g.ints["PlayerStatus.MaxLife"], g.ints["PouchData.Obj_Heart_Piece.StockNum"]), (20, 0))
        giver.give("Item_Bottle")
        giver.give("Item_Bottle")
        self.assertEqual(g.ints["PouchData.Item_Bottle.StockNum"], 2)

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


class SlotPatchTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = mw.generate([mw.Player("A", settings.build({})), mw.Player("B", settings.build({}))], 4)

    def test_remote_chests(self):
        for slot in range(2):
            patch = mw.slot_patch(self.result, slot)
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
                     "PlayerStatus.Life": 12, "PouchData.Obj_Heart_Piece.StockNum": 0})
        self.game = FakeGame(ints, {})
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
