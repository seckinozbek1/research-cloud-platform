from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from agent.chat_service import (
    _extract_project_location,
    _set_project_root,
    _active_project_root,
)


class ProjectLocationTest(unittest.TestCase):

    def test_extracts_explicit_project_location(self):
        path = _extract_project_location(
            "Use /tmp/example-project as the project location"
        )
        self.assertEqual(
            path,
            Path("/tmp/example-project").resolve(),
        )

    def test_project_root_is_session_scoped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()

            _set_project_root(
                "session-a",
                root,
            )

            self.assertEqual(
                _active_project_root("session-a"),
                root,
            )

            self.assertIsNone(
                _active_project_root("session-b")
            )
