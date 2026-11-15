"""Update check (ootrr.updates): version parsing and comparison, no network."""

import unittest
from unittest import mock

from ootrr import updates


class UpdatesTest(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(updates.parse_version("v0.3.0"), (0, 3, 0))
        self.assertEqual(updates.parse_version("0.10"), (0, 10))
        self.assertIsNone(updates.parse_version("v0.3.0-rc1"))
        self.assertIsNone(updates.parse_version("latest"))

    def test_is_newer(self):
        self.assertTrue(updates.is_newer("v0.4.0", "0.3.0"))
        self.assertTrue(updates.is_newer("v0.10.0", "0.9.9"))
        self.assertTrue(updates.is_newer("v0.3.1", "0.3"))
        self.assertFalse(updates.is_newer("v0.3.0", "0.3.0"))
        self.assertFalse(updates.is_newer("v0.3", "0.3.0"))
        self.assertFalse(updates.is_newer("v0.2.0", "0.3.0"))
        self.assertFalse(updates.is_newer("nightly", "0.3.0"))

    def test_check_offline(self):
        with mock.patch("urllib.request.urlopen", side_effect=OSError("offline")):
            self.assertIsNone(updates.check())

    def test_check_newer(self):
        class Resp:
            def __init__(self, body):
                self.body = body

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        body = b'{"tag_name": "v99.0.0", "name": "OoTRR v99", "html_url": "https://evil.example/x"}'
        with mock.patch("urllib.request.urlopen", return_value=Resp(body)):
            rel = updates.check()
        self.assertEqual(rel["tag"], "v99.0.0")
        self.assertEqual(rel["url"], updates.RELEASES_PAGE)  # only pages of the repository are opened
        with mock.patch("urllib.request.urlopen", return_value=Resp(b'{"tag_name": "v0.0.1"}')):
            self.assertIsNone(updates.check())


if __name__ == "__main__":
    unittest.main()
