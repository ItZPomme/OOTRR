"""Dungeon keys (small_keys, boss_keys): key chests, prudent logic, placement rules, patch and start flags."""

import os
import unittest

from ootrr import keys as keys_mod
from ootrr import settings
from ootrr.fill import generate
from ootrr.patch import build_patch, chest_changes
from ootrr.search import State
from ootrr.world import World

N_SEEDS = max(3, int(os.environ.get("OOTRR_TEST_SEEDS", "100")) // 5)

PRESETS = {
    "own / own": {"small_keys": "own_dungeon", "boss_keys": "own_dungeon"},
    "any / any": {"small_keys": "any_dungeon", "boss_keys": "any_dungeon", "maps_compasses": "shuffle"},
    "random / random": {"small_keys": "random", "boss_keys": "random", "shuffle_rewards": "shuffled"},
    "own / random": {"small_keys": "own_dungeon", "boss_keys": "random", "open_forest": "open"},
    "random / vanilla, beatable": {"small_keys": "random", "accessibility": "beatable"},
    "no logic": {"small_keys": "random", "boss_keys": "any_dungeon", "logic": "none"},
}


def key_items(world):
    return [name for name in world.items if keys_mod.parse_item(name)]


class KeysTest(unittest.TestCase):
    def test_vanilla_has_no_key_data(self):
        world = World(settings.build())
        self.assertFalse(world.key_dungeons)
        self.assertFalse(key_items(world))
        self.assertFalse([l for l in world.locations.values() if l.key_dungeon])

    def test_key_chests_and_counts(self):
        world = World(settings.build({"small_keys": "random", "boss_keys": "random"}))
        small = [l for l in world.locations.values() if " Small Key Chest " in l.name]
        boss = [l for l in world.locations.values() if l.name.endswith(" Boss Key Chest")]
        self.assertEqual(len(small), 37)
        self.assertEqual(len(boss), 6)
        hashes = [h for l in small + boss for h in l.hashes]
        self.assertEqual(len(hashes), len(set(hashes)))
        pool = [item for item, _ in world.pool()]
        for kd in world.key_dungeons.values():
            n = pool.count(keys_mod.item_name(keys_mod.SMALL, kd.game))
            self.assertEqual(n, len(kd.small) + len(kd.freestanding), kd.name)
            self.assertEqual(world.small_key_count(kd), n)
        self.assertEqual(sorted(world.removed_actors()),
                         sorted(k["hash"] for kd in world.key_dungeons.values() for k in kd.freestanding))
        # the ground keys stay with own_dungeon
        self.assertFalse(World(settings.build({"small_keys": "own_dungeon"})).removed_actors())

    def test_prudent_rules(self):
        world = World(settings.build({"small_keys": "any_dungeon", "boss_keys": "any_dungeon"}))
        self.assertIn("has(Small_Key_Forest_Temple, 5)", world.locations["Forest Temple Bow Chest"].rule_src)
        self.assertIn("Boss_Key_Forest_Temple", world.locations["Phantom Ganon"].rule_src)
        triforce = next(e for e in world.events if e.name == "Triforce")
        self.assertIn("Boss_Key_Ganons_Castle", triforce.rule_src)
        self.assertIn("has(Small_Key_Ganons_Castle, 1)", triforce.rule_src)
        # owning every other item is not enough without the keys
        everything = [i for i, _ in world.pool() if not keys_mod.parse_item(i)]
        self.assertFalse(State(world, everything).sweep({}).beaten())

    def test_own_dungeon_key_spots(self):
        world = World(settings.build({"small_keys": "own_dungeon"}))
        for loc in world.locations.values():
            if loc.key_spot:
                kd = world.key_dungeons[loc.key_dungeon]
                self.assertEqual(loc.region, kd.region)
                self.assertIn(loc.key_room, kd.key_rooms)
                self.assertNotIn("Small_Key", loc.rule_src)
            elif loc.key_dungeon:
                self.assertIn("Small_Key", loc.rule_src, loc.name)

    def test_removed(self):
        world = World(settings.build({"small_keys": "removed", "boss_keys": "removed"}))
        flags = world.start_flags()
        self.assertEqual(flags["DungeonInfo.ShadowTemple.SmallKeyNum"], 5)
        self.assertEqual(flags["DungeonInfo.GerudoTrainingGround.SmallKeyNum"], 9)
        self.assertTrue(flags["DungeonInfo.InsideGanonCastle.IsGetBossKey"])
        self.assertNotIn("DungeonInfo.BottomOfTheWell.IsGetBossKey", flags)
        self.assertFalse([i for i, _ in world.pool() if keys_mod.parse_item(i)])
        self.assertNotIn("Small_Key", world.locations["Forest Temple Bow Chest"].rule_src)

    def _check(self, overrides, seeds):
        world = World(settings.build(overrides))
        for seed in seeds:
            result = generate(world, seed)
            if overrides.get("logic") != "none":
                self.assertTrue(State(world).sweep(result.placements).beaten(), seed)
            for name, item in result.placements.items():
                key = keys_mod.parse_item(item)
                if not key:
                    continue
                loc = world.locations[name]
                kind, game = key
                kd = world._key_game[game]
                mode = world.key_mode(kind)
                self.assertTrue(world.can_place(item, loc), (item, name))
                self.assertTrue(loc.is_chest, name)
                if mode == "own_dungeon":
                    self.assertEqual(loc.key_dungeon, kd.name, (item, name))
                if mode == "any_dungeon":
                    self.assertTrue(loc.dungeon or loc.key_dungeon, (item, name))
                if world.location_game_dungeon(loc) != game:
                    self.assertNotEqual(loc.event, "keep", name)
            if world.key_mode(keys_mod.SMALL) == "own_dungeon":
                for kd in world.key_dungeons.values():  # vanilla number of keys per room
                    rooms = {}
                    for name, item in result.placements.items():
                        if item == keys_mod.item_name(keys_mod.SMALL, kd.game):
                            room = world.locations[name].key_room
                            rooms[room] = rooms.get(room, 0) + 1
                    self.assertEqual(rooms, kd.key_rooms, kd.name)
            # patch: the game's key in its own dungeon, a "door key" + chest event elsewhere
            patch = build_patch(world, result, "0" * 10)
            changes = chest_changes(patch)
            for chest in patch["chests"]:
                key = keys_mod.parse_item(chest["item"])
                if not key or chest["item"] == chest["vanilla"]:
                    continue
                change = changes[chest["hashes"][0]]
                if chest["key_dungeon"] == key[1]:
                    self.assertEqual(change["Drop__DropActor"], keys_mod.GAME_ITEM[key[0]])
                else:
                    self.assertEqual(change["Drop__DropActor"], keys_mod.FOREIGN_ACTOR)
                    event = change["GetEventName"]
                    self.assertEqual(patch["key_events"][event], list(key))
                    self.assertIn(event, patch["rsdb_changes"]["EventSetting"])

    def test_presets(self):
        for name, overrides in PRESETS.items():
            with self.subTest(preset=name):
                self._check(overrides, range(1, N_SEEDS + 1))


if __name__ == "__main__":
    unittest.main()
