"""Plandomizer (ootrr.plando): chosen placements are kept, the rest stays finishable, bad plandos are refused,
and a seed without plando is unchanged."""

import unittest

from ootrr import plando, settings, starting
from ootrr.fill import FillError, check, generate
from ootrr.world import World


def make_world(overrides: dict, spawn: dict | None = None, placements: dict | None = None) -> World:
    s = settings.build(starting.resolve(settings.build(overrides), 0))
    world = World(plando.apply_start(s, spawn))
    if placements is not None:
        world.plando = dict(placements)
    return world


class PlandoTest(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
