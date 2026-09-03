from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.project_inspection import (
    inspect_project,
    read_project_file,
    search_project,
)
from agent.result_renderer import (
    render_execution_result,
)


class ProjectInspectionTest(unittest.TestCase):

    def _fixture(self):
        tmp = tempfile.TemporaryDirectory()
        root = Path(tmp.name)

        (root / "src").mkdir()

        (root / "pyproject.toml").write_text(
            '[project]\nname="portable-demo"\n'
        )

        (root / "README.md").write_text(
            "This project trains a text classifier.\n"
        )

        (root / "src" / "train.py").write_text(
            "def train_model():\n"
            "    # train classifier\n"
            "    return True\n"
        )

        return tmp, root

    def test_inspection_discovers_project_markers(self):
        tmp, root = self._fixture()

        try:
            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(root),
                },
                clear=False,
            ):
                result = inspect_project()

            self.assertIn(
                "pyproject.toml",
                result["markers"],
            )

            self.assertIn(
                "src/train.py",
                result["likely_entrypoints"],
            )
        finally:
            tmp.cleanup()

    def test_search_returns_file_provenance(self):
        tmp, root = self._fixture()

        try:
            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(root),
                },
                clear=False,
            ):
                result = search_project(
                    "Where is the classifier trained?"
                )

            paths = [
                item["source"]
                for item in result["evidence"]
            ]

            self.assertIn(
                "src/train.py",
                paths,
            )
        finally:
            tmp.cleanup()

    def test_read_blocks_path_escape(self):
        tmp, root = self._fixture()

        try:
            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(root),
                },
                clear=False,
            ):
                result = read_project_file(
                    "../secret.txt"
                )

            self.assertEqual(
                result["status"],
                "BLOCKED",
            )
        finally:
            tmp.cleanup()

    def test_renderer_turns_json_into_natural_language(self):
        result = render_execution_result(
            {
                "status": "SUCCESS",
                "verification": {
                    "verified": True,
                    "result": {
                        "records_processed": 1000,
                    },
                },
                "technical_details": {
                    "execution": {
                        "exit_code": 0,
                    }
                },
            }
        )

        self.assertIn(
            "1,000 records",
            result,
        )

        self.assertIn(
            "verified",
            result,
        )

        self.assertIn(
            "code 0",
            result,
        )

    def test_inspection_does_not_depend_on_repository_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)

            original = (
                base
                / "original-project-name"
            )

            original.mkdir()

            (original / "pyproject.toml").write_text(
                '[project]\nname="portable-demo"\n'
            )

            (original / "README.md").write_text(
                "Portable project fixture.\n"
            )

            renamed = (
                base
                / "completely-different-folder-name"
            )

            original.rename(
                renamed
            )

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(renamed),
                },
                clear=False,
            ):
                result = inspect_project()

            self.assertEqual(
                result["status"],
                "OK",
            )

            self.assertEqual(
                result["project_name"],
                "completely-different-folder-name",
            )


    def test_project_answer_does_not_depend_on_chat_service(self):
        repo = Path(__file__).resolve().parents[1]

        text = (
            repo
            / "agent"
            / "project_answer.py"
        ).read_text()

        self.assertNotIn(
            "from agent.chat_service import",
            text,
        )

        self.assertIn(
            "from agent.llm_client import qwen_chat",
            text,
        )



    def test_ignored_directories_are_not_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            (root / "src").mkdir()
            (root / ".git").mkdir()
            (root / ".venv").mkdir()

            (root / "src" / "real.py").write_text(
                "managed approval implementation\n"
            )

            (root / ".git" / "hidden.py").write_text(
                "secret_unique_git_term\n"
            )

            (root / ".venv" / "hidden.py").write_text(
                "secret_unique_venv_term\n"
            )

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(root),
                },
                clear=False,
            ):
                git_result = search_project(
                    "secret_unique_git_term"
                )

                venv_result = search_project(
                    "secret_unique_venv_term"
                )

                real_result = search_project(
                    "managed approval"
                )

            self.assertEqual(
                git_result["hits"],
                [],
            )

            self.assertEqual(
                venv_result["hits"],
                [],
            )

            self.assertTrue(
                any(
                    hit["path"]
                    == "src/real.py"
                    for hit
                    in real_result["hits"]
                )
            )



    def test_git_index_fast_path_includes_untracked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            import subprocess

            subprocess.run(
                ["git", "init", "-q", str(root)],
                check=True,
            )

            tracked = root / "tracked.py"
            untracked = root / "untracked.py"

            tracked.write_text(
                "tracked execution implementation\n"
            )

            untracked.write_text(
                "untracked approval implementation\n"
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    "tracked.py",
                ],
                check=True,
            )

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(root),
                },
                clear=False,
            ):
                from agent.project_inspection import (
                    build_project_index,
                )

                index = build_project_index()

            names = {
                path.name
                for path in index
            }

            self.assertIn(
                "tracked.py",
                names,
            )

            self.assertIn(
                "untracked.py",
                names,
            )



    def test_git_search_includes_untracked_source_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            import subprocess

            subprocess.run(
                [
                    "git",
                    "init",
                    "-q",
                    str(root),
                ],
                check=True,
            )

            (root / "README.md").write_text(
                "managed execution approval "
                * 100
            )

            (root / "worker.py").write_text(
                "def approve_managed_execution():\n"
                "    return True\n"
            )

            subprocess.run(
                [
                    "git",
                    "-C",
                    str(root),
                    "add",
                    "README.md",
                ],
                check=True,
            )

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(root),
                },
                clear=False,
            ):
                result = search_project(
                    (
                        "Which files implement managed "
                        "execution and approval?"
                    )
                )

            self.assertEqual(
                result["search_backend"],
                "git_grep",
            )

            paths = [
                hit["path"]
                for hit in result["hits"]
            ]

            self.assertIn(
                "worker.py",
                paths,
            )

            self.assertLess(
                paths.index("worker.py"),
                paths.index("README.md"),
            )



    def test_project_index_is_cached_within_ttl(self):
        from agent.project_inspection import (
            build_project_index,
            clear_project_index_cache,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            (root / "app.py").write_text(
                "print('hello')\n"
            )

            clear_project_index_cache()

            with patch(
                "agent.project_inspection._build_project_index_uncached",
                return_value=[root / "app.py"],
            ) as builder:
                first = build_project_index(
                    root=root
                )

                second = build_project_index(
                    root=root
                )

            self.assertEqual(
                first,
                second,
            )

            self.assertEqual(
                builder.call_count,
                1,
            )

    def test_search_evidence_distinguishes_implementation_and_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            import subprocess

            subprocess.run(
                [
                    "git",
                    "init",
                    "-q",
                    str(root),
                ],
                check=True,
            )

            (root / "agent").mkdir()
            (root / "tests").mkdir()

            (root / "agent" / "execution.py").write_text(
                "managed execution approval\n"
            )

            (root / "tests" / "test_execution.py").write_text(
                "managed execution approval\n"
            )

            with patch.dict(
                os.environ,
                {
                    "RESEARCH_CLOUD_PROJECT_ROOT":
                        str(root),
                },
                clear=False,
            ):
                result = search_project(
                    "Where is managed execution approval implemented?"
                )

            roles = {
                hit["path"]: hit["role"]
                for hit in result["hits"]
            }

            self.assertEqual(
                roles["agent/execution.py"],
                "implementation",
            )

            self.assertEqual(
                roles["tests/test_execution.py"],
                "validation",
            )

    @patch(
        "agent.project_answer.qwen_chat",
        side_effect=RuntimeError(
            "model unavailable"
        ),
    )
    @patch(
        "agent.project_answer.build_project_index",
        return_value=[],
    )
    @patch(
        "agent.project_answer.inspect_project",
        return_value={
            "status": "OK",
            "project_name": "demo",
            "markers": [],
            "likely_entrypoints": [],
            "evidence": [],
        },
    )
    @patch(
        "agent.project_answer.search_project",
        return_value={
            "status": "OK",
            "hits": [
                {
                    "path": "agent/execution.py",
                    "role": "implementation",
                    "score": 100,
                    "matched_terms": ["execution"],
                    "excerpt": "managed execution",
                }
            ],
            "evidence": [
                {
                    "type": "PROJECT_FILE",
                    "source": "agent/execution.py",
                    "role": "implementation",
                }
            ],
        },
    )
    def test_project_answer_has_deterministic_fallback_when_model_fails(
        self,
        _search,
        _inspect,
        _index,
        _qwen,
    ):
        from agent.project_answer import (
            answer_project_question,
        )

        result = answer_project_question(
            "Where is execution implemented?"
        )

        self.assertEqual(
            result["status"],
            "DEGRADED",
        )

        self.assertIn(
            "agent/execution.py",
            result["message"],
        )

        self.assertIn(
            "error",
            result,
        )



if __name__ == "__main__":
    unittest.main()
