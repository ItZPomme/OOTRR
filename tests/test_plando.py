"""Plandomizer (ootrr.plando): chosen placements are kept, the rest stays finishable, bad plandos are refused,
and a seed without plando is unchanged."""

from collections import Counter
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ootrr import __main__ as cli, plando, settings, starting
from ootrr.fill import FillError, _pool_with_start_items, check, generate
from ootrr.patch import build_patch
from ootrr.spoiler import seed_hash
from ootrr.world import World


def make_world(overrides: dict, spawn: dict | None = None, placements: dict | None = None) -> World:
    s = settings.build(starting.resolve(settings.build(overrides), 0))
    world = World(plando.apply_start(s, spawn))
    if placements is not None:
        world.plando = dict(placements)
    return world


class PlandoTest(unittest.TestCase):
    def test_seed_install_preserves_live_native_module(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            load_dir = root / "load"
            source = load_dir / "OoTRR" / "exefs" / "subsdk9"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"native module")
            mod_dir = root / "new-mod" / "OoTRR-essai"
            (mod_dir / "romfs").mkdir(parents=True)

            self.assertTrue(cli._preserve_native_module(mod_dir, load_dir, "OoTRR-essai"))
            self.assertEqual((mod_dir / "exefs" / "subsdk9").read_bytes(), b"native module")

    def test_placements_kept_and_seed_finishable(self):
        placements = {"HF Grotto Chest 1": "Item_Hookshot", "HF Adult Chest 2": "Item_Hookshot",
                      "Song from Saria": "Item_Melody_FireBolero", "Queen Gohma": "Item_Medal_Light"}
        world = make_world({"starting_age": "adult", "shuffle_songs": "shuffle", "shuffle_rewards": "shuffled"},
                           {"age": "adult", "region": "Hyrule Field"}, placements)
        self.assertEqual(plando.validate(world, placements), [])
        for seed in range(10):
            result = generate(world, seed)
            for loc, item in placements.items():
                self.assertEqual(result.placements[loc], item)
            beaten, unreachable = check(world, result.placements)
            self.assertTrue(beaten)
            self.assertEqual(unreachable, [])
            # every shuffled location is filled exactly once, the extra Hookshot replaced a rupee
            self.assertEqual(set(result.placements), set(world.locations))

    def test_start_point(self):
        world = make_world({"starting_age": "adult"}, {"age": "adult", "region": "Hyrule Field"})
        self.assertEqual(starting.spawn(world.settings)["banc"], "HyruleField_Adult")
        with self.assertRaises(plando.PlandoError):
            make_world({}, {"age": "adult", "region": "Hyrule Field"})  # child start, adult start point

    def test_bad_plandos(self):
        world = make_world({})
        errors = plando.validate(world, {"Song from Saria": "Item_Hookshot", "Nowhere": "Item_Hookshot",
                                         "HF Grotto Chest 1": "Item_NotAnItem"})
        self.assertEqual(len(errors), 3)
        songs = make_world({"shuffle_songs": "shuffle"})
        self.assertEqual(len(plando.validate(songs, {"Song from Saria": "Item_Hookshot"})), 1)

    def test_impossible_plando_fails(self):
        # the only Megaton Hammer locked in a chest that needs it: that chest can never be opened
        world = make_world({}, None, {"GV Heart Piece Chest": "Item_Hammer"})
        self.assertIn("Megaton_Hammer", world.locations["GV Heart Piece Chest"].rule_src)
        self.assertEqual(plando.validate(world, world.plando), [])
        with self.assertRaises(FillError):
            generate(world, 1, max_attempts=3)

    def test_no_plando_same_seed(self):
        a = generate(make_world({}), 7).placements
        b = generate(make_world({}, None, {}), 7).placements
        self.assertEqual(a, b)

    def test_starting_items_are_saved_and_removed_from_pool(self):
        world = make_world({})
        before = Counter(item for item, _ in world.pool())
        after = Counter(item for item, _ in _pool_with_start_items(world, ["Item_Hookshot"]))
        self.assertEqual(sum(before.values()), sum(after.values()))
        self.assertEqual(after["Item_Hookshot"], before["Item_Hookshot"] - 1)
        self.assertEqual(after["TBox_Rupee_Green"], before["TBox_Rupee_Green"] + 1)

        result = generate(world, 7, starting_items=["Item_Hookshot"])
        self.assertEqual(result.starting_items, ["Item_Hookshot"])
        self.assertTrue(check(world, result.placements, result.starting_items)[0])
        self.assertIn("Item_Hookshot", build_patch(world, result, "TEST")["start_items"])
        self.assertNotEqual(seed_hash(world, result), seed_hash(world, replace(result, starting_items=[])))

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plando.json"
            plando.save(path, None, {}, None, {}, result.starting_items)
            self.assertEqual(plando.load(path)["start_items"], ["Item_Hookshot"])

    def test_unshuffled_starting_item_is_added_extra(self):
        world = make_world({})
        before = world.pool()
        after = _pool_with_start_items(world, ["Item_Melody_ZeldaLullaby"])
        self.assertEqual(after, before)

    def test_items_without_pouch_support_cannot_start(self):
        world = make_world({})
        unsupported = [
            "Goron_Tunic", "Zora_Tunic", "Item_Dungeon_Map", "Item_Dungeon_Compass", "Tbox_MagicJar_Large",
            "OoTRR_SmallKey_ForestTemple",
        ]
        self.assertEqual(len(plando.validate_start_items(world, unsupported)), len(unsupported))
        self.assertTrue(set(unsupported).isdisjoint(plando.startable_items(world)))

    def test_tunics_use_real_pouch_actor_names(self):
        world = make_world({})
        for actor, logic in (("Armor_Adult_Goron", "Goron_Tunic"),
                             ("Armor_Adult_Zora", "Zora_Tunic")):
            with self.subTest(actor=actor):
                self.assertEqual(world.items[actor].logic, logic)
                self.assertIn(actor, plando.startable_items(world))
                self.assertEqual(plando.validate_start_items(world, [actor]), [])
                result = generate(world, 7, starting_items=[actor])
                self.assertEqual(result.starting_items, [actor])
                self.assertTrue(check(world, result.placements, result.starting_items)[0])
                self.assertIn(actor, build_patch(world, result, "TEST")["start_items"])

    def test_many_start_items_retry_shuffled_scrub_fill(self):
        settings = {
            "open_forest": "open", "open_door_of_time": True, "shuffle_scrubs": True,
            "scrub_prices": "affordable", "skip_cutscenes": "safe", "shuffle_rewards": "shuffled",
            "skip_child_zelda": True, "start_with_consumables": True, "shuffle_songs": "shuffle",
            "cucco_count": 1, "big_poe_count": 1, "complete_mask_quest": True, "fast_bunny_hood": True,
            "blue_fire_arrows": True, "gerudo_card": "vanilla", "gerudo_fortress": "fast",
        }
        start_items = [
            "Item_Hookshot", "Item_Boomerang", "Item_Bottle_Letter", "Item_Bottle", "Item_DinFire",
            "Item_BombBag_Large", "Item_Gauntlet_Goron", "Item_Hammer", "Item_HeavyBoot", "Item_Longshot",
            "Item_HoverBoot", "Item_Melody_EponaSong", "Item_Melody_FireBolero", "Item_Melody_ForestMinuet",
            "Item_Melody_LightPrelude", "Item_Melody_SariaSong", "Item_Melody_ShadowNocturne",
            "Item_Melody_SpiritRequiem", "Item_Melody_StormSong", "Item_Melody_SunSong",
            "Item_Melody_TimeSong", "Item_Melody_WaterSerenade", "Item_Melody_ZeldaLullaby",
            "Item_Ocarina_Fairy", "Item_Scale_Silver", "Item_Range_SlingShot", "Item_Range_Bow",
            "Item_Sword_Biggoron", "Item_Sword_Kokiri", "Item_Shield_Mirror", "Item_BulletBag_Medium",
            "Item_Quiver_Medium", "Item_Token_Gerudo", "Armor_Adult_Goron", "Armor_Adult_Zora",
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            plan_path = root / "plando.json"
            plando.save(plan_path, None, settings, None, {}, start_items)
            for seed in (518856711, 855077799):
                result = cli.main([
                    "--plando", str(plan_path), "--seed", str(seed), "--out", str(root / "output"),
                    "--no-spoiler",
                ])
                self.assertEqual(result, 0, f"generation failed for seed {seed}")


if __name__ == "__main__":
    unittest.main()
