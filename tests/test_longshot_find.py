"""Desktop app: finding the Longshot version folder (tools.longshot_app.find_longshot / saved_longshot)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ootrr.tools.longshot_app import _version_key, find_longshot, saved_longshot


def _install(base: Path, *parts: str) -> Path:
    folder = base.joinpath(*parts)
    folder.mkdir(parents=True)
    (folder / "longshot.exe").write_bytes(b"")
    return folder


class FindLongshotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "Longshot"

    def tearDown(self):
        self.tmp.cleanup()

    def test_versions_compare_as_numbers(self):
        names = ["v3.0.0-rc.4", "v3.0.0", "v3.0.0-rc.10", "v2.10.0", "v2.9.1"]
        self.assertEqual(sorted(names, key=_version_key), ["v2.9.1", "v2.10.0", "v3.0.0-rc.4", "v3.0.0-rc.10", "v3.0.0"])

    def test_channels(self):
        _install(self.base, "rc", "v3.0.0-rc.7")
        self.assertEqual(find_longshot((self.base,)).name, "v3.0.0-rc.7")
        stable = _install(self.base, "stable", "v3.0.0")
        _install(self.base, "stable", "v2.9.0")
        self.assertEqual(find_longshot((self.base,)), stable)  # stable first, the newest one

    def test_old_layout_and_unknown_channel(self):
        old = _install(self.base, "v3.0.0-rc.4")
        self.assertEqual(find_longshot((self.base,)), old)
        old.joinpath("longshot.exe").unlink()
        beta = _install(self.base, "beta", "v3.1.0")
        self.assertEqual(find_longshot((self.base,)), beta)
        self.assertIsNone(find_longshot((Path(self.tmp.name) / "nothing",)))

    def test_saved_path_deleted_by_the_launcher(self):
        kept = _install(self.base, "rc", "v3.0.0-rc.7")
        self.assertEqual(saved_longshot(str(kept)), kept)
        gone = self.base / "v3.0.0-rc.3"
        found = saved_longshot(str(gone))
        self.assertTrue(found is None or (found / "longshot.exe").is_file())  # never the deleted folder


if __name__ == "__main__":
    unittest.main()
