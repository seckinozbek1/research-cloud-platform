from __future__ import annotations

import json
import re
import threading
import uuid
from typing import Any

from agent.llm_client import qwen_chat
from agent.result_renderer import render_execution_result
from agent.project_answer import answer_project_question
from agent.ui_service import (
    analyse_user_request,
    execute_approved_plan,
)


_SESSIONS: dict[str, list[dict[str, str]]] = {}

# Structured operational state is kept separately from prose history.
# Conversation text is useful context, but verified execution results
# should not have to be reconstructed from natural language.
_SESSION_STATE: dict[str, dict[str, Any]] = {}

_LOCK = threading.Lock()
MAX_HISTORY = 16


_qwen = qwen_chat

def _history(
    session_id: str,
) -> list[dict[str, str]]:
    with _LOCK:
        return list(
            _SESSIONS.get(
                session_id,
                []
            )
        )


def _append(
    session_id: str,
    role: str,
    content: str,
) -> None:
    with _LOCK:
        messages = _SESSIONS.setdefault(
            session_id,
            [],
        )

        messages.append(
            {
                "role": role,
                "content": content,
            }
        )

        del messages[:-MAX_HISTORY]


def _context_text(
    history: list[dict[str, str]],
) -> str:
    return "\n".join(
        f"{item['role']}: {item['content']}"
        for item in history[-8:]
    )



def _remember_operation(
    session_id: str,
    result: dict[str, Any],
) -> None:
    with _LOCK:
        state = _SESSION_STATE.setdefault(
            session_id,
            {},
        )

        state["last_operation"] = result


def _last_operation(
    session_id: str,
) -> dict[str, Any] | None:
    with _LOCK:
        state = _SESSION_STATE.get(
            session_id,
            {},
        )

        result = state.get(
            "last_operation"
        )

        if isinstance(result, dict):
            return dict(result)

    return None


def _is_operation_status_followup(
    message: str,
) -> bool:
    """
    Recognize simple referential questions about the most recent
    operation.

    These can be answered from verified structured session state and
    should not be reinterpreted as a new operational request.
    """

    normalized = re.sub(
        r"[^a-z0-9]+",
        " ",
        message.lower(),
    ).strip()

    phrases = {
        "did it work",
        "did that work",
        "did the run work",
        "did the job work",
        "did the operation work",
        "did it succeed",
        "did that succeed",
        "was it successful",
        "was that successful",
        "was the run successful",
        "is it done",
        "is that done",
        "did it finish",
        "did that finish",
        "did it complete",
        "did that complete",
    }

    return normalized in phrases


def _route(
    message: str,
    history: list[dict[str, str]],
) -> str:
    system = """
Classify the CURRENT user message for an operations assistant.

Return exactly one word:

CHAT
PROJECT
or
OPERATION

CHAT includes greetings, casual conversation, conceptual questions,
general explanations, and ordinary discussion that does not require
inspection or execution.

PROJECT includes questions whose answer depends on the actual contents,
structure, configuration, dependencies, scripts, or implementation of
the active software project. Examples include "what does this repo do?",
"where is training configured?", or "which file starts the API?"

OPERATION includes requests to inspect live machine state, diagnose runtime
behaviour, check live logs, execute, run, test, modify, deploy, provision,
verify a real system, or otherwise perform an operational action.

Use conversation context to resolve references such as "run it".
Do not perform the task. Classify only.
""".strip()

    messages = [
        {
            "role": "system",
            "content": system,
        },
        *history[-8:],
        {
            "role": "user",
            "content": message,
        },
    ]

    result = _qwen(
        messages,
        max_tokens=10,
    ).upper()

    if "OPERATION" in result:
        return "OPERATION"

    if "PROJECT" in result:
        return "PROJECT"

    return "CHAT"


def _chat_reply(
    message: str,
    history: list[dict[str, str]],
) -> str:
    system = """
You are an Operations Meta-Agent.

You are a normal conversational assistant as well as an operations
specialist.

For ordinary conversation, respond naturally and concisely.
Do not pretend to inspect, execute, or modify anything unless an
operational tool has actually been used.

The product interface is currently English-first.
""".strip()

    return _qwen(
        [
            {
                "role": "system",
                "content": system,
            },
            *history[-8:],
            {
                "role": "user",
                "content": message,
            },
        ],
        max_tokens=300,
    )


def _humanise_plan(
    result: dict[str, Any],
) -> str:
    plan = result["plan"]

    summary = (
        plan.get("user_facing_summary")
        or plan["capability"]["description"]
    )

    return (
        f"I can do that. {summary} "
        "I will use a controlled managed workspace, "
        "verify the result, and record what happened. "
        "Your project source files will not be modified, "
        "and no paid cloud resources will be created."
    )


def _humanise_result(
    result: dict[str, Any],
) -> str:
    return render_execution_result(
        result
    )


def handle_chat_message(
    message: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    session_id = (
        session_id
        or uuid.uuid4().hex
    )

    cleaned = message.strip()

    if not cleaned:
        return {
            "session_id": session_id,
            "kind": "clarification",
            "message": "What would you like to talk about or do?",
        }

    history = _history(
        session_id
    )

    previous_operation = _last_operation(
        session_id
    )

    if (
        previous_operation is not None
        and _is_operation_status_followup(cleaned)
    ):
        _append(
            session_id,
            "user",
            cleaned,
        )

        reply = _humanise_result(
            previous_operation
        )

        _append(
            session_id,
            "assistant",
            reply,
        )

        return {
            "session_id": session_id,
            "kind": "chat",
            "message": reply,
            "raw": previous_operation,
        }

    try:
        route = _route(
            cleaned,
            history,
        )
    except Exception as exc:
        return {
            "session_id": session_id,
            "kind": "error",
            "message": (
                "I could not reach the local language model."
            ),
            "raw": {
                "error": str(exc),
            },
        }

    _append(
        session_id,
        "user",
        cleaned,
    )

    if route == "CHAT":
        reply = _chat_reply(
            cleaned,
            history,
        )

        _append(
            session_id,
            "assistant",
            reply,
        )

        return {
            "session_id": session_id,
            "kind": "chat",
            "message": reply,
        }

    if route == "PROJECT":
        try:
            project_result = answer_project_question(
                cleaned
            )

        except Exception as exc:
            project_result = {
                "status": "ERROR",
                "message": (
                    "I could not inspect the project safely. "
                    "No project files were modified. "
                    "You can retry the request."
                ),
                "error": {
                    "type": type(exc).__name__,
                    "message": str(exc),
                },
            }

        reply = project_result["message"]

        _append(
            session_id,
            "assistant",
            reply,
        )

        return {
            "session_id": session_id,
            "kind": "project_answer",
            "message": reply,
            "raw": project_result,
        }

    result = analyse_user_request(
        cleaned,
        conversation_context=_context_text(
            history
        ),
        session_id=session_id,
    )

    status = result.get("status")

    if status == "APPROVAL_REQUIRED":
        reply = _humanise_plan(
            result
        )

        _append(
            session_id,
            "assistant",
            reply,
        )

        return {
            "session_id": session_id,
            "kind": "approval",
            "message": reply,
            "approval_id": result["approval_id"],
            "raw": result,
        }

    if status == "CLARIFICATION_REQUIRED":
        reply = (
            result.get("question")
            or "Could you clarify what you want me to do?"
        )

        _append(
            session_id,
            "assistant",
            reply,
        )

        return {
            "session_id": session_id,
            "kind": "clarification",
            "message": reply,
            "raw": result,
        }

    reply = (
        result.get("message")
        or "I could not prepare a safe operational plan."
    )

    _append(
        session_id,
        "assistant",
        reply,
    )

    return {
        "session_id": session_id,
        "kind": "error",
        "message": reply,
        "raw": result,
    }


def approve_chat_action(
    session_id: str,
    approval_id: str,
) -> dict[str, Any]:
    result = execute_approved_plan(
        approval_id,
        session_id=session_id,
    )

    _remember_operation(
        session_id,
        result,
    )

    message = _humanise_result(
        result
    )

    _append(
        session_id,
        "assistant",
        message,
    )

    return {
        "session_id": session_id,
        "kind": (
            "result"
            if result.get("status") == "SUCCESS"
            else "error"
        ),
        "message": message,
        "raw": result,
    }
