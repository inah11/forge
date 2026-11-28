import re
import unittest
from pathlib import Path

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "check.yml"

# A live (not commented-out) command that runs the whole tests/ suite.
RUNS_SUITE = re.compile(r"^\s*(?:run:\s*)?python3? -m unittest discover\b.*\s-s\s+tests\b", re.M)


class CiWorkflowTest(unittest.TestCase):
    def test_check_workflow_runs_the_unit_tests(self):
        self.assertRegex(
            WORKFLOW.read_text(),
            RUNS_SUITE,
            f"{WORKFLOW.name} must run `python3 -m unittest discover -s tests`",
        )


if __name__ == "__main__":
    unittest.main()
