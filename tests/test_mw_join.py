"""Joining a multiworld: room codes (mw_code), a player's data (multiworld.SlotData), the server's ROOM / GETSLOT
answers and the host session (mw_session), without UPnP."""

from __future__ import annotations

import json
import socket
import tempfile
import unittest
from pathlib import Path

from ootrr import multiworld as mw
from ootrr import mw_protocol as P
from ootrr import settings
from ootrr.mw_code import CodeError, RoomCode, decode, encode
from ootrr.mw_session import Host, SessionError, fetch_slot, join, join_room, room_players, room_state


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class CodeTest(unittest.TestCase):
    def test_round_trip(self):
        for host, port, h in (("82.65.12.201", 38300, "D565610946"), ("10.0.0.1", 1, "0000000000"),
                              ("255.255.255.255", 65535, "FFFFFFFFFF")):
            code = RoomCode(host, port, h)
            text = encode(code)
            self.assertEqual(len(text.replace("-", "")), 20)
            self.assertEqual(decode(text), code)
            self.assertEqual(decode(text.lower().replace("-", " ")), code)  # typed loosely

    def test_mistakes(self):
        text = encode(RoomCode("82.65.12.201", 38300, "D565610946"))
        typo = text[:3] + ("1" if text[3] != "1" else "2") + text[4:]
        with self.assertRaises(CodeError):
            decode(typo)
        with self.assertRaises(CodeError):
            decode(text[:-1])
        with self.assertRaises(CodeError):
            decode("U" * 20)  # not in the alphabet
        with self.assertRaises(CodeError):
            encode(RoomCode("not an ip", 38300, "D565610946"))
        # confusable letters are read as digits
        self.assertEqual(decode(text.replace("1", "I").replace("0", "O")), decode(text))


class SlotDataTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = mw.generate([mw.Player("Ann", settings.build({})), mw.Player("Bo", settings.build({}))], 6)

    def test_round_trip_and_no_spoiler(self):
        data = mw.slot_data(self.result, 1)
        raw = mw.slot_to_json(data)
        self.assertNotIn("players", raw)  # never the other worlds
        self.assertEqual(set(raw["placements"]), set(self.result.placements[1]))
        again = mw.slot_from_json(json.loads(json.dumps(raw)))
        self.assertEqual(again, data)
        self.assertEqual(again.room_hash, mw.room_hash(self.result))

    def test_patch_and_watch_from_slot_data(self):
        data = mw.slot_data(self.result, 0)
        self.assertEqual(mw.slot_patch(data), mw.slot_patch(self.result, 0))
        self.assertEqual(mw.remote_watch(data), mw.remote_watch(self.result, 0))

    def test_load_slot_both_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            full = Path(tmp) / "mw.json"
            full.write_text(json.dumps(mw.to_json(self.result)), encoding="utf-8")
            one = Path(tmp) / "p2.json"
            one.write_text(json.dumps(mw.slot_to_json(mw.slot_data(self.result, 1))), encoding="utf-8")
            self.assertEqual(mw.load_slot(full, 2), mw.load_slot(one))
            self.assertEqual(mw.load_slot(one, 2).slot, 1)
            with self.assertRaises(ValueError):
                mw.load_slot(one, 1)  # someone else's file
            with self.assertRaises(ValueError):
                mw.load_slot(full)  # which player?

    def test_pack(self):
        data = mw.slot_to_json(mw.slot_data(self.result, 0))
        chunks = P.pack(data)
        self.assertTrue(all(len(c) <= P.CHUNK for c in chunks))
        self.assertEqual(P.unpack(chunks), data)


class SessionTest(unittest.TestCase):
    """A real server (Host, in a thread) and real requests, on this PC."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = mw.generate([mw.Player("Ann", settings.build({})), mw.Player("Bo", settings.build({}))], 6)
        cls.file = Path(cls.tmp.name) / "mw.json"
        cls.file.write_text(json.dumps(mw.to_json(cls.result)), encoding="utf-8")
        cls.host = Host(cls.file, port=_free_port(), address="127.0.0.1", use_upnp=False, log=lambda s: None)
        cls.code = cls.host.start()

    @classmethod
    def tearDownClass(cls):
        cls.host.stop()
        cls.tmp.cleanup()

    def test_code(self):
        room = decode(self.code)
        self.assertEqual((room.host, room.port, room.room_hash), ("127.0.0.1", self.host.port, mw.room_hash(self.result)))

    def test_players_and_join(self):
        self.assertEqual(room_players(self.code), ["Ann", "Bo"])
        room, data, path = join(self.code, "bo", Path(self.tmp.name) / "joined")  # name, any case
        self.assertEqual(data, mw.slot_data(self.result, 1))
        self.assertEqual(mw.load_slot(path), data)
        self.assertEqual(join(self.code, 1, Path(self.tmp.name) / "joined")[1].slot, 0)  # or a number
        with self.assertRaises(SessionError):
            join(self.code, "Nobody", Path(self.tmp.name) / "joined")

    def test_refusals(self):
        room = decode(self.code)
        wrong = RoomCode(room.host, room.port, "0123456789")
        with self.assertRaises(SessionError):
            room_players(wrong)
        with self.assertRaises(SessionError):
            fetch_slot(room, 3)
        closed = RoomCode("127.0.0.1", _free_port(), room.room_hash)
        with self.assertRaises(SessionError):
            room_players(closed)


class WaitingRoomTest(unittest.TestCase):
    """The app's host: a waiting room where every player joins with their own settings, then the multiworld is
    generated and served under the same code."""

    def test_join_settings_and_generate(self):
        with tempfile.TemporaryDirectory() as tmp:
            host_settings = settings.build({"shuffle_gifts": False})
            bo_settings = settings.build({"shuffle_skulltulas": "all"})
            host = Host(None, port=_free_port(), address="127.0.0.1", use_upnp=False, log=lambda s: None)
            code = host.open_room("Ann", host_settings, Path(tmp))
            try:
                self.assertEqual(room_state(code), (False, ["Ann"]))
                with self.assertRaises(SessionError):
                    room_players(code)  # not generated yet
                with self.assertRaises(SessionError):
                    fetch_slot(code, 1)
                self.assertEqual(join_room(code, "Bo", settings.build({})), ["Ann", "Bo"])
                self.assertEqual(join_room(code, "bo", bo_settings), ["Ann", "Bo"])  # same player, new settings
                self.assertEqual(join_room(code, "  Cy  ", settings.build({})), ["Ann", "Bo", "Cy"])
                with self.assertRaises(SessionError):
                    join_room(code, "ann", settings.build({}))  # the host's name
                with self.assertRaises(SessionError):
                    join_room(code, "", settings.build({}))
                host.lobby.remove("Cy")
                self.assertEqual(room_state(code), (False, ["Ann", "Bo"]))

                path = host.generate(5)
                generated, names = room_state(code)  # same code, now the multiworld
                self.assertEqual((generated, names), (True, ["Ann", "Bo"]))
                with self.assertRaises(SessionError):
                    join_room(code, "Dee", settings.build({}))  # too late
                result = mw.load(path)
                self.assertEqual(result.players[0].settings, host_settings)
                self.assertEqual(result.players[1].settings, bo_settings)
                data = fetch_slot(code, 2)
                self.assertEqual(data, mw.slot_data(result, 1))
                self.assertEqual(data.settings, bo_settings)
                self.assertNotEqual(decode(code).room_hash, data.room_hash)  # the code holds the room's id
            finally:
                host.stop()

            again = Host(path, port=_free_port(), address="127.0.0.1", use_upnp=False, log=lambda s: None)
            try:  # hosted again from the file: the same code still works
                self.assertEqual(decode(again.start()).room_hash, decode(code).room_hash)
                self.assertEqual(room_players(again.code), ["Ann", "Bo"])
                self.assertEqual(fetch_slot(again.code, 1), mw.slot_data(result, 0))
            finally:
                again.stop()

    def test_failed_generation_reopens(self):
        with tempfile.TemporaryDirectory() as tmp:
            host = Host(None, port=_free_port(), address="127.0.0.1", use_upnp=False, log=lambda s: None)
            code = host.open_room("Ann", settings.build({}), Path(tmp))
            try:
                with self.assertRaises(SessionError):
                    host.generate(1)  # alone
                self.assertEqual(join_room(code, "Bo", settings.build({})), ["Ann", "Bo"])  # still open
            finally:
                host.stop()


if __name__ == "__main__":
    unittest.main()
