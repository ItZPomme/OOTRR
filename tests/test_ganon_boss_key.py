"""ganon_boss_key: Ganon's Castle boss key given by a condition (stones, medallions, dungeons, hearts)."""

import itertools
import unittest

from ootrr import keys as keys_mod
from ootrr import settings, settings_ui
from ootrr.fill import check, generate
from ootrr.formats.gamedata import encode_bool_exp
from ootrr.patch import build_patch
from ootrr.search import State
from ootrr.world import (GANON_KEY_EXP, GANON_KEY_MODULE, JUNK_REPLACEMENT, MAX_LIFE, MEDAL_FLAGS, STONE_FLAGS, World,
                         ganon_key_exps)

KEY = keys_mod.item_name(keys_mod.BOSS, "InsideGanonCastle")
FLAG = "DungeonInfo.InsideGanonCastle.IsGetBossKey"
CHEST = "Ganons Castle Boss Key Chest"
MEDALLIONS = {"ganon_boss_key": "medallions", "ganon_boss_key_count": 6}


def evaluate(exps, name, flags, ints):
    stack = []
    for op, *args in exps[name]:
        if op == "Bool":
            stack.append(args[0] in flags)
        elif op == "IntEq":
            stack.append(ints.get(args[0]) == args[1])
        elif op == "Exp":
            stack.append(evaluate(exps, args[0], flags, ints))
        elif op == "NOT":
            stack.append(not stack.pop())
        else:
            b, a = stack.pop(), stack.pop()
            stack.append(a and b if op == "AND" else a or b)
    value, = stack
    return value


class ConditionTest(unittest.TestCase):
    def test_rewards(self):
        for mode, flags in (("stones", STONE_FLAGS), ("medallions", MEDAL_FLAGS),
                            ("dungeons", STONE_FLAGS + MEDAL_FLAGS)):
            for n in range(0, len(flags) + 1):
                exps = ganon_key_exps(mode, n)
                for owned in itertools.product([False, True], repeat=len(flags)):
                    have = {f for f, o in zip(flags, owned) if o}
                    self.assertEqual(evaluate(exps, GANON_KEY_EXP, have, {}), len(have) >= n, (mode, n, have))

    def test_hearts(self):
        for n in range(1, 21):
            exps = ganon_key_exps("hearts", n)
            for hearts in range(3, 21):
                self.assertEqual(evaluate(exps, GANON_KEY_EXP, set(), {MAX_LIFE: 4 * hearts}), hearts >= n)
            self.assertLessEqual(max(len(encode_bool_exp(prog)) for prog in exps.values()), 26)  # the game's longest expression

    def test_names_differ_from_the_bridge(self):
        world = World(settings.build({**MEDALLIONS, "bridge": "medallions", "bridge_count": 2}))
        exps = world.bool_exps()
        have = set(MEDAL_FLAGS[:2])
        self.assertTrue(evaluate(exps, "OoTRR_Bridge_Condition_Exp_A00", have, {}))
        self.assertFalse(evaluate(exps, GANON_KEY_EXP, have, {}))


class GanonBossKeyTest(unittest.TestCase):
    def test_default_changes_nothing(self):
        world = World(settings.build({}))
        self.assertNotIn(CHEST, world.locations)
        self.assertNotIn(GANON_KEY_EXP, world.bool_exps())
        self.assertNotIn("ganon_boss_key", world.ainb_edits())

    def test_count_limits(self):
        for mode, limit in settings.COUNT_LIMITS.items():
            settings.build({"ganon_boss_key": mode, "ganon_boss_key_count": limit})
            with self.assertRaises(settings.SettingsError):
                settings.build({"ganon_boss_key": mode, "ganon_boss_key_count": limit + 1})
            self.assertEqual(settings_ui.int_range("ganon_boss_key_count", {"ganon_boss_key": mode}), (1, limit))
        self.assertFalse(settings_ui.enabled("ganon_boss_key_count", settings.defaults()))

    def test_chest_and_key(self):
        # whatever boss_keys says: the chest is a location, the key is not an item and is not owned from the start
        for boss in settings.KEY_MODES:
            with self.subTest(boss_keys=boss):
                world = World(settings.build({**MEDALLIONS, "boss_keys": boss}))
                self.assertIn(CHEST, world.locations)
                pool = [item for item, _ in world.pool()]
                self.assertNotIn(KEY, pool)
                self.assertNotIn(FLAG, world.start_flags())
                others = [i for i in pool if (keys_mod.parse_item(i) or ("",))[0] == keys_mod.BOSS]
                self.assertEqual(len(others), 5 if boss in keys_mod.SHUFFLED else 0)
                triforce = next(e for e in world.events if e.name == "Triforce")
                self.assertIn("ganon_boss_key_condition", triforce.rule_src)
                self.assertNotIn("Boss_Key", triforce.rule_src)

    def test_follows_boss_keys(self):
        for boss in settings.KEY_MODES:
            world = World(settings.build({"boss_keys": boss}))
            self.assertEqual(CHEST in world.locations, boss != "vanilla")
            self.assertEqual(KEY in [i for i, _ in world.pool()], boss in keys_mod.SHUFFLED)
            self.assertEqual(world.start_flags().get(FLAG, False), boss == "removed")

    def test_own_modes(self):
        """vanilla, removed and random: whatever boss_keys says, the other five keys follow boss_keys."""
        for boss in settings.KEY_MODES:
            for mode in ("vanilla", "removed", "random"):
                with self.subTest(boss_keys=boss, ganon=mode):
                    world = World(settings.build({"boss_keys": boss, "ganon_boss_key": mode}))
                    pool = [item for item, _ in world.pool()]
                    self.assertEqual(CHEST in world.locations, mode != "vanilla")
                    self.assertEqual(KEY in pool, mode == "random")
                    flags = world.start_flags()
                    self.assertEqual(flags.get(FLAG, False), mode == "removed")
                    self.assertEqual(flags.get("DungeonInfo.FireTemple.IsGetBossKey", False), boss == "removed")
                    others = [i for i in pool if (keys_mod.parse_item(i) or ("",))[0] == keys_mod.BOSS and i != KEY]
                    self.assertEqual(len(others), 5 if boss in keys_mod.SHUFFLED else 0)
                    self.assertNotIn(GANON_KEY_EXP, world.bool_exps())
                    self.assertNotIn("ganon_boss_key", world.ainb_edits())
                    rule = next(e.rule_src for e in world.events if e.name == "Triforce")
                    self.assertEqual("Vanilla_Boss_Key_Ganons_Castle" in rule, mode == "vanilla")
                    self.assertEqual(rule.endswith("Boss_Key_Ganons_Castle"), mode != "removed")
                    volvagia = world.locations["Volvagia"].rule_src
                    self.assertEqual("Boss_Key_Fire_Temple" in volvagia, boss != "removed")
                    self.assertEqual("Vanilla_Boss_Key_Fire_Temple" in volvagia, boss == "vanilla")

    def test_random_goes_anywhere(self):
        # boss_keys = own_dungeon keeps the others home; Ganon's key may leave the castle
        world = World(settings.build({"boss_keys": "own_dungeon", "ganon_boss_key": "random"}))
        chest = world.locations["HF Grotto Chest 1"]
        self.assertTrue(world.can_place(KEY, chest))
        self.assertFalse(world.can_place(keys_mod.item_name(keys_mod.BOSS, "FireTemple"), chest))
        home = {generate(world, seed).placements.get(CHEST) for seed in range(1, 4)}
        self.assertNotEqual(home, {KEY})

    def test_logic(self):
        rewards = ("Item_Medal_Forest", "Item_Medal_Shadow")
        for boss in ("vanilla", "any_dungeon", "removed"):
            world = World(settings.build({**MEDALLIONS, "boss_keys": boss, "bridge": "open"}))
            rule = next(e.rule for e in world.events if e.name == "Triforce")
            self.assertTrue(self.full_state(world).beaten())
            for reward in rewards:
                state = self.full_state(world, reward)
                self.assertIn("Ganons Castle Tower", state.reached["adult"])
                self.assertFalse(rule(state, "adult"))

    @staticmethod
    def full_state(world: World, *missing: str) -> State:
        """Everything except `missing` (shuffled rewards: the bosses give nothing here)."""
        state = State(world, [name for name in world.items if name not in missing] * 9)
        state.can_return = True
        return state.sweep({})

    def test_hearts_logic(self):
        world = World(settings.build({"ganon_boss_key": "hearts", "ganon_boss_key_count": 10, "bridge": "open"}))
        rule = next(e.rule for e in world.events if e.name == "Triforce")
        self.assertTrue(rule(self.full_state(world), "adult"))
        self.assertFalse(rule(self.full_state(world, "Obj_Heart_Piece", "Obj_Heart_Container"), "adult"))

    def test_seeds(self):
        presets = [{"ganon_boss_key": "stones", "ganon_boss_key_count": 3, "shuffle_rewards": "shuffled"},
                   {**MEDALLIONS, "boss_keys": "any_dungeon", "small_keys": "random", "skip_trials": True},
                   {"ganon_boss_key": "dungeons", "ganon_boss_key_count": 9, "accessibility": "beatable"},
                   {"ganon_boss_key": "hearts", "ganon_boss_key_count": 12, "boss_keys": "removed"},
                   {"ganon_boss_key": "random"}, {"ganon_boss_key": "removed", "boss_keys": "own_dungeon"},
                   {"ganon_boss_key": "vanilla", "boss_keys": "random", "small_keys": "own_dungeon"}]
        for values in presets:
            for seed in range(1, 4):
                with self.subTest(values=values, seed=seed):
                    world = World(settings.build(values))
                    result = generate(world, seed)
                    self.assertTrue(check(world, result.placements, result.starting_items)[0])
                    self.assertEqual(list(result.placements.values()).count(KEY), values["ganon_boss_key"] == "random")

    def test_patch(self):
        world = World(settings.build(MEDALLIONS))
        patch = build_patch(world, generate(world, 1), "TEST")
        self.assertEqual(patch["ainb_edits"]["ganon_boss_key"],
                         {"module": GANON_KEY_MODULE, "bool_exp": GANON_KEY_EXP, "flag": FLAG})
        self.assertIn(GANON_KEY_EXP, patch["bool_exps"])
        chest = next(c for c in patch["chests"] if c["location"] == CHEST)
        self.assertNotIn(chest["item"], (KEY, "Item_Dungeon_BossKey"))
        self.assertIn(JUNK_REPLACEMENT, [item for item, _ in world.pool()])


if __name__ == "__main__":
    unittest.main()
