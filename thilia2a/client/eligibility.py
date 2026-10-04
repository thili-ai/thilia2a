"""A deterministic A2A client for the Returns Eligibility Assistant — no LLM involved, the same
real client path every lesson used to grade the system.
"""
import re

import a2a.types as t
from a2a.client.client_factory import create_client


async def ask(order_id_text: str, base_url: str = "http://127.0.0.1:8101") -> tuple[str, str | None]:
    """Ask the Order Agent about one order; return (state_name, message_text)."""
    client = await create_client(base_url)
    message = t.Message(
        message_id=f"msg-{order_id_text}", role=t.Role.ROLE_USER, parts=[t.Part(text=order_id_text)],
    )
    request = t.SendMessageRequest(message=message)
    async for event in client.send_message(request):
        state = t.TaskState.Name(event.task.status.state)
        text = event.task.status.message.parts[0].text if event.task.status.HasField("message") else None
        return state, text


def parse_returnable(text: str | None) -> bool | None:
    """Extract the returnable=True/False verdict from an Order Agent's completion message."""
    match = re.search(r"returnable=(True|False)", text or "")
    return match.group(1) == "True" if match else None
