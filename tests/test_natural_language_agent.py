import unittest
from unittest.mock import patch

from agent.capabilities import (
    get_capability,
    public_capabilities,
)
from agent.nl_execute import handle_request
from agent.nl_planner import (
    plan_natural_language_request,
)


SUPPORTED = {
    "intent": "execute",
    "capability": "managed_smoke_test",
    "confidence": 0.98,
    "clarification_question": None,
    "user_facing_summary": (
        "I can run a safe isolated local test."
    ),
}

LOW_CONFIDENCE = {
    "intent": "execute",
    "capability": "managed_smoke_test",
    "confidence": 0.30,
    "clarification_question": (
        "Would you like me to run a safe isolated test?"
    ),
    "user_facing_summary": (
        "The request is ambiguous."
    ),
}

INVENTED = {
    "intent": "execute",
    "capability": "delete_everything",
    "confidence": 0.99,
    "clarification_question": None,
    "user_facing_summary": (
        "I will delete everything."
    ),
}

UNKNOWN = {
    "intent": "unknown",
    "capability": None,
    "confidence": 0.10,
    "clarification_question": (
        "What would you like me to do?"
    ),
    "user_facing_summary": (
        "The request is unclear."
    ),
}


class NaturalLanguageAgentTest(unittest.TestCase):

    def test_safe_capability_is_registered(self):
        self.assertIsNotNone(
            get_capability("managed_smoke_test")
        )

    def test_unknown_capability_is_not_registered(self):
        self.assertIsNone(
            get_capability("delete_everything")
        )

    def test_public_registry_hides_internal_execution_contract(self):
        item = public_capabilities()[0]

        self.assertNotIn(
            "execution_request",
            item,
        )

    @patch(
        "agent.nl_planner._call_qwen"
    )
    def test_obviously_vague_request_bypasses_qwen(
        self,
        mock_qwen,
    ):
        result = plan_natural_language_request(
            "Do something with this project."
        )

        self.assertEqual(
            result["status"],
            "CLARIFICATION_REQUIRED",
        )

        self.assertEqual(
            result["source"],
            "deterministic_ambiguity_gate",
        )

        mock_qwen.assert_not_called()

    @patch(
        "agent.nl_planner._call_qwen"
    )
    def test_help_me_is_treated_as_vague(
        self,
        mock_qwen,
    ):
        result = plan_natural_language_request(
            "Help me."
        )

        self.assertEqual(
            result["status"],
            "CLARIFICATION_REQUIRED",
        )

        mock_qwen.assert_not_called()

    @patch(
        "agent.nl_planner._call_qwen",
        return_value=SUPPORTED,
    )
    def test_specific_supported_request_produces_plan(
        self,
        _,
    ):
        result = plan_natural_language_request(
            "Run a safe local test."
        )

        self.assertEqual(
            result["status"],
            "PLAN_READY",
        )

        self.assertEqual(
            result["capability"]["id"],
            "managed_smoke_test",
        )

        self.assertEqual(
            result["validated_execution_plan"]
            ["placement"]["decision"],
            "LOCAL_PC",
        )

    @patch(
        "agent.nl_planner._call_qwen",
        return_value=LOW_CONFIDENCE,
    )
    def test_low_confidence_requires_clarification(
        self,
        _,
    ):
        result = plan_natural_language_request(
            "Run something."
        )

        self.assertEqual(
            result["status"],
            "CLARIFICATION_REQUIRED",
        )

    @patch(
        "agent.nl_planner._call_qwen",
        return_value=INVENTED,
    )
    def test_invented_capability_is_rejected(
        self,
        _,
    ):
        result = plan_natural_language_request(
            "Delete the environment."
        )

        self.assertEqual(
            result["status"],
            "CLARIFICATION_REQUIRED",
        )

        self.assertIsNone(
            result["capability"]
        )

    @patch(
        "agent.nl_planner._call_qwen",
        return_value=UNKNOWN,
    )
    def test_unknown_intent_requires_clarification(
        self,
        _,
    ):
        result = plan_natural_language_request(
            "Please handle this."
        )

        self.assertEqual(
            result["status"],
            "CLARIFICATION_REQUIRED",
        )

    @patch(
        "agent.nl_planner._call_qwen",
        side_effect=RuntimeError(
            "local model unavailable"
        ),
    )
    def test_planner_failure_fails_safe(
        self,
        _,
    ):
        result = plan_natural_language_request(
            "Run a safe test."
        )

        self.assertEqual(
            result["status"],
            "PLANNER_ERROR",
        )

    @patch(
        "agent.nl_planner._call_qwen",
        return_value=SUPPORTED,
    )
    def test_natural_language_execution_requires_approval(
        self,
        _,
    ):
        result = handle_request(
            "Run a safe test workload."
        )

        self.assertEqual(
            result["status"],
            "APPROVAL_REQUIRED",
        )

    @patch(
        "agent.nl_planner._call_qwen",
        return_value=SUPPORTED,
    )
    @patch(
        "agent.nl_execute.execute"
    )
    def test_approved_request_reaches_only_managed_executor(
        self,
        mock_execute,
        _,
    ):
        mock_execute.return_value = {
            "status": "SUCCESS",
            "job_id": "job-safe",
            "workspace": "/safe/job-safe",
            "verification": {
                "verified": True,
            },
        }

        result = handle_request(
            "Run the safe test.",
            approved=True,
        )

        self.assertEqual(
            result["status"],
            "SUCCESS",
        )

        mock_execute.assert_called_once()

        kwargs = mock_execute.call_args.kwargs

        self.assertTrue(
            kwargs["approved"]
        )

        self.assertNotIn(
            "rm ",
            kwargs["request"],
        )


if __name__ == "__main__":
    unittest.main()
