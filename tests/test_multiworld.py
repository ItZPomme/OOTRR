"""Multiworld: shared fill over several worlds (ootrr.multiworld) and the item relay server (tools.mw_server)."""

from __future__ import annotations

import asyncio
import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from ootrr import keys as keys_mod
from ootrr import multiworld as mw
from ootrr import mw_protocol as P
from ootrr import settings
from ootrr.fill import prefill
from ootrr.tools.mw_server import Room, Server

SEEDS = range(max(2, int(os.environ.get("OOTRR_TEST_SEEDS", "100")) // 10))

CASES = {
    "default x2": [{}, {}],
    "default x3": [{}, {}, {}],
    "mixed settings": [{}, {"shuffle_songs": "shuffle", "shuffle_rewards": "shuffled", "small_keys": "any_dungeon"},
                       {"open_forest": "open", "maps_compasses": "shuffle", "shuffle_gifts": True}],
}


def _players(overrides: list[dict]) -> list[mw.Player]:
    return [mw.Player(f"P{i + 1}", settings.build(o)) for i, o in enumerate(overrides)]


class MultiworldFillTest(unittest.TestCase):
    def test_cases(self):
        for name, overrides in CASES.items():
            players = _players(overrides)
            worlds = mw.build_worlds(players)
            for seed in SEEDS:
                with self.subTest(case=name, seed=seed):
                    result = mw.generate(players, seed, worlds=worlds)
                    self._check(worlds, result)

    def _check(self, worlds, result):
        beaten, unreachable = mw.check(worlds, result.placements)
        self.assertTrue(beaten)
        for w, u in zip(worlds, unreachable):
            if w.settings["accessibility"] == "all":
                self.assertEqual(u, [])
        # every world: all its shuffled locations are filled, and the items of every player are those of its pool
        placed: list[Counter] = [Counter() for _ in worlds]
        bound = {item for w in worlds for item, dungeon in w.pool() if dungeon}  # maps and compasses (shuffle)
        for k, (w, places) in enumerate(zip(worlds, result.placements)):
            for loc in w.shuffled_locations():
                self.assertIn(loc.name, places)
            for loc, (owner, item) in places.items():
                if w.locations[loc].shuffle:
                    placed[owner][item] += 1
                # dungeon keys, maps and compasses never leave their world
                if keys_mod.parse_item(item) or item in bound:
                    self.assertEqual(owner, k, f"{item} at {loc}")
                # fixed locations, shuffled rewards and songs stay in their world
                if not w.locations[loc].shuffle:
                    self.assertEqual(owner, k, f"fixed location {loc}")
        for owner, w in enumerate(worlds):
            self.assertEqual(placed[owner], Counter(item for item, _ in w.pool()))
        # some items really go to other players
        self.assertTrue(any(result.sent(k) for k in range(len(worlds))))

    def test_same_seed_same_result(self):
        players = _players([{}, {}])
        a = mw.generate(players, 7)
        b = mw.generate(players, 7)
        self.assertEqual(a.placements, b.placements)
        self.assertEqual(mw.room_hash(a), mw.room_hash(b))

    def test_file_round_trip(self):
        players = _players([{}, {"shuffle_songs": "shuffle"}])
        worlds = mw.build_worlds(players)
        result = mw.generate(players, 3, worlds=worlds)
        data = mw.to_json(result, worlds)
        again = mw.from_json(data)
        self.assertEqual(again.placements, result.placements)
        self.assertEqual(mw.room_hash(again), data["hash"])
        # a game made by an earlier version keeps its hash after an update
        older = mw.to_json(mw.from_json({**data, "version": "0.0.1"}))
        self.assertNotEqual(older["hash"], data["hash"])
        self.assertEqual(older["hash"], mw.room_hash(mw.from_json(older)))
        self.assertIn("P2", mw.to_text(data))

    def test_refused(self):
        with self.assertRaises(ValueError):
            mw.build_worlds(_players([{}]))
        with self.assertRaises(ValueError):
            mw.build_worlds([mw.Player("A", settings.build({})), mw.Player("A", settings.build({}))])
        with self.assertRaises(ValueError):
            mw.build_worlds(_players([{}, {"logic": "none"}]))

    def test_prefill_keeps_single_world_draws(self):
        """fill.prefill is the start of fill._attempt: the single-world seeds must not change (generator.cpp)."""
        import random
        from ootrr.fill import _attempt
        from ootrr.world import World
        world = World(settings.build({}))
        a = _attempt(world, random.Random(5))
        rng = random.Random(5)
        placements, _, _ = prefill(world, rng)
        for loc, item in placements.items():
            self.assertEqual(a[loc], item)


class Client:
    """A fake game for the server tests."""

    def __init__(self, reader, writer):
        self.reader, self.writer = reader, writer

    @classmethod
    async def connect(cls, port: int) -> "Client":
        return cls(*await asyncio.open_connection("127.0.0.1", port))

    async def send(self, *fields):
        self.writer.write(P.encode(*fields))
        await self.writer.drain()

    async def read(self) -> list[str]:
        return P.decode(await asyncio.wait_for(self.reader.readuntil(b"\n"), 5))

    async def read_until(self, cmd: str) -> list[str]:
        while True:
            msg = await self.read()
            if msg[0] == cmd:
                return msg

    def close(self):
        self.writer.close()


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        players = _players([{}, {}])
        cls.result = mw.generate(players, 11)

    def _room(self, path: Path | None = None, release: bool = True) -> Room:
        return Room(self.result, path, release)

    def test_room_check_and_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mw.state.json"
            room = self._room(path)
            loc, (owner, item) = next(iter(self.result.sent(0).items()))
            ev = room.check(0, loc)
            self.assertEqual(ev.items, [(owner, 0)])
            self.assertEqual(room.received[owner], [(0, item, loc)])
            self.assertEqual(room.check(0, loc).items, [])  # found twice: nothing more
            self.assertEqual(room.check(0, "No Such Place").items, [])
            own = next(iter(self.result.own_items(0)))
            self.assertEqual(room.check(0, own).items, [])  # the game gives its own items itself
            room.save()
            again = self._room(path)
            self.assertEqual(again.received, room.received)
            self.assertEqual(again.checked, room.checked)

    def test_release_on_goal(self):
        room = self._room()
        ev = room.finish(0)
        self.assertEqual(len(room.received[1]), len(self.result.sent(0)))
        self.assertEqual(len(ev.items), len(self.result.sent(0)))
        self.assertEqual(room.finish(0).items, [])
        quiet = self._room(release=False)
        quiet.finish(0)
        self.assertEqual(quiet.received[1], [])

    def test_network(self):
        asyncio.run(self._network())

    async def _network(self):
        room = self._room()
        server = Server(room)
        server.log = lambda text: None
        srv = await asyncio.start_server(server.handle, "127.0.0.1", 0, limit=P.MAX_LINE)
        port = srv.sockets[0].getsockname()[1]
        try:
            # wrong room, wrong slot, no HELLO
            bad = await Client.connect(port)
            await bad.send(P.HELLO, P.PROTOCOL, "WRONGHASH", 1)
            self.assertEqual((await bad.read())[:2], [P.ERROR, P.E_ROOM])
            bad.close()
            bad = await Client.connect(port)
            await bad.send(P.HELLO, P.PROTOCOL, room.hash, 3)
            self.assertEqual((await bad.read())[:2], [P.ERROR, P.E_SLOT])
            bad.close()
            bad = await Client.connect(port)
            await bad.send(P.CHECK, "x")
            self.assertEqual((await bad.read())[:2], [P.ERROR, P.E_HELLO])
            bad.close()

            a, b = await Client.connect(port), await Client.connect(port)
            await a.send(P.HELLO, P.PROTOCOL, room.hash, 1, "P1")
            self.assertEqual(await a.read(), [P.WELCOME, "1", "2", "P1", "P2"])
            await b.send(P.HELLO, P.PROTOCOL, room.hash, 2)
            await b.read_until(P.WELCOME)
            await b.send(P.SYNC, 0)

            sent = sorted(self.result.sent(0).items())
            to_b = [(loc, item) for loc, (owner, item) in sent if owner == 1]
            loc, item = to_b[0]
            await a.send(P.CHECK, loc)
            self.assertEqual(await b.read_until(P.ITEM), [P.ITEM, "0", "1", item, loc])
            self.assertEqual(await a.read_until(P.SENT), [P.SENT, "2", item, loc])

            # B reconnects without having applied the item: SYNC 0 sends it again, SYNC 1 sends nothing
            b.close()
            b = await Client.connect(port)
            await b.send(P.HELLO, P.PROTOCOL, room.hash, 2)
            await b.read_until(P.WELCOME)
            await b.send(P.SYNC, 0)
            self.assertEqual(await b.read_until(P.ITEM), [P.ITEM, "0", "1", item, loc])
            await b.send(P.SYNC, 1)
            await b.send(P.PING)
            self.assertEqual(await b.read_until(P.PONG), [P.PONG])

            # A finishes: the rest of A's items for B are released
            await a.send(P.GOAL)
            indexes = set()
            while len(indexes) < len(to_b) - 1:
                msg = await b.read_until(P.ITEM)
                indexes.add(int(msg[1]))
            self.assertEqual(indexes, set(range(1, len(to_b))))
            a.close()
            b.close()
        finally:
            srv.close()
            await srv.wait_closed()


if __name__ == "__main__":
    unittest.main()
