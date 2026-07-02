from __future__ import annotations

import asyncio

from support_agent_lab.bootstrap import create_container
from support_agent_lab.models import new_id


async def _demo() -> None:
    container = create_container()
    conversation_id = new_id("conv")
    print("Production Support Agent Lab")
    print("Type a message. Empty line exits.")
    while True:
        text = input("user> ").strip()
        if not text:
            return
        response = await container.orchestrator.handle_message(conversation_id, "user_demo", text)
        print(f"agent> {response.message.content}")
        print(f"trace> {response.trace.id} tools={[tool.name for tool in response.trace.tool_results]}")


def main() -> None:
    asyncio.run(_demo())

