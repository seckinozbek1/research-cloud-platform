import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.execute_task import execute
from agent.execution import (
    create_workspace,
    run_managed_job,
    verify_job,
    workspace_path,
    write_manifest,
)


LOCAL_PLACEMENT = {
    "decision": "LOCAL_PC",
    "status": "RESOLVED",
}

BURST_PLACEMENT = {
    "decision": "CLOUD_BURST",
    "status": "RESOLVED",
}


class OperationsExecutionTest(
    unittest.TestCase
):

    def setUp(self):
        self.tmp = (
            tempfile.TemporaryDirectory()
        )
        self.root = Path(
            self.tmp.name
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_rejects_path_traversal_job_id(self):
        with self.assertRaises(ValueError):
            workspace_path(
                "../escape",
                self.root,
            )

    def test_rejects_absolute_like_job_id(self):
        with self.assertRaises(ValueError):
            workspace_path(
                "/tmp/escape",
                self.root,
            )

    def test_workspace_creates_expected_dirs(self):
        ws = create_workspace(
            "job-test",
            self.root,
        )

        for name in [
            "input",
            "scratch",
            "output",
            "logs",
        ]:
            self.assertTrue(
                (ws / name).is_dir()
            )

    def test_workspace_has_marker(self):
        ws = create_workspace(
            "job-marker",
            self.root,
        )

        self.assertTrue(
            (
                ws
                / ".agent_workspace"
            ).exists()
        )

    def test_manifest_rejects_unknown_job_kind(self):
        create_workspace(
            "job-invalid",
            self.root,
        )

        with self.assertRaises(
            ValueError
        ):
            write_manifest(
                "job-invalid",
                {
                    "job_kind":
                        "arbitrary",
                },
                self.root,
            )

    def test_manifest_rejects_arbitrary_command(self):
        create_workspace(
            "job-command",
            self.root,
        )

        with self.assertRaises(
            ValueError
        ):
            write_manifest(
                "job-command",
                {
                    "job_kind":
                        "managed_smoke",
                    "command":
                        "rm -rf /",
                },
                self.root,
            )

    @patch(
        "agent.execute_task."
        "validate_placement",
        return_value=LOCAL_PLACEMENT,
    )
    def test_execution_requires_approval(
        self,
        _,
    ):
        result = execute(
            "test workload",
            approved=False,
            root=self.root,
        )

        self.assertEqual(
            result["status"],
            "APPROVAL_REQUIRED",
        )

        jobs = [
            p
            for p in self.root.iterdir()
            if p.name != "_audit"
        ]

        self.assertEqual(
            jobs,
            [],
        )

    @patch(
        "agent.execute_task."
        "validate_placement",
        return_value=BURST_PLACEMENT,
    )
    def test_non_local_placement_blocks_execution(
        self,
        _,
    ):
        result = execute(
            "test workload",
            approved=True,
            root=self.root,
        )

        self.assertEqual(
            result["status"],
            "BLOCKED",
        )

    @patch(
        "agent.execute_task."
        "validate_placement",
        return_value=LOCAL_PLACEMENT,
    )
    def test_approved_local_job_executes(
        self,
        _,
    ):
        result = execute(
            "test workload",
            approved=True,
            job_id="job-run",
            root=self.root,
        )

        self.assertEqual(
            result["status"],
            "SUCCESS",
        )

        self.assertEqual(
            result["execution"]
            ["exit_code"],
            0,
        )

    def test_managed_worker_creates_result(self):
        create_workspace(
            "job-worker",
            self.root,
        )

        write_manifest(
            "job-worker",
            {
                "job_kind":
                    "managed_smoke",
            },
            self.root,
        )

        result = run_managed_job(
            "job-worker",
            self.root,
        )

        self.assertEqual(
            result["exit_code"],
            0,
        )

        self.assertTrue(
            (
                self.root
                / "job-worker"
                / "output"
                / "result.json"
            ).exists()
        )

    def test_verification_detects_success(self):
        create_workspace(
            "job-verify",
            self.root,
        )

        write_manifest(
            "job-verify",
            {
                "job_kind":
                    "managed_smoke",
            },
            self.root,
        )

        run_managed_job(
            "job-verify",
            self.root,
        )

        result = verify_job(
            "job-verify",
            self.root,
        )

        self.assertTrue(
            result["verified"]
        )

    def test_audit_log_records_lifecycle(self):
        create_workspace(
            "job-audit",
            self.root,
        )

        write_manifest(
            "job-audit",
            {
                "job_kind":
                    "managed_smoke",
            },
            self.root,
        )

        run_managed_job(
            "job-audit",
            self.root,
        )

        verify_job(
            "job-audit",
            self.root,
        )

        audit = (
            self.root
            / "_audit"
            / "execution_events.jsonl"
        )

        events = [
            json.loads(line)
            ["event"]
            for line
            in audit.read_text()
            .splitlines()
        ]

        self.assertEqual(
            events,
            [
                "workspace_created",
                "manifest_written",
                "job_executed",
                "verification_passed",
            ],
        )


if __name__ == "__main__":
    unittest.main()
