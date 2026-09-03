from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import agent.web_app as web_app
import agent.ui_service as service


PLAN = {
    "status": "PLAN_READY",
    "capability": {
        "id": "managed_smoke_test",
        "name": "Safe managed local test",
        "description": "Safe test.",
    },
    "approval_required": True,
    "validated_execution_plan": {
        "placement": {
            "decision": "LOCAL_PC",
        }
    },
    "user_facing_summary": "Safe local test.",
}


class WebUITest(unittest.TestCase):

    def setUp(self):
        service.clear_pending_approvals()

    @patch(
        "agent.ui_service.plan_natural_language_request",
        return_value=PLAN,
    )
    def test_analysis_creates_approval(self, _):
        result = service.analyse_user_request(
            "Run a safe test."
        )

        self.assertEqual(
            result["status"],
            "APPROVAL_REQUIRED",
        )

        self.assertTrue(
            result["approval_id"]
        )

    @patch(
        "agent.ui_service.plan_natural_language_request",
        return_value={
            "status": "CLARIFICATION_REQUIRED",
            "question": "What should I do?",
        },
    )
    def test_clarification_has_no_approval(self, _):
        result = service.analyse_user_request(
            "Help."
        )

        self.assertEqual(
            result["status"],
            "CLARIFICATION_REQUIRED",
        )

        self.assertNotIn(
            "approval_id",
            result,
        )

    def test_invalid_approval_is_rejected(self):
        result = service.execute_approved_plan(
            "not-real"
        )

        self.assertEqual(
            result["status"],
            "APPROVAL_NOT_FOUND",
        )

    @patch(
        "agent.ui_service.plan_natural_language_request",
        return_value=PLAN,
    )
    @patch(
        "agent.ui_service.execute"
    )
    def test_approval_executes_registered_capability(
        self,
        mock_execute,
        _,
    ):
        mock_execute.return_value = {
            "status": "SUCCESS",
            "job_id": "ui-job",
            "verification": {
                "verified": True,
            },
        }

        analysed = service.analyse_user_request(
            "Run a safe test."
        )

        result = service.execute_approved_plan(
            analysed["approval_id"]
        )

        self.assertEqual(
            result["status"],
            "SUCCESS",
        )

        mock_execute.assert_called_once()

    @patch(
        "agent.ui_service.plan_natural_language_request",
        return_value=PLAN,
    )
    @patch(
        "agent.ui_service.execute"
    )
    def test_approval_is_single_use(
        self,
        mock_execute,
        _,
    ):
        mock_execute.return_value = {
            "status": "SUCCESS",
            "job_id": "ui-job",
            "verification": {
                "verified": True,
            },
        }

        analysed = service.analyse_user_request(
            "Run a safe test."
        )

        token = analysed["approval_id"]

        service.execute_approved_plan(token)
        second = service.execute_approved_plan(token)

        self.assertEqual(
            second["status"],
            "APPROVAL_NOT_FOUND",
        )

    def test_web_app_exposes_required_routes(self):
        paths = {
            route.path
            for route in web_app.app.routes
        }

        for expected in (
            "/",
            "/health",
            "/agent/analyse",
            "/agent/execute",
        ):
            self.assertIn(
                expected,
                paths,
            )

    def test_ui_is_local_and_has_approval_control(self):
        repo = Path(__file__).resolve().parents[1]
        text = (
            repo / "ui" / "index.html"
        ).read_text()

        self.assertIn(
            "Approve & Run",
            text,
        )

        self.assertIn(
            "Raw JSON",
            text,
        )

        self.assertIn(
            "/chat/message",
            text,
        )

        self.assertIn(
            "/chat/approve",
            text,
        )

        self.assertNotIn(
            "https://",
            text,
        )


if __name__ == "__main__":
    unittest.main()
