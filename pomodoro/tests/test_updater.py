"""更新检查模块测试:版本解析/比较/Release 查询(网络路径用假 _fetch 替换)。"""

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import updater


class TestParseVersion(unittest.TestCase):
    def test_full(self):
        self.assertEqual(updater.parse_version("v1.2.3"), (1, 2, 3))

    def test_no_v(self):
        self.assertEqual(updater.parse_version("1.0"), (1, 0, 0))

    def test_prerelease_suffix_ignored(self):
        self.assertEqual(updater.parse_version("v1.2.3-beta.1"), (1, 2, 3))

    def test_two_digit_part(self):
        self.assertEqual(updater.parse_version("v10.20.30"), (10, 20, 30))

    def test_garbage(self):
        self.assertEqual(updater.parse_version("abc"), (0, 0, 0))
        self.assertEqual(updater.parse_version(""), (0, 0, 0))


class TestIsNewer(unittest.TestCase):
    def test_newer(self):
        self.assertTrue(updater.is_newer("1.1.0", "1.0.0"))

    def test_equal(self):
        self.assertFalse(updater.is_newer("1.0.0", "1.0.0"))

    def test_older(self):
        self.assertFalse(updater.is_newer("0.9.9", "1.0.0"))

    def test_same_major_minor(self):
        self.assertTrue(updater.is_newer("1.0.1", "1.0.0"))


class TestCheckUpdate(unittest.TestCase):
    FAKE_JSON = b'{"tag_name": "v1.1.0", "html_url": "https://github.com/a/b/releases/tag/v1.1.0"}'

    def test_returns_newer_version(self):
        with mock.patch.object(updater, "REPO", "u/r"):
            with mock.patch.object(updater, "_fetch",
                                   return_value=self.FAKE_JSON) as fetch:
                result = updater.check_update("1.0.0")
        self.assertEqual(result["version"], "1.1.0")
        self.assertIn("releases/tag", result["url"])
        self.assertIn("releases/latest", fetch.call_args[0][0])

    def test_up_to_date_returns_none(self):
        with mock.patch.object(updater, "REPO", "u/r"):
            with mock.patch.object(updater, "_fetch", return_value=self.FAKE_JSON):
                self.assertIsNone(updater.check_update("1.1.0"))

    def test_network_error_raises(self):
        with mock.patch.object(updater, "_fetch", side_effect=OSError("boom")):
            with self.assertRaises(OSError):
                updater.check_update("1.0.0")

    def test_no_release_tag_returns_none(self):
        with mock.patch.object(updater, "_fetch",
                               return_value=b'{"html_url": "x"}'):
            self.assertIsNone(updater.check_update("1.0.0"))


if __name__ == "__main__":
    unittest.main()
