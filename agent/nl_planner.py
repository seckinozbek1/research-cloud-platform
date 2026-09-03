from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

from agent.capabilities import (
    get_capability,
    public_capabilities,
)
from agent.execute_task import build_execution_plan


def get_qwen_api_url() -> str:
    explicit = os.environ.get("QWEN_API_URL")

    if explicit:
        return explicit

    host = os.environ.get("QWEN_HOST", "127.0.0.1")
    port = os.environ.get("QWEN_PORT", "8080")

    return f"http://{host}:{port}/v1/chat/completions"



SYSTEM_PROMPT = """
You are the natural-language planning layer of a controlled operations agent.

The user may have no infrastructure knowledge.

Your responsibility is to understand the requested outcome and map it to an
explicitly registered capability.

You do NOT execute actions.
You do NOT invent capabilities.
You do NOT make operational authorization decisions.

Rules:

1. Communicate in English.
2. Understand the user's goal in ordinary language.
3. Never ask the user for CPU, RAM, GPU, cloud flags, routing states, or other
   infrastructure internals merely because they exist in the backend.
4. Prefer facts that the system can inspect, discover, or measure itself.
5. Select only a capability explicitly present in the capability registry.
6. If the request is unsupported or genuinely ambiguous, ask ONE short,
   plain-English clarification question.
7. Never invent a capability ID.
8. Never output shell commands.
9. Never claim execution already occurred.
10. Do not expose internal policy names unless necessary.
11. Return JSON only.

Return exactly this structure:

{
  "intent": "execute" | "analyse" | "unknown",
  "capability": "<registered capability id or null>",
  "confidence": <number from 0 to 1>,
  "clarification_question": "<plain English question or null>",
  "user_facing_summary": "<short plain English explanation>"
}
""".strip()


def _extract_json(
    text: str,
) -> dict[str, Any]:
    cleaned = text.strip()

    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")

        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise ValueError(
            "Planner did not return a JSON object."
        )

    return json.loads(
        cleaned[start:end + 1]
    )


def _call_qwen(
    user_request: str,
    conversation_context: str | None = None,
) -> dict[str, Any]:
    registry = json.dumps(
        public_capabilities(),
        indent=2,
    )

    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": (
                "Available capabilities:\n"
                f"{registry}\n\n"
                "Conversation context:\n"
                f"{conversation_context or '(none)'}\n\n"
                "Current user request:\n"
                f"{user_request}"
            ),
        },
    ]

    payload = {
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 300,
        "chat_template_kwargs": {
            "enable_thinking": False,
        },
    }

    request = urllib.request.Request(
        get_qwen_api_url(),
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:
        body = json.loads(
            response.read().decode("utf-8")
        )

    content = (
        body["choices"][0]
        ["message"]["content"]
    )

    return _extract_json(content)


def _is_obviously_vague(
    user_request: str,
) -> bool:
    """
    Conservative deterministic guard for requests that contain no
    actionable intent.

    This prevents the LLM from forcing a vague request onto the only
    capability currently available.
    """

    normalized = " ".join(
        user_request.lower().strip().split()
    )

    vague_requests = {
        "do something",
        "do something with this",
        "do something with this project",
        "help",
        "help me",
        "do it",
        "handle this",
        "take care of this",
        "fix it",
    }

    if normalized in vague_requests:
        return True

    actionable_terms = {
        "test",
        "run",
        "execute",
        "verify",
        "check",
        "inspect",
        "analyse",
        "analyze",
        "prepare",
    }

    words = set(normalized.split())

    return not bool(
        words.intersection(actionable_terms)
    )


def plan_natural_language_request(
    user_request: str,
    conversation_context: str | None = None,
) -> dict[str, Any]:
    if _is_obviously_vague(user_request):
        return {
            "status": "CLARIFICATION_REQUIRED",
            "question": (
                "What would you like me to do with the project? "
                "For example, I can currently prepare and run "
                "a safe isolated test."
            ),
            "capability": None,
            "source": "deterministic_ambiguity_gate",
        }

    try:
        llm_plan = _call_qwen(
            user_request,
            conversation_context,
        )
    except Exception as exc:
        return {
            "status": "PLANNER_ERROR",
            "message": (
                "I could not interpret the request safely."
            ),
            "error": str(exc),
        }

    capability_id = llm_plan.get(
        "capability"
    )

    capability = (
        get_capability(capability_id)
        if isinstance(capability_id, str)
        else None
    )

    try:
        confidence = float(
            llm_plan.get("confidence", 0.0)
        )
    except (TypeError, ValueError):
        confidence = 0.0

    if (
        capability is None
        or confidence < 0.55
    ):
        question = (
            llm_plan.get(
                "clarification_question"
            )
            or (
                "Could you briefly describe what "
                "you want me to do?"
            )
        )

        return {
            "status": "CLARIFICATION_REQUIRED",
            "question": question,
            "capability": None,
            "llm_interpretation": llm_plan,
        }

    validated_execution_plan = (
        build_execution_plan(
            capability["execution_request"]
        )
    )

    return {
        "status": "PLAN_READY",
        "capability": {
            "id": capability["id"],
            "name": capability["name"],
            "description":
                capability["description"],
        },
        "approval_required":
            capability["approval_required"],
        "validated_execution_plan":
            validated_execution_plan,
        "user_facing_summary":
            llm_plan.get(
                "user_facing_summary"
            ),
    }
