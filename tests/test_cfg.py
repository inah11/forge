import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import mock

FORGE = Path(__file__).resolve().parent.parent / "bin" / "forge"


def load_forge():
    loader = SourceFileLoader("forge_cli", str(FORGE))
    mod = module_from_spec(spec_from_loader("forge_cli", loader))
    loader.exec_module(mod)
    return mod


class CfgRepoTest(unittest.TestCase):
    def setUp(self):
        self.forge = load_forge()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.forge.CFG_PATH = self.tmp / "forge.json"
        home = mock.patch.dict(os.environ, {"HOME": str(self.tmp)})
        home.start()
        self.addCleanup(home.stop)
        for d in ("srv", "app", "explicit"):
            (self.tmp / d).mkdir()
        self.repos = {"server": {"path": "~/srv", "test_cmd": "true"}, "android": "~/app"}

    def write(self, conf):
        self.forge.CFG_PATH.write_text(json.dumps(conf))

    def test_repos_only_defaults_repo_to_first_mapped(self):
        self.write({"repos": self.repos})
        self.assertEqual(self.forge.cfg()["repo"], str(self.tmp / "srv"))

    def test_valid_repo_is_kept_even_with_repos(self):
        explicit = str(self.tmp / "explicit")
        self.write({"repo": explicit, "repos": self.repos})
        self.assertEqual(self.forge.cfg()["repo"], explicit)

    def test_missing_repo_dir_falls_back_to_first_mapped(self):
        self.write({"repo": str(self.tmp / "nope"), "repos": self.repos})
        self.assertEqual(self.forge.cfg()["repo"], str(self.tmp / "srv"))

    def test_neither_repo_nor_repos_dies_with_message(self):
        self.write({})
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit):
            self.forge.cfg()
        self.assertIn("is not a directory", err.getvalue())


if __name__ == "__main__":
    unittest.main()
