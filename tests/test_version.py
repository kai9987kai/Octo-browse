import unittest

from main import OCTO_BROWSER_VERSION
from octobrowse.version import __version__


class VersionTests(unittest.TestCase):
    def test_main_uses_package_release_version(self) -> None:
        self.assertEqual(__version__, "3.3")
        self.assertEqual(OCTO_BROWSER_VERSION, __version__)


if __name__ == "__main__":
    unittest.main()
