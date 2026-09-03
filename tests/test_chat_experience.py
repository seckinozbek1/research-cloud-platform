from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

import agent.chat_service as chat


class ChatExperienceTest(unittest.TestCase):

    def setUp(self):
        chat._SESSIONS.clear()
        chat._SESSION_STATE.clear()

    @patch(
        "agent.chat_service._route",
        return_value="CHAT",
    )
    @patch(
        "agent.chat_service._chat_reply",
        return_value="Doing well. What are you working on?",
    )
    def test_casual_message_gets_normal_reply(
        self,
        _reply,
        _route,
    ):
        result = chat.handle_chat_message(
            "What's up?"
        )

        self.assertEqual(
            result["kind"],
            "chat",
        )

        self.assertIn(
            "Doing well",
            result["message"],
        )

        self.assertNotIn(
            "approval_id",
            result,
        )

    @patch(
        "agent.chat_service._route",
        return_value="OPERATION",
    )
    @patch(
        "agent.chat_service.analyse_user_request"
    )
    def test_operation_enters_approval_flow(
        self,
        analyse,
        _route,
    ):
        analyse.return_value = {
            "status": "APPROVAL_REQUIRED",
            "approval_id": "approval-1",
            "plan": {
                "capability": {
                    "description": "Run a safe test.",
                },
                "user_facing_summary": "I can run the safe test.",
            },
        }

        result = chat.handle_chat_message(
            "Run a safe test."
        )

        self.assertEqual(
            result["kind"],
            "approval",
        )

        self.assertEqual(
            result["approval_id"],
            "approval-1",
        )

        self.assertIn(
            "controlled",
            result["message"],
        )

    @patch(
        "agent.chat_service.execute_approved_plan"
    )
    def test_verified_execution_is_human_readable(
        self,
        execute,
    ):
        execute.return_value = {
            "status": "SUCCESS",
            "verification": {
                "verified": True,
            },
        }

        result = chat.approve_chat_action(
            "session-1",
            "approval-1",
        )

        self.assertEqual(
            result["kind"],
            "result",
        )

        self.assertIn(
            "verified",
            result["message"],
        )

        self.assertIn(
            "raw",
            result,
        )

    def test_ui_exposes_raw_json_below_chat(self):
        repo = Path(__file__).resolve().parents[1]
        text = (
            repo / "ui" / "index.html"
        ).read_text()

        self.assertIn(
            "Raw JSON",
            text,
        )

        self.assertIn(
            "Approve & Run",
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

    def test_ui_has_no_external_frontend_dependency(self):
        repo = Path(__file__).resolve().parents[1]
        text = (
            repo / "ui" / "index.html"
        ).read_text()

        self.assertNotIn(
            "<script src=",
            text,
        )

        self.assertNotIn(
            "<link href=\"https://",
            text,
        )

    def test_one_launcher_starts_model_and_app(self):
        repo = Path(__file__).resolve().parents[1]
        text = (
            repo
            / "scripts"
            / "start_operations_app.sh"
        ).read_text()

        self.assertIn(
            "start_qwen_server.sh",
            text,
        )

        self.assertIn(
            "uvicorn",
            text,
        )


    @patch(
        "agent.chat_service.execute_approved_plan"
    )
    def test_did_it_work_uses_verified_session_state(
        self,
        execute,
    ):
        execute.return_value = {
            "status": "SUCCESS",
            "verification": {
                "verified": True,
            },
        }

        chat.approve_chat_action(
            "session-followup",
            "approval-1",
        )

        with patch(
            "agent.chat_service._route"
        ) as route:
            result = chat.handle_chat_message(
                "Did it work?",
                session_id="session-followup",
            )

        self.assertEqual(
            result["kind"],
            "chat",
        )

        self.assertIn(
            "verified",
            result["message"],
        )

        self.assertEqual(
            result["raw"]["status"],
            "SUCCESS",
        )

        route.assert_not_called()

    @patch(
        "agent.chat_service.execute_approved_plan"
    )
    def test_was_it_successful_uses_same_verified_result(
        self,
        execute,
    ):
        execute.return_value = {
            "status": "SUCCESS",
            "verification": {
                "verified": True,
            },
        }

        chat.approve_chat_action(
            "session-followup-2",
            "approval-2",
        )

        result = chat.handle_chat_message(
            "Was it successful?",
            session_id="session-followup-2",
        )

        self.assertEqual(
            result["kind"],
            "chat",
        )

        self.assertIn(
            "successfully",
            result["message"],
        )



    @patch(
        "agent.chat_service._route",
        return_value="PROJECT",
    )
    @patch(
        "agent.chat_service.answer_project_question"
    )
    def test_project_question_uses_read_only_evidence(
        self,
        answer,
        _route,
    ):
        answer.return_value = {
            "status": "OK",
            "message": (
                "The training entry point is src/train.py."
            ),
            "evidence": [
                {
                    "type": "PROJECT_FILE",
                    "source": "src/train.py",
                }
            ],
        }

        result = chat.handle_chat_message(
            "Where is the training code?"
        )

        self.assertEqual(
            result["kind"],
            "project_answer",
        )

        self.assertIn(
            "src/train.py",
            result["message"],
        )

        self.assertEqual(
            result["raw"]["evidence"][0]["type"],
            "PROJECT_FILE",
        )



if __name__ == "__main__":
    unittest.main()
