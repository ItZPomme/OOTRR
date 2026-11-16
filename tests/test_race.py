"""Race helpers (ootrr.race): settings string round trips, rejects bad strings, and the hash symbols."""

import random
import unittest

from ootrr import race, settings, settings_ui
from ootrr.__main__ import seed_to_int


def random_settings(rng: random.Random) -> dict:
    values = {}
    for name in race.FIELDS:
        values[name] = rng.choice(race._values(name))
    limits = {"stones": 3, "medallions": 6, "dungeons": 9, "hearts": 20}
    if values["bridge"] in limits:
        values["bridge_count"] = min(values["bridge_count"], limits[values["bridge"]])
    return settings.build(values)


class SettingsStringTest(unittest.TestCase):
    def test_fields_are_the_shown_settings(self):
        # a setting added to the app must go into a new format (FORMAT + 1), never silently into format 2
        self.assertEqual(set(race.FIELDS), set(settings_ui.SHOWN))
        self.assertEqual(len(race.FIELDS), len(set(race.FIELDS)))
        for name, (lo, hi) in race.INT_FIELDS.items():
            self.assertIn(name, race.FIELDS)
            self.assertLessEqual(lo, settings.defaults()[name])
            self.assertGreaterEqual(hi, settings.defaults()[name])

    def test_format_3_is_frozen(self):
        # changing FIELDS, a setting's values or a range breaks shared strings: bump race.FORMAT instead
        self.assertEqual(race.FORMAT, 3)
        self.assertEqual(race.encode(settings.defaults()), "R3-3FZC33800HV")
        self.assertEqual(race.encode(settings.defaults(), 727557), "R3-3FZC33800V0-727557")
        self.assertEqual(race.encode({"small_keys": "random", "boss_keys": "own_dungeon"}), "R3-3FZC3382M6Q")
        self.assertEqual(race.encode({"gerudo_card": "vanilla"}), "R3-3FZC338021C")
        self.assertEqual(race.encode({"gerudo_fortress": "fast"}), "R3-3FZC33801KT")

    def test_format_2_still_read(self):
        # strings shared with OoTRR 0.3.0 - 0.4.0: same settings, gerudo_card at its default
        self.assertEqual(race.decode("R2-0VZV0RT00K5-727557"), (settings.defaults(), "727557"))
        values, _ = race.decode("R2-0VZV0RT0NRG")
        self.assertEqual((values["small_keys"], values["boss_keys"], values["gerudo_card"]),
                         ("random", "own_dungeon", "random"))
        self.assertEqual(race.decode_full("R2-0VZV0RT00T4-727557-HE668CBE6F0").seed_hash, "E668CBE6F0")

    def test_round_trip(self):
        rng = random.Random(1)
        for _ in range(300):
            values = random_settings(rng)
            seed = str(rng.randrange(10 ** 9)) if rng.random() < 0.5 else None
            s = race.encode(values, seed)
            decoded, got_seed = race.decode(s)
            self.assertEqual(decoded, values, s)
            self.assertEqual(got_seed, seed)
            # case, spaces and look-alike letters do not matter
            parts = s.split("-")
            parts[1] = parts[1].lower().replace("0", "o").replace("1", "l")
            self.assertEqual(race.decode("  " + "-".join(parts) + "\n"), (values, seed))

    def test_same_string_same_seed(self):
        # what the app does with a pasted string: --seed and --set for every non-default value
        import contextlib
        import io
        import tempfile
        from pathlib import Path

        from ootrr.__main__ import main
        s = race.encode({"bridge": "stones", "bridge_count": 2, "shuffle_songs": "shuffle",
                         "starting_age": "random"}, "race")
        names = []
        for _ in range(2):
            values, seed = race.decode(s)
            argv = ["--seed", seed]
            for k, v in values.items():
                if v != settings.defaults()[k]:
                    argv += ["--set", f"{k}={v}"]
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(argv + ["--out", tmp]), 0)
                names.append(sorted(p.name for p in Path(tmp).iterdir()))
        self.assertEqual(names[0], names[1])
        self.assertTrue(names[0][0].startswith(f"OoTRR_{seed_to_int('race')}_"))

    def test_host_seed_hash(self):
        # optional -H<hash> after the seed: covered by the check letters, strings without it are unchanged
        s = race.encode(settings.defaults(), 727557, "e668cbe6f0")
        self.assertEqual(s, "R3-3FZC33800BZ-727557-HE668CBE6F0")
        self.assertEqual(race.decode_full(s), (settings.defaults(), "727557", "E668CBE6F0"))
        self.assertEqual(race.decode(s), (settings.defaults(), "727557"))
        self.assertEqual(race.decode_full(race.encode({}, 5)).seed_hash, None)
        self.assertEqual(race.decode_full(s.lower()).seed_hash, "E668CBE6F0")
        for bad in (s[:-1] + "1",  # hash changed: check fails
                    s[:-1],  # wrong length
                    "R3-3FZC33800BZ-HE668CBE6F0"):  # hash without seed
            with self.assertRaises(race.SettingsStringError, msg=bad):
                race.decode_full(bad)
        with self.assertRaises(race.SettingsStringError):
            race.encode({}, None, "E668CBE6F0")
        with self.assertRaises(race.SettingsStringError):
            race.encode({}, 1, "not-a-hash")

    def test_hidden_settings_are_not_shared(self):
        values = dict(settings.defaults(), shuffle_shops="2", spawn_point=3)
        decoded, _ = race.decode(race.encode(values))
        self.assertEqual(decoded, settings.defaults())

    def test_text_seed_becomes_its_number(self):
        _, seed = race.decode(race.encode({}, "poulet"))
        self.assertEqual(seed, str(seed_to_int("poulet")))
        self.assertEqual(race.decode(race.encode({}, "  "))[1], None)

    def test_rejects(self):
        good = race.encode({"bridge": "medallions"}, 42)
        bad = ["", "hello", "R1-0VZV0RT00AJ", "R1-13TNSA00PC", "R2-0VZV0RT00A", "R2-0VZV0RT00AJX",
               "R2-0VZV0RT00A!",
               "R2-0VZV0RT01AJ",  # one letter changed: check fails
               "R3-3FZC33800H", "R3-3FZC33800HVX", "R3-3FZC33801HV",
               "R3-0VZV0RT00AJ",  # a format 2 payload under the format 3 prefix
               good[:-1] + "3",  # seed changed: check fails
               good + "-1",
               "R2-" + "Z" * 11, "R3-" + "Z" * 11]  # out of range
        for s in bad:
            with self.assertRaises(race.SettingsStringError, msg=s):
                race.decode(s)
        with self.assertRaisesRegex(race.SettingsStringError, "format 4"):
            race.decode("R4-3FZC33800HV")  # a string of a newer OoTRR version
        for s in bad:
            with self.assertRaises(race.SettingsStringError, msg=s):
                race.decode(s)
        with self.assertRaisesRegex(race.SettingsStringError, "format 1"):
            race.decode("R1-13TNSA00PC")  # a string of the previous OoTRR version


class HashSymbolsTest(unittest.TestCase):
    def test_symbols(self):
        self.assertEqual(len(race.SYMBOLS), 32)
        self.assertEqual(len(set(race.SYMBOLS)), 32)
        self.assertEqual(race.hash_symbols("E668CBE6F0"),
                         ["Small Key", "Gold Skulltula", "Hover Boots", "Magic Bean", "Heart Container"])
        self.assertEqual(race.hash_symbols("0000000000"), ["Deku Stick"] * 5)
        self.assertEqual(race.hash_symbols("FFFFFFFFFF"), ["Fairy"] * 5)

    def test_every_symbol_is_drawn(self):
        from ootrr.tools import seed_icons

        class Recorder:
            S = 1.0

            def __init__(self):
                self.calls = 0

            def poly(self, *a, **k):
                self.calls += 1

            oval = line = rect = poly

        for name in race.SYMBOLS:
            r = Recorder()
            seed_icons.draw(r, name, 0, 0, 40)
            self.assertGreater(r.calls, 0, name)

    def test_spoiler_names_the_symbols(self):
        from ootrr import spoiler
        from ootrr.fill import generate
        from ootrr.world import World
        world = World(settings.build())
        sp = spoiler.build(world, generate(world, 5))
        self.assertEqual(sp["hash_symbols"], race.hash_symbols(sp["hash"]))
        self.assertIn("Hash symbols : " + "  ·  ".join(sp["hash_symbols"]), spoiler.to_text(sp))


if __name__ == "__main__":
    unittest.main()
