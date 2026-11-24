"""Key logic written in the data: a rule per key chest (keys.json) and key counts in location rules."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from ootrr import keys as keys_mod
from ootrr import patch as patch_mod
from ootrr import settings
from ootrr.fill import generate
from ootrr.native_logic import Exporter
from ootrr.world import DATA_DIR, DataError, World

COUNT = "has(Small_Key_Forest_Temple, 1)"


def data_copy(edit) -> Path:
    """A copy of ootrr/data with chests.json and keys.json changed by edit(chests, keys)."""
    tmp = Path(tempfile.mkdtemp(prefix="ootrr_keys_"))
    shutil.rmtree(tmp)
    shutil.copytree(DATA_DIR, tmp)
    chests_path, keys_path = tmp / "world" / "chests.json", tmp / "keys.json"
    chests = json.loads(chests_path.read_text(encoding="utf-8"))
    keys = json.loads(keys_path.read_text(encoding="utf-8"))
    edit(chests["locations"], keys["dungeons"])
    chests_path.write_text(json.dumps(chests), encoding="utf-8")
    keys_path.write_text(json.dumps(keys), encoding="utf-8")
    return tmp


def with_counts(chests, keys):
    keys["Forest Temple"]["layout"] = False  # these tests are about the prudent (non-layout) rules
    chests["Forest Temple Bow Chest"]["rule"] = COUNT
    chests["Forest Temple Compass Chest"]["rule"] = "can_use(Bow)"  # no count: the prudent "all the keys"
    keys["Forest Temple"]["small"][0]["rule"] = "True"
    keys["Forest Temple"]["boss_key"]["rule"] = "can_use(Bow) and has(Small_Key_Forest_Temple, 3)"


class KeyTermsTest(unittest.TestCase):
    def test_helpers(self):
        rule = "can_use(Bow) and has(Small_Key_Forest_Temple, 2) and Boss_Key_Fire_Temple"
        self.assertTrue(keys_mod.mentions(rule, keys_mod.SMALL, "Forest Temple"))
        self.assertFalse(keys_mod.mentions(rule, keys_mod.SMALL, "Fire Temple"))
        self.assertTrue(keys_mod.mentions(rule, keys_mod.BOSS, "Fire Temple"))
        self.assertEqual(keys_mod.without_key_terms(rule), "can_use(Bow) and True and True")
        self.assertEqual(keys_mod.without_key_terms(rule, (keys_mod.BOSS,)),
                         "can_use(Bow) and has(Small_Key_Forest_Temple, 2) and True")
        self.assertEqual(keys_mod.conjuncts("True and can_use(Bow)"), {"can_use(Bow)"})
        # split at the top level only: parentheses and "or" stay whole
        self.assertEqual(keys_mod.conjuncts("x and (y and z or w) and has(K, 2)"), {"x", "y and z or w", "has(K, 2)"})
        self.assertEqual(keys_mod.conjuncts("a and b or c"), {"a and b or c"})
        self.assertEqual(keys_mod.conjuncts("(a and b)"), {"a", "b"})
        self.assertEqual(keys_mod.conjuncts("(a) or (b)"), {"(a) or (b)"})
        self.assertEqual(keys_mod.clamp_counts("has(Small_Key_Shadow_Temple, 5)", "Shadow Temple", 4),
                         "has(Small_Key_Shadow_Temple, 4)")

    def test_ground_keys_counted(self):
        """The data writes the dungeon's total (ground key included): every shuffled mode moves the ground key into
        the pool, so a rule asking for all the keys keeps its count."""
        for mode in ("own_dungeon", "any_dungeon", "random"):
            world = World(settings.build({"small_keys": mode, "boss_keys": mode}))
            kd = world.key_dungeons["Shadow Temple"]
            self.assertEqual(world.small_key_count(kd), 5, mode)
            self.assertIn("has(Small_Key_Shadow_Temple, 5)", world.locations[kd.boss_location].rule_src, mode)


class KeyChestNamesTest(unittest.TestCase):
    def test_named_key_chests(self):
        def names(chests, keys):
            keys["Forest Temple"]["small"][0]["name"] = "Forest Temple First Room Key Chest"
            keys["Forest Temple"]["boss_key"]["name"] = "Forest Temple Boss Key Room Chest"
        data = data_copy(names)
        try:
            world = World(settings.build({"small_keys": "any_dungeon", "boss_keys": "any_dungeon"}), data)
            self.assertIn("Forest Temple First Room Key Chest", world.locations)
            self.assertIn("Forest Temple Boss Key Room Chest", world.locations)
            self.assertNotIn("Forest Temple Small Key Chest 1", world.locations)
            self.assertIn("Forest Temple Small Key Chest 2", world.locations)  # the others keep their numbers
        finally:
            shutil.rmtree(data, ignore_errors=True)


FLARE_DANCER_CHEST = 8757492004108970488  # Fire Temple, behind the hammer door
ROOM_22_CHEST = 1705064956286753527  # Fire Temple, room 22: was the 8th small key chest


def room_22_chest(world):
    return next(loc for loc in world.locations.values() if ROOM_22_CHEST in loc.hashes)


class UnlockedDoorTest(unittest.TestCase):
    """Fire Temple: the hammer door is unlocked from the start (keys.json unlocked_doors), its key chest holds an
    item and no small key is owned from the start."""

    def test_flag_and_counter(self):
        counter = "DungeonInfo.FireTemple.SmallKeyNum"
        for mode in ("vanilla", "own_dungeon", "any_dungeon", "random"):
            world = World(settings.build({"small_keys": mode}))
            flags = world.start_flags()
            self.assertIs(flags["#749909151"], True, mode)
            self.assertNotIn(counter, flags, mode)
            room_22_chest(world)  # a normal location
        removed = World(settings.build({"small_keys": "removed"}))
        self.assertEqual(removed.start_flags()[counter], 7)

    def test_no_count_above_the_keys(self):
        world = World(settings.build({"small_keys": "any_dungeon"}))
        for loc in world.locations.values():
            self.assertNotIn("has(Small_Key_Fire_Temple, 8)", loc.rule_src, loc.name)


class StartKeysTest(unittest.TestCase):
    """keys.json start_keys: small keys owned from the start, taken off the rules' counts."""

    def test_clamp(self):
        self.assertEqual(keys_mod.clamp_counts("has(Small_Key_Fire_Temple, 4)", "Fire Temple", 7, 1),
                         "has(Small_Key_Fire_Temple, 3)")
        self.assertEqual(keys_mod.clamp_counts("has(Small_Key_Fire_Temple, 1)", "Fire Temple", 7, 1), "True")

    def test_start_key_alone_needs_no_key(self):
        """A count covered by the start key becomes True, and the prudent 'all the keys' is not added back."""
        def one_key(chests, keys):
            keys["Fire Temple"]["start_keys"] = 1
            name = next(n for n, body in chests.items() if FLARE_DANCER_CHEST in body.get("hashes", []))
            chests[name]["rule"] = "can_use(Megaton_Hammer) and has(Small_Key_Fire_Temple, 1)"
        data = data_copy(one_key)
        try:
            world = World(settings.build({"small_keys": "any_dungeon"}), data)
            self.assertEqual(world.start_flags()["DungeonInfo.FireTemple.SmallKeyNum"], 1)
            chest = next(l for l in world.locations.values() if FLARE_DANCER_CHEST in l.hashes)
            self.assertNotIn("Small_Key_Fire_Temple", chest.rule_src)
        finally:
            shutil.rmtree(data, ignore_errors=True)


class KeyCountsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = data_copy(with_counts)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.data, ignore_errors=True)

    def world(self, **values):
        return World(settings.build(values), self.data)

    def test_count_replaces_all_keys(self):
        world = self.world(small_keys="any_dungeon")
        bow = world.locations["Forest Temple Bow Chest"].rule_src
        self.assertIn(COUNT, bow)
        self.assertNotIn("has(Small_Key_Forest_Temple, 5)", bow)
        # the other locations still need all the keys
        self.assertIn("has(Small_Key_Forest_Temple, 5)", world.locations["Forest Temple Compass Chest"].rule_src)

    def test_key_chest_rules(self):
        world = self.world(small_keys="any_dungeon", boss_keys="any_dungeon")
        first = world.locations[world.key_dungeons["Forest Temple"].small_location(0)].rule_src
        self.assertNotIn("can_use(Bow)", first)  # its own rule, not the dungeon's
        boss = world.locations[world.key_dungeons["Forest Temple"].boss_location].rule_src
        self.assertIn("has(Small_Key_Forest_Temple, 3)", boss)
        self.assertNotIn("has(Small_Key_Forest_Temple, 5)", boss)

    def test_unshuffled_keys_are_owned(self):
        for values in ({}, {"small_keys": "removed"}, {"boss_keys": "any_dungeon"}):
            world = self.world(**values)
            self.assertNotIn("Small_Key", world.locations["Forest Temple Bow Chest"].rule_src, values)

    def test_own_dungeon_key_spots(self):
        world = self.world(small_keys="own_dungeon")
        first = world.locations[world.key_dungeons["Forest Temple"].small_location(0)]
        self.assertTrue(first.key_spot)
        self.assertNotIn("Small_Key", first.rule_src)

    def test_generates(self):
        for values in ({"small_keys": "any_dungeon", "boss_keys": "any_dungeon"},
                       {"small_keys": "own_dungeon", "boss_keys": "random"}, {}):
            world = self.world(**values)
            for seed in range(5):
                generate(world, seed)

    def test_native_export(self):
        Exporter(self.data).world()  # key terms are always true for the native generator

    def test_key_chest_rule_must_stay_within_the_dungeons(self):
        def stricter(chests, keys):
            # only checked against an explicit dungeon rule (without one, it is made of the key chests' rules)
            keys["Forest Temple"]["layout"] = False
            keys["Forest Temple"]["rule"] = "can_use(Bow)"
            keys["Forest Temple"]["small"][0]["rule"] = "can_use(Megaton_Hammer)"
        data = data_copy(stricter)
        try:
            with self.assertRaises(DataError):
                World(settings.build({"small_keys": "any_dungeon"}), data)
        finally:
            shutil.rmtree(data, ignore_errors=True)


def forest_layout(chests, keys):
    """Forest Temple marked as described: two chests behind small keys, the other chests need none."""
    forest = keys["Forest Temple"]
    forest["layout"] = True
    for body in [b for b in chests.values() if isinstance(b, dict) and b.get("region") == "Forest Temple"] + forest["small"] + [
            forest["boss_key"]]:
        if "rule" in body:
            body["rule"] = keys_mod.without_key_terms(body["rule"], (keys_mod.SMALL,))
    chests["Forest Temple Bow Chest"]["rule"] = "has(Small_Key_Forest_Temple, 2)"
    chests["Forest Temple Compass Chest"]["rule"] = "can_use(Bow) and has(Small_Key_Forest_Temple, 5)"


class LayoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = data_copy(forest_layout)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.data, ignore_errors=True)

    def test_rules_used_as_written(self):
        world = World(settings.build({"small_keys": "own_dungeon"}), self.data)
        locs = world.locations
        self.assertNotIn("Small_Key", locs["Forest Temple Purple Rupee Chest"].rule_src)  # no count: no key
        self.assertIn("has(Small_Key_Forest_Temple, 2)", locs["Forest Temple Bow Chest"].rule_src)
        # every chest of the dungeon may hold its keys, not only the vanilla key rooms
        spots = {l.name for l in locs.values() if l.key_spot and l.key_dungeon == "Forest Temple"}
        self.assertIn("Forest Temple Bow Chest", spots)
        self.assertIn("Forest Temple Purple Rupee Chest", spots)
        # the other dungeons stay prudent
        shadow = [l for l in locs.values() if l.key_dungeon == "Shadow Temple" and not l.key_spot]
        self.assertTrue(shadow and all("Small_Key_Shadow_Temple" in l.rule_src for l in shadow))

    def test_keys_anywhere_in_the_dungeon(self):
        world = World(settings.build({"small_keys": "own_dungeon"}), self.data)
        item = keys_mod.item_name(keys_mod.SMALL, "ForestTemple")
        rooms = world.key_dungeons["Forest Temple"].key_rooms
        outside_rooms = False
        for seed in range(30):
            result = generate(world, seed)
            spots = [name for name, placed in result.placements.items() if placed == item]
            self.assertEqual(len(spots), 5, seed)
            for name in spots:
                self.assertEqual(world.locations[name].key_dungeon, "Forest Temple")
                outside_rooms |= world.locations[name].key_room not in rooms
            # a key is never behind a count it is needed for: the 5th key is not in the compass chest
            self.assertNotEqual(result.placements.get("Forest Temple Compass Chest"), item, seed)
        self.assertTrue(outside_rooms)  # not tied to the vanilla rooms any more


if __name__ == "__main__":
    unittest.main()


class GroundKeysTest(unittest.TestCase):
    """key_locations = ground: a small key may lie on the ground (Heart Container, Piece of Heart, Gold Skulltula
    drop) in its own dungeon, given as the game's key item."""

    FIRE = keys_mod.item_name(keys_mod.SMALL, "FireTemple")
    FOREST = keys_mod.item_name(keys_mod.SMALL, "ForestTemple")
    FIRE_BOSS = keys_mod.item_name(keys_mod.BOSS, "FireTemple")

    def test_placement(self):
        chests = World(settings.build({"small_keys": "any_dungeon"}))
        heart = chests.locations["Fire Temple Volvagia Heart"]
        self.assertFalse(chests.can_place(self.FIRE, heart))  # default: chests only
        for mode in ("own_dungeon", "any_dungeon", "random"):
            world = World(settings.build({"small_keys": mode, "boss_keys": mode, "key_locations": "ground"}))
            heart = world.locations["Fire Temple Volvagia Heart"]
            self.assertTrue(world.can_place(self.FIRE, heart), mode)
            self.assertFalse(world.can_place(self.FOREST, heart), mode)  # another dungeon's key: wrong counter
            self.assertFalse(world.can_place(self.FIRE_BOSS, heart), mode)  # boss keys stay in chests
            for loc in world.locations.values():
                if (loc.pickup or loc.skulltula) and world.location_game_dungeon(loc) is None:
                    self.assertFalse(world.can_place(self.FIRE, loc), loc.name)  # outside the dungeons

    def test_ground_item(self):
        loc = {"location": "Fire Temple Volvagia Heart", "item": self.FIRE, "key_dungeon": "FireTemple",
               "pickup": "boss", "hashes": [1], "vanilla": "Obj_Heart_Container"}
        self.assertEqual(patch_mod.ground_item(loc), "Item_Dungeon_SmallKey")
        self.assertEqual(patch_mod.ground_item({**loc, "item": "Item_Bow"}), "Item_Bow")
        with self.assertRaises(ValueError):
            patch_mod.ground_item({**loc, "item": self.FOREST})

    def test_seeds_place_ground_keys(self):
        world = World(settings.build({"small_keys": "own_dungeon", "key_locations": "ground"}))
        found = False
        for seed in range(10):
            result = generate(world, seed=seed)
            patch = patch_mod.build_patch(world, result, "0" * 10)
            _, pickups = patch_mod.pickup_changes(patch)
            ground = [l for l in patch["chests"] if (l["pickup"] or l["skulltula"]) and keys_mod.parse_item(l["item"])]
            for loc in ground:
                self.assertEqual(keys_mod.parse_item(loc["item"])[1], loc["key_dungeon"])
            if ground:
                found = True
                self.assertIn("Item_Dungeon_SmallKey", pickups.values())
        self.assertTrue(found)
