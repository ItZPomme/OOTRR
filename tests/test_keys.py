"""Dungeon keys (small_keys, boss_keys): key chests, prudent logic, placement rules, patch and start flags."""

import os
import re
import unittest

from ootrr import keys as keys_mod
from ootrr import settings
from ootrr.fill import generate
from ootrr.patch import build_patch, chest_changes, pickup_changes, skulltula_changes
from ootrr.search import State
from ootrr.spoiler import build as build_spoiler
from ootrr.world import DATA_DIR, World
from seed_pool import submit_cases

def written_zero(loc, dungeon: str) -> bool:
    """The data gives this location a key count of 0 (key_graph worst case: no key door on its way)."""
    key = keys_mod.logic_name(keys_mod.SMALL, dungeon)
    marks = [f'"{loc.name}":'] + [str(h) for h in loc.hashes]
    for path in [DATA_DIR / "keys.json", *sorted((DATA_DIR / "world").glob("*.json"))]:
        for line in path.read_text(encoding="utf-8").splitlines():
            if any(m in line for m in marks) and re.search(rf"has\(\s*{key}\s*,\s*0\s*\)", line):
                return True
    return False


N_SEEDS = max(3, int(os.environ.get("OOTRR_TEST_SEEDS", "100")) // 5)

PRESETS = {
    "own / own": {"small_keys": "own_dungeon", "boss_keys": "own_dungeon"},
    "any / any": {"small_keys": "any_dungeon", "boss_keys": "any_dungeon", "maps_compasses": "shuffle"},
    "random / random": {"small_keys": "random", "boss_keys": "random", "shuffle_rewards": "shuffled"},
    "own / random": {"small_keys": "own_dungeon", "boss_keys": "random", "open_forest": "open"},
    "random / vanilla, beatable": {"small_keys": "random", "accessibility": "beatable"},
    "no logic": {"small_keys": "random", "boss_keys": "any_dungeon", "logic": "none"},
    "own / own, ground keys": {"small_keys": "own_dungeon", "boss_keys": "own_dungeon", "key_locations": "ground",
                               "shuffle_skulltulas": "all"},
    "random / any, ground keys": {"small_keys": "random", "boss_keys": "any_dungeon", "key_locations": "ground",
                                  "shuffle_hearts": "all"},
    "random / random, trials skipped": {"small_keys": "random", "boss_keys": "random", "skip_trials": True,
                                        "accessibility": "beatable"},
}


def key_items(world):
    return [name for name in world.items if keys_mod.parse_item(name)]


class KeysTest(unittest.TestCase):
    def test_vanilla_has_no_key_data(self):
        world = World(settings.build())
        self.assertFalse(world.key_dungeons)
        self.assertFalse(key_items(world))
        self.assertFalse([l for l in world.locations.values() if l.key_dungeon])

    def test_vanilla_keys_are_counted(self):
        """Vanilla keys: events in their vanilla places, so a key count asks for what collecting the keys needs."""
        world = World(settings.build())
        everything = State(world, [n for n in world.items] * 9)
        everything.can_return = True
        everything.sweep({})
        for kd in world._all_key_dungeons.values():  # every vanilla key can be collected with every item
            for event in keys_mod.vanilla_small_events(kd):
                self.assertIn(event, everything.events)
            if kd.boss_key:
                self.assertIn(keys_mod.vanilla_boss_event(kd), everything.events)
        self.assertTrue(everything.beaten())
        # the Gerudo Proving Grounds maze needs the items of its keys, not only the entrance
        nothing = State(world)
        nothing.reached["adult"].add("Gerudo Proving Grounds")
        nothing.sweep({})
        self.assertFalse(nothing.can_reach(world.locations["GPG Maze Final Chest"]))
        self.assertNotIn("Twinrova", [n for n, l in world.locations.items() if nothing.can_reach(l)])
        # removed keys: the counters start full, nothing to collect
        removed = World(settings.build({"small_keys": "removed", "boss_keys": "removed"}))
        self.assertFalse([e for e in removed.events if e.name.startswith(keys_mod.VANILLA_EVENT)])
        self.assertNotIn("Small_Key", removed.locations["GPG Maze Final Chest"].rule_src)

    def test_vanilla_counts(self):
        """vanilla_counts only lowers the counts of the locations it names, and only for vanilla keys."""
        world = World(settings.build())
        fire = world._all_key_dungeons["Fire Temple"]
        rule, small = "has(Small_Key_Fire_Temple, 3)", (keys_mod.SMALL,)
        self.assertIn(">= 3", keys_mod.vanilla_terms(rule, {"Fire Temple": fire}, small, "Fire Temple Map Chest"))
        self.assertIn(">= 2", keys_mod.vanilla_terms(rule, {"Fire Temple": fire}, small, "Fire Temple Small Key Chest 4"))
        own = World(settings.build({"small_keys": "own_dungeon"}))
        self.assertIn("has(Small_Key_Water_Temple, 3)", own.locations["Water Temple Longshot Chest"].rule_src)
        for kd in world._all_key_dungeons.values():  # every name exists, every count is written in its rule
            rules = {kd.small_location(i): str(c.get("rule", kd.rule)) for i, c in enumerate(kd.small)}
            for name, counts in kd.vanilla_counts.items():
                rule = rules.get(name) or own.locations[name].rule_src
                for n in counts:
                    self.assertIn(f", {n})", rule, name)

    def test_key_chests_and_counts(self):
        world = World(settings.build({"small_keys": "random", "boss_keys": "random"}))
        small_names = {kd.small_location(i) for kd in world.key_dungeons.values() for i in range(len(kd.small))}
        boss_names = {kd.boss_location for kd in world.key_dungeons.values() if kd.boss_key}
        small = [world.locations[n] for n in small_names]
        boss = [world.locations[n] for n in boss_names]
        # Fire Temple: 7 chests, Water Temple: 3 (one door unlocked from the start in each, keys.json)
        self.assertEqual(len(small), 35)
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
        # own_dungeon moves the ground keys too: they leave the maps and join the pool
        own = World(settings.build({"small_keys": "own_dungeon"}))
        self.assertEqual(sorted(own.removed_actors()), sorted(world.removed_actors()))
        own_pool = [item for item, _ in own.pool()]
        for kd in own.key_dungeons.values():
            self.assertEqual(own_pool.count(keys_mod.item_name(keys_mod.SMALL, kd.game)), own.small_key_count(kd))
            self.assertEqual(own.small_key_count(kd), len(kd.small) + len(kd.freestanding), kd.name)
        # vanilla small keys: the ground keys stay
        self.assertFalse(World(settings.build({"boss_keys": "own_dungeon"})).removed_actors())

    def test_ground_key_sources_are_spoiler_locations(self):
        world = World(settings.build({"small_keys": "own_dungeon", "key_locations": "ground"}))
        name = "Shadow Temple Giant Pot Small Key"
        loc = world.locations[name]
        item = keys_mod.item_name(keys_mod.SMALL, "ShadowTemple")
        self.assertTrue(loc.shuffle)
        self.assertEqual(loc.pickup, "key")
        self.assertTrue(loc.key_spot)
        self.assertNotIn(12562389953863361839, world.removed_actors())
        self.assertTrue(world.can_place(item, loc))
        self.assertEqual([i for i, _ in world.pool()].count(item), world.small_key_count(
            world.key_dungeons["Shadow Temple"]))

        result = generate(world, seed=1)
        areas = build_spoiler(world, result)["locations"]
        self.assertIn(name, [location for locations in areas.values() for location in locations])

    def test_prudent_rules(self):
        world = World(settings.build({"small_keys": "any_dungeon", "boss_keys": "any_dungeon"}))
        # every location of a key dungeon asks for its keys (its own count from the data, or all of them)
        for loc in world.locations.values():
            kd = world.key_dungeons.get(loc.key_dungeon)
            if kd and not kd.layout and loc.name != kd.boss_location:  # layout: rules used as written
                key = keys_mod.logic_name(keys_mod.SMALL, loc.key_dungeon)
                self.assertTrue(key in loc.rule_src or kd.start_keys or written_zero(loc, loc.key_dungeon), loc.name)
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
            kd = world.key_dungeons.get(loc.key_dungeon)
            if not kd or kd.layout:  # layout: keys anywhere in the dungeon, rules as written
                continue
            if loc.key_spot:
                self.assertEqual(loc.region, kd.region)
                self.assertIn(loc.key_room, kd.key_rooms)
                self.assertNotIn("Small_Key", loc.rule_src)
            elif not kd.start_keys and not written_zero(loc, loc.key_dungeon):
                # (with keys owned from the start, or a count of 0 written, a location may need no key)
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

    def _check(self, overrides, results):
        world = World(settings.build(overrides))
        for seed, result in results:
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
                if world.ground_key(item, loc):  # key_locations = ground: a small key in its own dungeon's map
                    self.assertEqual((kind, world.location_game_dungeon(loc)), (keys_mod.SMALL, game), name)
                else:
                    self.assertTrue(loc.is_chest, name)
                if mode == "own_dungeon":
                    self.assertEqual(loc.key_dungeon, kd.name, (item, name))
                if mode == "any_dungeon":
                    self.assertTrue(loc.dungeon or loc.key_dungeon, (item, name))
                if world.location_game_dungeon(loc) != game:
                    self.assertNotEqual(loc.event, "keep", name)
            if world.key_mode(keys_mod.SMALL) == "own_dungeon":
                for kd in world.key_dungeons.values():  # vanilla number of keys per room
                    if kd.layout:
                        continue
                    rooms = {}
                    for name, item in result.placements.items():
                        if item == keys_mod.item_name(keys_mod.SMALL, kd.game):
                            room = world.locations[name].key_room
                            rooms[room] = rooms.get(room, 0) + 1
                    self.assertEqual(rooms, kd.key_rooms, kd.name)
            # patch: the game's key in its own dungeon, a "door key" + chest event elsewhere
            patch = build_patch(world, result, "0" * 10)
            changes = chest_changes(patch)
            ground, pickups = pickup_changes(patch)
            drops = skulltula_changes(patch, pickups)
            for chest in patch["chests"]:
                key = keys_mod.parse_item(chest["item"])
                if not key or chest["item"] == chest["vanilla"]:
                    continue
                if chest["pickup"] or chest["skulltula"]:  # a ground item giving the game's key
                    h = chest["hashes"][0]
                    actor = ground[h]["Gyaml"] if chest["pickup"] else drops[h]["Drop__DropActor"]
                    self.assertEqual(pickups[actor], keys_mod.GAME_ITEM[keys_mod.SMALL], chest["location"])
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
        results = submit_cases(PRESETS, range(1, N_SEEDS + 1))
        for name, overrides in PRESETS.items():
            with self.subTest(preset=name):
                self._check(overrides, results[name])


if __name__ == "__main__":
    unittest.main()
