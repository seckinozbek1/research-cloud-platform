from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.runtime_context import (
    get_runtime_context,
)


class PortabilityTest(unittest.TestCase):

    def test_project_root_is_discovered_without_username(self):
        with patch.dict(
            os.environ,
            {},
            clear=False,
        ):
            context = get_runtime_context()

        self.assertTrue(
            context.project_root.is_absolute()
        )

        expected_project_root = (
            Path(__file__).resolve().parents[1]
        )

        self.assertEqual(
            context.project_root,
            expected_project_root,
        )

    def test_runtime_root_can_be_overridden(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_RUNTIME":
                        tmp,
                },
                clear=False,
            ):
                context = (
                    get_runtime_context()
                )

            self.assertEqual(
                context.runtime_root,
                Path(tmp).resolve(),
            )

    def test_managed_root_follows_runtime_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_RUNTIME":
                        tmp,
                },
                clear=False,
            ):
                context = (
                    get_runtime_context()
                )

            self.assertEqual(
                context.managed_root,
                (
                    Path(tmp)
                    / "agent-managed"
                ).resolve(),
            )

    def test_managed_root_can_be_overridden_independently(self):
        with tempfile.TemporaryDirectory() as tmp:
            custom = (
                Path(tmp)
                / "custom-managed"
            )

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_MANAGED_ROOT":
                        str(custom),
                },
                clear=False,
            ):
                context = (
                    get_runtime_context()
                )

            self.assertEqual(
                context.managed_root,
                custom.resolve(),
            )

    def test_product_code_contains_no_user_specific_paths(self):
        repo = (
            Path(__file__)
            .resolve()
            .parents[1]
        )

        forbidden = (
            "/home/seckinozbek",
            "/mnt/c/Users/secki",
            "C:\\Users\\secki",
        )

        offenders: list[str] = []

        for directory in (
            repo / "agent",
            repo / "scripts",
            repo / "ui",
        ):
            for path in directory.rglob("*"):
                if (
                    not path.is_file()
                    or "__pycache__"
                    in path.parts
                ):
                    continue

                try:
                    text = path.read_text(
                        errors="ignore"
                    )
                except OSError:
                    continue

                for token in forbidden:
                    if token in text:
                        offenders.append(
                            f"{path.relative_to(repo)}: {token}"
                        )

        self.assertEqual(
            offenders,
            [],
            "Machine-specific paths remain:\n"
            + "\n".join(offenders),
        )


    def test_readme_has_no_user_specific_paths(self):
        repo = Path(__file__).resolve().parents[1]
        readme = repo / "README.md"

        text = readme.read_text(
            errors="ignore"
        )

        forbidden = (
            "/home/seckinozbek",
            "/mnt/c/Users/secki",
            "C:\\Users\\secki",
        )

        offenders = [
            token
            for token in forbidden
            if token in text
        ]

        self.assertEqual(
            offenders,
            [],
            "Machine-specific paths remain in README.",
        )



if __name__ == "__main__":
    unittest.main()
