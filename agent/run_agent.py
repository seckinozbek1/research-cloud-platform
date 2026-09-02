from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any

from agent.tools import TOOLS, TOOL_SCHEMAS
from agent.validation import validate_placement
from agent.output import print_result


API_URL = "http://127.0.0.1:8080/v1/chat/completions"

SYSTEM_PROMPT = """
You are a case-agnostic infrastructure operations meta-agent.

Your current role is evidence collection and explanation.

The program has a separate deterministic validation layer that owns
operational placement decisions. Your prose is not an authoritative
placement decision.

Rules:

1. Never invent operational facts.
2. Clearly distinguish OBSERVED, INFERRED, and UNKNOWN information.
3. Missing information remains UNKNOWN.
4. Environment capacity alone is not workload suitability.
5. For local-versus-cloud placement questions, inspect ALL THREE:
   - the current environment
   - the workload request
   - the explicit placement policy
6. Do not call CPU, RAM, GPU, disk, or another resource sufficient,
   insufficient, high, low, risky, or constrained without workload-specific
   evidence supporting that comparison.
7. Disk utilization alone is not evidence of insufficient storage.
8. Dirty Git state alone is not evidence of instability or unreliability.
9. Current free GPU memory may include memory consumed by this agent's
   inference server.
10. Do not recommend local, cloud, hybrid, server, or distributed placement
    in this phase. Summarize evidence and unknowns instead.
11. Tools are authoritative only for facts they actually measure.
12. You have read-only capabilities only.
""".strip()


def call_model(
    messages: list[dict[str, Any]],
) -> dict[str, Any]:
    payload = {
        "messages": messages,
        "tools": TOOL_SCHEMAS,
        "tool_choice": "auto",
        "temperature": 0.1,
        "max_tokens": 500,
        "chat_template_kwargs": {
            "enable_thinking": False,
        },
    }

    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=120,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def execute_tool(
    name: str,
    user_request: str,
) -> dict[str, Any]:
    if name not in TOOLS:
        return {
            "error": f"Unknown tool: {name}",
        }

    if name in {"inspect_workload", "inspect_policy"}:
        return TOOLS[name](user_request)

    return TOOLS[name]()


def run_agent(
    user_request: str,
) -> tuple[str, dict[str, Any]]:
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT,
        },
        {
            "role": "user",
            "content": user_request,
        },
    ]

    evidence: dict[str, Any] = {}

    for _ in range(6):
        response = call_model(messages)
        message = response["choices"][0]["message"]

        tool_calls = message.get("tool_calls") or []

        if not tool_calls:
            return (
                message.get("content", ""),
                evidence,
            )

        messages.append(message)

        for call in tool_calls:
            name = call["function"]["name"]

            print(f"\n[tool request] {name}")

            result = execute_tool(
                name,
                user_request,
            )

            evidence[name] = result

            print(
                json.dumps(
                    result,
                    indent=2,
                )
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": json.dumps(result),
                }
            )

    raise RuntimeError(
        "Agent exceeded maximum tool-call iterations."
    )


if __name__ == "__main__":
    user_request = (
        " ".join(sys.argv[1:])
        or "Inspect the current environment."
    )

    narrative, evidence = run_agent(user_request)

    validated = validate_placement(evidence)

    print_result(
        evidence=evidence,
        validated=validated,
        commentary=narrative,
    )
