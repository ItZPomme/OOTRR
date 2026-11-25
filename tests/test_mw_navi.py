"""Navi's multiworld balloons (mw_navi): texts, table shared by the mod and the bridge, queue."""

from __future__ import annotations

import unittest

from ootrr import multiworld as mw
from ootrr import mw_navi, settings
from ootrr import mw_protocol as P
from ootrr.tools.mw_longshot import Bridge

NAMES = ["A", "B"]


class FakeNavi:
    """The game's side: a balloon asked for is shown (`frame`) unless it has been played."""

    def __init__(self, mark: str | None) -> None:
        self.ints = {} if mark is None else {mark: 0}
        self.bools: dict[str, bool] = {}
        self.asked: str | None = None
        self.shown: list[str] = []
        self.visible = True

    def get_int(self, name):
        return self.ints.get(name)

    def get_bool(self, name):
        return self.bools.get(name, False)

    def set_bool(self, name, value):
        self.bools[name] = value

    def set_enum(self, name, value):
        assert name == mw_navi.REQUEST
        self.asked = value

    def frame(self):
        if self.asked and self.visible:
            flag = f"HavePlayedNaviBalloonMessage.{self.asked}"
            if not self.get_bool(flag):
                self.shown.append(self.asked)
                self.bools[flag] = True
            self.asked = None


class TextTest(unittest.TestCase):
    def test_one_or_two_lines(self):
        self.assertEqual(mw_navi.text("Bob", "Hookshot"), b"You received Hookshot from Bob!")
        long = mw_navi.text("Abcdefghijklmnop", "Magical Boomerang", b"<", b">")
        self.assertEqual(long, b"You received <Magical Boomerang>\nfrom Abcdefghijklmnop!")
        self.assertEqual(mw_navi.text("Bob", ""), b"You received a gift from Bob!")

    def test_control_characters(self):
        self.assertNotIn(b"\x0e", mw_navi.text("Bo\x0eb", "Hook\x0eshot"))


class LayoutTest(unittest.TestCase):
    def test_numbers(self):
        self.assertEqual(len(mw_navi.NUMBERS), len(set(mw_navi.NUMBERS)))
        self.assertEqual(len(mw_navi.NUMBERS), 271)
        self.assertEqual((mw_navi.NUMBERS[0], mw_navi.NUMBERS[-1]), (511, 9))
        self.assertNotIn(118, mw_navi.NUMBERS)  # asked for by the game
        self.assertEqual(mw_navi.raw_value(9), "type009")

    def test_incoming_lists_chain_steps_without_locations(self):
        places = [{"x": (1, "Item_Longshot"), "y": (0, "Item_DinFire")}, {"z": (1, "Item_Boomerang")}]
        self.assertEqual(mw_navi.incoming(places, 1), [(0, "Item_Hookshot"), (0, "Item_Longshot")])
        self.assertEqual(mw_navi.incoming(places, 0), [])

    def test_too_many_pairs(self):
        pairs = [(s, f"Item_{i}") for s in range(4) for i in range(80)] + [(0, "Obj_Rupee_Red")]
        table = mw_navi.layout(pairs)
        self.assertEqual(len(table), len(mw_navi.NUMBERS))
        self.assertEqual({p for p in table.values() if not p[1]}, {(s, "") for s in range(4)})
        self.assertNotIn((0, "Obj_Rupee_Red"), table.values())
        self.assertEqual(table, mw_navi.layout(list(reversed(pairs))))

    def test_slot_data_round_trip_and_patch(self):
        players = [mw.Player(n, settings.build({})) for n in NAMES]
        result = mw.generate(players, 4)
        data = mw.slot_data(result, 1)
        self.assertTrue(data.incoming)
        self.assertEqual(mw.slot_from_json(mw.slot_to_json(data)), data)
        raw = mw.slot_to_json(data)
        del raw["incoming"]  # player data from an older host
        old = mw.slot_from_json(raw)
        self.assertEqual(old.incoming, [])
        self.assertNotIn("mw_navi", mw.slot_patch(old))
        patch = mw.slot_patch(data)["mw_navi"]
        table = mw_navi.layout(data.incoming)
        self.assertEqual(patch["mark"], mw_navi.mark(table, NAMES))
        self.assertEqual({int(n) for n in patch["balloons"]}, set(table))
        self.assertTrue(all(sender == "A" for sender, _ in patch["balloons"].values()))


class AnnouncerTest(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.table = mw_navi.layout([(0, "Item_Hookshot"), (0, "Item_Boomerang")])
        self.number = {pair: mw_navi.raw_value(n) for n, pair in self.table.items()}
        self.game = FakeNavi(mw_navi.mark(self.table, NAMES))
        self.navi = mw_navi.Announcer(self.game, self.table, NAMES, clock=lambda: self.now)

    def play(self, seconds: float) -> None:
        for _ in range(int(seconds * 6)):  # the bridge looks at the game every 10 frames
            self.navi.step()
            self.game.frame()
            self.now += 1 / 6

    def test_one_at_a_time_and_repeated(self):
        self.navi.add(0, "Item_Hookshot")
        self.navi.add(0, "Item_Boomerang")
        self.navi.add(0, "Item_Hookshot")
        self.play(1)
        hook, boomerang = self.number[0, "Item_Hookshot"], self.number[0, "Item_Boomerang"]
        self.assertEqual(self.game.shown, [hook])
        self.play(20)
        self.assertEqual(self.game.shown, [hook, boomerang, hook])

    def test_unknown_item_and_sender(self):
        self.navi.add(0, "Item_DinFire")
        self.navi.add(1, "Item_DinFire")
        self.play(20)
        self.assertEqual(self.game.shown, [self.number[0, ""]])

    def test_asked_again_until_shown(self):
        self.game.visible = False
        self.navi.add(0, "Item_Hookshot")
        self.play(5)
        self.game.asked = None  # dropped by the game
        self.game.visible = True
        self.play(10)
        self.assertEqual(self.game.shown, [self.number[0, "Item_Hookshot"]])

    def test_gives_up(self):
        self.game.visible = False
        self.navi.add(0, "Item_Hookshot")
        self.play(120)
        self.assertIsNone(self.navi.current)

    def test_loading(self):
        self.game.visible = False
        self.navi.add(0, "Item_Hookshot")
        self.play(1)
        self.game.asked, self.game.visible = None, True
        self.navi.reloaded()
        self.play(2)
        self.assertEqual(self.game.shown, [self.number[0, "Item_Hookshot"]])

    def test_mod_without_balloons(self):
        self.game.ints.clear()
        self.navi.add(0, "Item_Hookshot")
        self.play(5)
        self.assertEqual((self.game.shown, self.game.bools), ([], {}))

    def test_long_absence(self):
        for _ in range(60):
            self.navi.add(0, "Item_Hookshot")
        self.assertEqual(len(self.navi.waiting), self.navi.MAX_WAITING)


class BridgeNaviTest(unittest.TestCase):
    def test_item_given_then_said(self):
        pairs = [(0, "Obj_Rupee_Red")]
        table = mw_navi.layout(pairs)
        game = FakeNavi(mw_navi.mark(table, NAMES))
        game.ints.update({mw.RECEIVED_COUNTER: 0, "PlayerStatus.CurrentRupee": 0})
        game.set_int = lambda name, value, add=False: game.ints.__setitem__(name, value)
        bridge = Bridge(game, {}, "H", 2, NAMES, lambda *f: None, lambda line: None, incoming=pairs)
        bridge.on_server([P.WELCOME, "2", "2", *NAMES])
        bridge.on_server([P.ITEM, "0", "1", "Obj_Rupee_Red", "somewhere"])
        for state in ({"event": True}, {}, {}, {}):
            bridge.on_game(state)
            game.frame()
        self.assertEqual(game.ints["PlayerStatus.CurrentRupee"], 20)
        number = next(n for n, p in table.items() if p == pairs[0])
        self.assertEqual(game.shown, [mw_navi.raw_value(number)])


if __name__ == "__main__":
    unittest.main()
