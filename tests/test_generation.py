import os
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ootrr import settings as settings_mod  # noqa: E402
from ootrr.fill import generate  # noqa: E402
from ootrr.formats.byml import F64, I64, U32, U64, HashDict, read_byml, write_byml  # noqa: E402
from ootrr.patch import build_patch, chest_changes  # noqa: E402
from ootrr.rules import RuleCompiler, RuleError  # noqa: E402
from ootrr.search import State, is_beatable  # noqa: E402
from ootrr.spoiler import build as build_spoiler  # noqa: E402
from ootrr.world import World  # noqa: E402

N_SEEDS = int(os.environ.get("OOTRR_TEST_SEEDS", "100"))

PRESETS = {
    "jeu d'origine": {},
    "sans monocle": {"logic_lens_required": False},
    "ganon seulement": {"accessibility": "beatable"},
    "forêt ouverte": {"open_forest": "open", "open_door_of_time": True, "bridge": "medallions"},
    "cartes mélangées": {"maps_compasses": "shuffle"},
    "cartes au départ": {"maps_compasses": "start_with"},
    "cartes retirées": {"maps_compasses": "removed"},
    "sans cinématiques": {"skip_cutscenes": "safe", "maps_compasses": "start_with"},
    "quarts de cœur libres": {"shuffle_hearts": "freestanding"},
    "tous les cœurs": {"shuffle_hearts": "all", "maps_compasses": "shuffle"},
    "sans Zelda enfant": {"skip_child_zelda": True, "skip_cutscenes": "safe"},
    "récompenses mélangées": {"shuffle_rewards": "shuffled", "open_forest": "open", "open_door_of_time": True},
    "pont cœurs": {"bridge": "hearts", "bridge_count": 8, "shuffle_hearts": "freestanding"},
    "pont récompenses": {"bridge": "dungeons", "bridge_count": 5, "shuffle_rewards": "shuffled"},
    "Skulltulas extérieur": {"shuffle_skulltulas": "overworld", "shuffle_scrubs": True},
    "Skulltulas toutes": {"shuffle_skulltulas": "all", "shuffle_hearts": "freestanding", "open_forest": "open"},
}


class _FakeState:
    def __init__(self, **items):
        self.items = Counter(items)

    def has(self, item, n=1):
        return self.items[item] >= n


class RuleTests(unittest.TestCase):
    def setUp(self):
        self.c = RuleCompiler(
            ["Bow", "Magic_Meter", "Progressive_Hookshot", "Ocarina", "Zeldas_Lullaby"],
            ["Ev"],
            {"h": "Bow or Ev"},
            {"flag": True, "mode": "a", "n": 2},
            {"Bow": {"age": "adult", "needs": ["Magic_Meter"]}},
        )

    def test_basics(self):
        s = _FakeState(Bow=1, Progressive_Hookshot=2)
        self.assertTrue(self.c.compile("Bow and has(Progressive_Hookshot, 2)")(s, "child"))
        self.assertFalse(self.c.compile("has(Progressive_Hookshot, 3)")(s, "child"))
        self.assertTrue(self.c.compile("h")(s, "child"))
        self.assertTrue(self.c.compile("flag and setting_is(mode, 'a')")(s, "child"))
        self.assertTrue(self.c.compile("count(Bow, Progressive_Hookshot, Ocarina) >= setting_value(n)")(s, "child"))

    def test_can_use_checks_age_and_needs(self):
        rule = self.c.compile("can_use(Bow)")
        self.assertFalse(rule(_FakeState(Bow=1), "adult"))
        self.assertFalse(rule(_FakeState(Bow=1, Magic_Meter=1), "child"))
        self.assertTrue(rule(_FakeState(Bow=1, Magic_Meter=1), "adult"))

    def test_errors(self):
        for bad in ("Bow and", "Unknown_Thing", "__import__('os')", "Bow.x", "mode", "has(Bow)"):
            with self.assertRaises(RuleError, msg=bad):
                self.c.compile(bad)


class WorldTests(unittest.TestCase):
    def setUp(self):
        self.world = World(settings_mod.build())

    def test_levels_never_go_down(self):
        inv = Counter()
        self.world.collect(inv, "Item_Longshot")
        self.world.collect(inv, "Item_Hookshot")
        self.assertEqual(inv["Progressive_Hookshot"], 2)
        self.world.collect(inv, "Item_Gauntlet_Silver")
        self.world.collect(inv, "Item_Gauntlet_Goron")
        self.assertEqual(inv["Progressive_Strength"], 2)
        self.world.collect(inv, "TBox_Rupee_Red")
        self.assertNotIn("TBox_Rupee_Red", inv)

    def test_empty_inventory_cannot_win(self):
        self.assertFalse(is_beatable(self.world, {}))

    def test_vanilla_game_is_beatable(self):
        vanilla = {name: loc.vanilla for name, loc in self.world.locations.items()}
        state = State(self.world).sweep(vanilla)
        self.assertTrue(state.beaten())
        self.assertEqual(sorted(set(self.world.locations) - state.collected), [])

    def test_skip_child_zelda_gives_items_at_start(self):
        world = World(settings_mod.build({"skip_child_zelda": True}))
        self.assertEqual(world.start_items(), ["Item_ZeldaLetter", "Item_Melody_ZeldaLullaby"])
        state = State(world)
        state.expand()
        for name in ("HC Zeldas Letter", "Song from Impa"):
            self.assertTrue(state.can_reach(world.locations[name]), name)
        self.assertEqual(self.world.start_items(), [])
        door = World(settings_mod.build({"open_door_of_time": True}))
        self.assertEqual(door.start_items(), ["Item_ZeldaLetter", "Item_Melody_ZeldaLullaby"])
        self.assertIn("HyruleField_Child_Prefab_91f9", door.logic_patches())
        self.assertEqual(door.locations["Song from Ocarina of Time"].region,
                         self.world.locations["Song from Ocarina of Time"].region)
        self.assertEqual(door.start_flags()["#931730378"], "Step06")

    def test_closed_forest_child_stays_in_forest_at_start(self):
        """Sans épée ni Arbre Mojo, l'enfant ne doit pas pouvoir sortir de la forêt."""
        fixed_only = {l.name: l.vanilla for l in self.world.fixed_locations()}
        state = State(self.world)
        state.expand()
        self.assertNotIn("Hyrule Field", state.reached["child"])
        self.assertNotIn("Hyrule Field", State(self.world).sweep(fixed_only).reached["child"])


class GenerationTests(unittest.TestCase):
    def _check(self, overrides, seeds):
        world = World(settings_mod.build(overrides))
        pool = Counter(item for item, _ in world.pool())
        mode = world.settings["maps_compasses"]
        for seed in seeds:
            result = generate(world, seed)
            self.assertEqual(set(result.placements), set(world.locations), f"seed {seed}")
            self.assertTrue(is_beatable(world, result.placements), f"seed {seed}")
            if world.settings["accessibility"] == "all":
                self.assertEqual(result.unreachable, [], f"seed {seed}")
            # le contenu des coffres est une permutation du contenu d'origine
            placed = Counter(result.placements[l.name] for l in world.shuffled_locations())
            self.assertEqual(placed, pool, f"seed {seed}")
            # les lieux fixes gardent leur objet (sauf les récompenses de boss mélangées entre elles)
            rewards = {l.name for l in world.reward_locations()}
            for loc in world.fixed_locations():
                if world.settings["shuffle_rewards"] == "shuffled" and loc.name in rewards:
                    continue
                self.assertEqual(result.placements[loc.name], loc.vanilla)
            self.assertEqual(sorted(result.placements[n] for n in rewards),
                             sorted(world.locations[n].vanilla for n in rewards))
            # cœurs au sol : seulement des objets autorisés ; lieux incertains sans progression
            for loc in world.shuffled_locations():
                item = result.placements[loc.name]
                self.assertTrue(world.can_place(item, loc), f"{item} interdit à {loc.name}, seed {seed}")
            # cartes et boussoles : dans leur donjon, ou absentes
            for loc in world.locations.values():
                item = result.placements[loc.name]
                if item in ("Item_Dungeon_Map", "Item_Dungeon_Compass"):
                    self.assertIn(mode, ("vanilla", "shuffle"))
                    owners = [l for l in world.locations.values() if l.vanilla == item and l.dungeon == loc.dungeon]
                    self.assertTrue(owners, f"{item} hors de son donjon : {loc.name}")
            if mode in ("removed", "start_with"):
                self.assertNotIn("Item_Dungeon_Map", result.placements.values())
            flags = world.start_flags()
            self.assertEqual(any(k.startswith("DungeonInfo.") for k in flags), mode == "start_with")
            # porte du temps ouverte / scène de Rauru sautée : leurs scènes sont « déjà vues »
            door = {"HavePlayedEvent.Dm_TimeTemple_0010", "HavePlayedEvent.Dm_TimeTemple_0040"}
            self.assertEqual(any(k.startswith("HavePlayedEvent.") and k not in door for k in flags),
                             world.settings["skip_cutscenes"] == "safe")
            self.assertEqual(flags.get("Market_Child_TimeTempleDoor_Opened", False),
                             world.settings["open_door_of_time"])

    def test_presets(self):
        for name, overrides in PRESETS.items():
            with self.subTest(preset=name):
                self._check(overrides, range(1, N_SEEDS + 1))

    def test_deterministic(self):
        a = generate(World(settings_mod.build()), 42).placements
        b = generate(World(settings_mod.build()), 42).placements
        self.assertEqual(a, b)

    def test_spoiler_and_patch(self):
        world = World(settings_mod.build())
        result = generate(world, 7)
        spoiler = build_spoiler(world, result)
        self.assertIn("Triforce", [e["item"] for e in spoiler["playthrough"][-1]])
        changes = chest_changes(build_patch(world, result, spoiler["hash"]))
        for loc in world.shuffled_locations():
            item = result.placements[loc.name]
            if loc.pickup:
                continue
            for h in loc.hashes:
                if item == loc.vanilla:
                    self.assertNotIn(h, changes)
                else:
                    self.assertEqual(changes[h]["Drop__DropActor"], item)
                    self.assertEqual("GetEventName" in changes[h], loc.event == "drop")
                    self.assertEqual("Drop__CheckActor" in changes[h], loc.conditional)


class BridgeExpTests(unittest.TestCase):
    """Les expressions du pont (notation postfixe du jeu) valent bien « au moins N »."""

    @staticmethod
    def _eval(exps, name, flags, ints):
        stack = []
        for step in exps[name]:
            op = step[0]
            if op == "Bool":
                stack.append(step[1] in flags)
            elif op == "Exp":
                stack.append(BridgeExpTests._eval(exps, step[1], flags, ints))
            elif op == "IntEq":
                stack.append(ints.get(step[1], 0) == step[2])
            elif op == "NOT":
                stack.append(not stack.pop())
            else:
                b, a = stack.pop(), stack.pop()
                stack.append(a and b if op == "AND" else a or b)
        assert len(stack) == 1
        return stack[0]

    def test_counts(self):
        import itertools
        from ootrr.world import BRIDGE_EXP, MEDAL_FLAGS, STONE_FLAGS, bridge_exps
        for mode, flags in (("stones", STONE_FLAGS), ("medallions", MEDAL_FLAGS), ("dungeons", STONE_FLAGS + MEDAL_FLAGS)):
            for n in range(1, len(flags) + 1):
                exps = bridge_exps(mode, n)
                for owned in itertools.product([False, True], repeat=len(flags)):
                    have = {f for f, o in zip(flags, owned) if o}
                    for name in BRIDGE_EXP.values():
                        self.assertEqual(self._eval(exps, name, have, {}), len(have) >= n, (mode, n, have))
        exps = bridge_exps("hearts", 5)
        name = next(iter(BRIDGE_EXP.values()))
        self.assertFalse(self._eval(exps, name, set(), {"PlayerStatus.MaxLife": 19}))
        self.assertTrue(self._eval(exps, name, set(), {"PlayerStatus.MaxLife": 20}))
        self.assertTrue(self._eval(exps, name, set(), {"PlayerStatus.MaxLife": 23}))
        self.assertTrue(self._eval(bridge_exps("open", 0), name, set(), {}))


class BymlTests(unittest.TestCase):
    def test_roundtrip_types(self):
        tree = {"a": [1, U32(2), I64(-3), U64(2**64 - 1), 1.5, F64(2.25), True, None, "texte"],
                "b": {"z": "x", "y": [{"k": "texte"}]}, "h": HashDict({5: "v"}, hash_size=4)}
        back = read_byml(write_byml(tree))
        self.assertEqual(back, tree)
        self.assertIs(type(back["a"][3]), U64)
        self.assertIs(type(back["a"][5]), F64)


if __name__ == "__main__":
    unittest.main()
