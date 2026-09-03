from __future__ import annotations

import json
import urllib.request

from agent.nl_planner import get_qwen_api_url


def qwen_chat(
    messages: list[dict[str, str]],
    max_tokens: int = 350,
    temperature: float = 0.2,
) -> str:
    """
    Shared local OpenAI-compatible Qwen client.

    This module owns transport only.
    It performs no routing, planning, authorization,
    filesystem access, or execution.
    """

    payload = {
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
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

    return (
        body["choices"][0]
        ["message"]["content"]
        .strip()
    )
