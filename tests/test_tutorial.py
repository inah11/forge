import contextlib
import io
import json
import shutil
import subprocess
import tempfile
import unittest
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from unittest import mock

FORGE = Path(__file__).resolve().parent.parent / "bin" / "forge"
PR7 = "https://github.com/you/app/pull/9"
PR8 = "https://github.com/you/app/pull/10"


def load_forge():
    loader = SourceFileLoader("forge_cli", str(FORGE))
    mod = module_from_spec(spec_from_loader("forge_cli", loader))
    loader.exec_module(mod)
    return mod


def done(cmd, out="", code=0):
    return subprocess.CompletedProcess(cmd, code, stdout=out, stderr="")


class TutorialTest(unittest.TestCase):
    def setUp(self):
        self.forge = f = load_forge()
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.repo = self.tmp / "app"
        self.repo.mkdir()
        f.ROOT = self.tmp
        f.LOGS = self.tmp / "logs"
        (self.tmp / "tickets").mkdir()
        self.c = {"repo": str(self.repo), "base_branch": "main", "test_cmd": "true", "models": {}}
        self.tasks = [
            ("7--api", {"jira": "7", "goal": "add the api"}, {"state": "approved", "pr_url": PR7, "merged": True}),
            ("8--other", {"jira": "8", "goal": "another ticket"}, {"state": "approved", "pr_url": PR8, "merged": True}),
        ]
        self.sh_calls = []
        self.model = mock.Mock(return_value=done(["claude"], json.dumps({"result": "# How it works\nLike a librarian."})))
        self.publish = mock.Mock(return_value="https://github.com/you/app/pull/99")
        patches = [
            mock.patch.object(f, "all_tasks", lambda: self.tasks),
            mock.patch.object(f, "read_plan", lambda c, key: {"title": f"PLAN-MARKER {key}", "subtasks": [{"id": "api"}]}),
            mock.patch.object(f, "render_audit", lambda c, key: f"AUDIT-MARKER {key}"),
            mock.patch.object(f, "sh", self.fake_sh),
            mock.patch.object(f, "publish_files", self.publish),
            mock.patch.object(f, "agent_env", lambda c: {"CLAUDE_CONFIG_DIR": "/forge/account"}),
            mock.patch.object(f, "ledger_record", mock.Mock()),
            mock.patch.object(f.subprocess, "run", self.model),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def fake_sh(self, cmd, cwd=None, check=True, capture=True, env=None):
        line = cmd if isinstance(cmd, str) else " ".join(cmd)
        self.sh_calls.append(line)
        if "gh pr diff" in line:
            return done(cmd, f"DIFF-MARKER for {line.split()[-1]}")
        if "rev-parse --abbrev-ref HEAD" in line:
            return done(cmd, "main\n")
        return done(cmd)

    def published_files(self):
        self.publish.assert_called_once()
        return sorted(self.publish.call_args.args[3])

    def model_call(self):
        self.model.assert_called_once()
        return self.model.call_args

    def quiet(self, fn, *args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(*args)

    # a
    def test_audit_publishes_tutorial_when_model_succeeds(self):
        self.quiet(self.forge.write_audit, self.c, "7", str(self.repo))
        self.assertIn("docs/forge/7/tutorial.md", self.published_files())
        self.assertIn("Like a librarian.", (self.repo / "docs/forge/7/tutorial.md").read_text())

    # b
    def test_prompt_has_audit_plan_and_diff_and_model_is_configurable(self):
        self.quiet(self.forge.write_audit, self.c, "7", str(self.repo))
        call = self.model_call()
        body = call.kwargs["input"]
        for marker in ("AUDIT-MARKER 7", "PLAN-MARKER 7", f"DIFF-MARKER for {PR7}"):
            self.assertIn(marker, body)
        self.assertNotIn(PR8, body)
        cmd = call.args[0]
        self.assertEqual(cmd[cmd.index("--model") + 1], "sonnet")
        self.assertEqual(call.kwargs["env"]["CLAUDE_CONFIG_DIR"], "/forge/account")

        self.model.reset_mock(); self.publish.reset_mock()
        shutil.rmtree(self.repo / "docs")
        self.c["models"] = {"tutorial": "opus"}
        self.quiet(self.forge.write_audit, self.c, "7", str(self.repo))
        cmd = self.model_call().args[0]
        self.assertEqual(cmd[cmd.index("--model") + 1], "opus")

    # c
    def test_model_failure_still_publishes_audit_without_tutorial_and_logs(self):
        failures = {
            "timeout": subprocess.TimeoutExpired(["claude"], 300),
            "non-zero exit": done(["claude"], "", 1),
            "empty answer": done(["claude"], json.dumps({"result": "  "})),
        }
        for name, outcome in failures.items():
            with self.subTest(name):
                self.model.reset_mock(); self.publish.reset_mock()
                self.model.side_effect = outcome if isinstance(outcome, Exception) else None
                self.model.return_value = outcome
                shutil.rmtree(self.repo / "docs", ignore_errors=True)
                shutil.rmtree(self.forge.LOGS, ignore_errors=True)
                self.quiet(self.forge.write_audit, self.c, "7", str(self.repo))
                files = self.published_files()
                self.assertIn("docs/forge/7/audit.md", files)
                self.assertNotIn("docs/forge/7/tutorial.md", files)
                logs = list(self.forge.LOGS.glob("tutorial-7-*.log"))
                self.assertEqual(len(logs), 1, "the failure must be logged")
                self.assertIn("tutorial", logs[0].read_text().lower())

    # d
    def test_tutorial_false_skips_model_and_audit_is_unchanged(self):
        self.c["tutorial"] = False
        self.quiet(self.forge.write_audit, self.c, "7", str(self.repo))
        self.model.assert_not_called()
        self.assertEqual(self.published_files(), ["docs/forge/7/audit.md", "docs/forge/7/plan.json"])

    # e
    def test_forge_tutorial_regenerates_and_publishes_only_that_ticket(self):
        out = self.repo / "docs/forge/7"
        out.mkdir(parents=True)
        (out / "audit.md").write_text("COMMITTED AUDIT 7")
        (out / "tutorial.md").write_text("OLD TUTORIAL")
        self.c["tutorial"] = False   # the switches only stop the automatic run; the command always runs
        self.c["audit"] = False
        with mock.patch.object(self.forge, "cfg", lambda: self.c):
            self.quiet(self.forge.cmd_tutorial, ["7"])
        self.assertIn("COMMITTED AUDIT 7", self.model_call().kwargs["input"])
        self.assertIn("Like a librarian.", (out / "tutorial.md").read_text())
        self.assertEqual((out / "audit.md").read_text(), "COMMITTED AUDIT 7")
        self.assertFalse((self.repo / "docs/forge/8").exists())
        self.assertFalse(any(PR8 in line for line in self.sh_calls))
        self.assertEqual(self.published_files(), ["docs/forge/7/tutorial.md"])
        self.assertEqual(self.publish.call_args.args[2], "forge/7-tutorial")

    # f
    def test_audit_false_means_no_tutorial_at_ticket_close(self):
        self.c["audit"] = False
        with mock.patch.object(self.forge, "run_gate", lambda cmd, cwd: ("green", "")):
            self.quiet(self.forge.ticket_close, self.c, "7")
        self.model.assert_not_called()
        self.publish.assert_not_called()
        self.assertFalse((self.repo / "docs").exists())
        self.assertTrue((self.tmp / "tickets" / "7.closed").exists())


if __name__ == "__main__":
    unittest.main()
