from __future__ import annotations

import unittest
from pathlib import Path


class LauncherExperienceTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.repo = (
            Path(__file__)
            .resolve()
            .parents[1]
        )

    def test_shell_launcher_waits_for_app_health(self):
        text = (
            self.repo
            / "scripts"
            / "start_operations_app.sh"
        ).read_text()

        self.assertIn(
            "wait_for_health",
            text,
        )

        self.assertIn(
            'APP_HEALTH="${APP_URL}/health"',
            text,
        )

        ready_position = text.index(
            "Operations Meta-Agent is ready."
        )

        health_position = text.index(
            'wait_for_health "$APP_HEALTH"'
        )

        self.assertGreater(
            ready_position,
            health_position,
        )

    def test_shell_launcher_opens_browser(self):
        text = (
            self.repo
            / "scripts"
            / "start_operations_app.sh"
        ).read_text()

        self.assertIn(
            "open_browser",
            text,
        )

        self.assertIn(
            "cmd.exe",
            text,
        )

        self.assertIn(
            "xdg-open",
            text,
        )

        self.assertIn(
            "command -v open",
            text,
        )

    def test_launcher_remains_local_only(self):
        text = (
            self.repo
            / "scripts"
            / "start_operations_app.sh"
        ).read_text()

        self.assertIn(
            "127.0.0.1",
            text,
        )

        self.assertNotIn(
            "0.0.0.0",
            text,
        )

    def test_windows_launcher_has_no_machine_specific_path(self):
        files = [
            (
                self.repo
                / "scripts"
                / "launch_operations_app_windows.ps1"
            ),
            (
                self.repo
                / "scripts"
                / "Launch_Operations_Meta_Agent.vbs"
            ),
        ]

        combined = "\n".join(
            path.read_text()
            for path in files
        )

        forbidden = [
            "/home/seckinozbek",
            "/mnt/c/Users/secki",
            r"C:\Users\secki",
            "research-cloud-platform",
        ]

        for value in forbidden:
            self.assertNotIn(
                value,
                combined,
            )

    def test_windows_launcher_discovers_repo_relative_to_itself(self):
        text = (
            self.repo
            / "scripts"
            / "launch_operations_app_windows.ps1"
        ).read_text()

        self.assertIn(
            "$MyInvocation.MyCommand.Path",
            text,
        )

        self.assertIn(
            "wslpath",
            text,
        )

    def test_hidden_launcher_uses_hidden_window(self):
        text = (
            self.repo
            / "scripts"
            / "Launch_Operations_Meta_Agent.vbs"
        ).read_text()

        self.assertIn(
            "shell.Run command, 0, False",
            text,
        )


if __name__ == "__main__":
    unittest.main()
