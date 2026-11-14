"""The app's settings table (ootrr.settings_ui) stays in step with the settings and the in-game menu."""

import unittest

from ootrr import ingame_menu, settings, settings_ui


class SettingsTableTest(unittest.TestCase):
    def test_every_setting_has_one_place(self):
        shown = settings_ui.SHOWN
        self.assertEqual(len(shown), len(set(shown)), "a setting is shown twice")
        groups = [set(shown), set(settings_ui.NATIVE_ONLY), set(settings_ui.HIDDEN)]
        for i, a in enumerate(groups):
            for b in groups[i + 1:]:
                self.assertFalse(a & b, f"setting in two groups: {a & b}")
        self.assertEqual(set().union(*groups), set(settings.SETTINGS))

    def test_menu_settings_are_in_the_app(self):
        # every row of the native menu is offered by the app, or explicitly native-only / hidden
        menu = {r[0] for r in ingame_menu.SETTING_ROWS}
        missing = menu - set(settings_ui.SHOWN) - set(settings_ui.NATIVE_ONLY) - set(settings_ui.HIDDEN)
        self.assertFalse(missing, f"menu settings missing from the app: {missing}")

    def test_texts_and_labels(self):
        for title, names in settings_ui.PAGES:
            self.assertLessEqual(len(names), settings_ui.MAX_ROWS, title)
            for name in names:
                self.assertTrue(settings_ui.title(name))
                self.assertTrue(settings_ui.caption(name))
                if settings.SETTINGS[name][1] is not int:
                    for value in settings_ui.choices(name):
                        self.assertTrue(settings_ui.value_label(name, value))

    def test_native_only_refused_for_pc_mod(self):
        from ootrr.__main__ import main
        self.assertEqual(main(["--set", "shuffle_shops=2", "--check"]), 2)


if __name__ == "__main__":
    unittest.main()
