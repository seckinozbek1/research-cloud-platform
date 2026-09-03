from __future__ import annotations

import os

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from agent.chat_service import (
    approve_chat_action,
    handle_chat_message,
)
from agent.runtime_context import get_runtime_context
from agent.ui_service import (
    analyse_user_request,
    execute_approved_plan,
)


app = FastAPI(
    title="Operations Meta-Agent",
    version="0.2.0",
)


class ChatPayload(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=5000,
    )

    session_id: str | None = Field(
        default=None,
        max_length=128,
    )


class ChatApprovalPayload(BaseModel):
    session_id: str = Field(
        min_length=1,
        max_length=128,
    )

    approval_id: str = Field(
        min_length=1,
        max_length=128,
    )


class AnalysePayload(BaseModel):
    request: str = Field(
        min_length=1,
        max_length=5000,
    )


class ExecutePayload(BaseModel):
    approval_id: str = Field(
        min_length=1,
        max_length=128,
    )



def _demo_mode() -> bool:
    return os.getenv("OPERATIONS_DEMO_MODE", "").strip().lower() in {
        "1", "true", "yes", "on"
    }


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get(
    "/",
    response_class=HTMLResponse,
)
def index() -> HTMLResponse:
    path = (
        get_runtime_context()
        .project_root
        / "ui"
        / "index.html"
    )

    if not path.is_file():
        raise HTTPException(
            status_code=500,
            detail="UI file not found.",
        )

    return HTMLResponse(
        path.read_text()
    )


@app.post("/chat/message")
def chat_message(
    payload: ChatPayload,
) -> dict[str, Any]:
    return handle_chat_message(
        payload.message,
        payload.session_id,
    )


@app.post("/chat/approve")
def chat_approve(
    payload: ChatApprovalPayload,
) -> dict[str, Any]:
    if _demo_mode():
        raise HTTPException(
            status_code=403,
            detail="Execution is disabled in demo mode.",
        )

    return approve_chat_action(
        payload.session_id,
        payload.approval_id,
    )


# Compatibility endpoints retained for development/tests.

@app.post("/agent/analyse")
def analyse(
    payload: AnalysePayload,
) -> dict[str, Any]:
    return analyse_user_request(
        payload.request
    )


@app.post("/agent/execute")
def execute_plan(
    payload: ExecutePayload,
) -> dict[str, Any]:
    if _demo_mode():
        raise HTTPException(
            status_code=403,
            detail="Execution is disabled in demo mode.",
        )

    result = execute_approved_plan(
        payload.approval_id
    )

    if result["status"] == "APPROVAL_NOT_FOUND":
        raise HTTPException(
            status_code=404,
            detail=result["message"],
        )

    return result
