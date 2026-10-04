"""The Order Agent — wraps `thilimcp`'s exact MCP server as its own tool backend, and delegates to
the Catalog Agent over A2A, mid-task, for the one thing it doesn't know: return policy.

Two protocols, two different jobs, inside the same `execute()`: MCP reaches this agent's own
database; A2A reaches a different agent it has never imported.
"""
from datetime import date

import a2a.helpers as h
import a2a.types as t
from a2a.client.client_factory import create_client
from a2a.client.errors import AgentCardResolutionError
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from fastapi import FastAPI
from mcp.client import Client as MCPClient
from mcp.server.mcpserver import MCPServer
from thilimcp import build_server

RPC_URL = "/a2a/v1"

# The dataset's own reference date — thilimcp's seed script has no concept of "now".
TODAY = date(2026, 9, 30)


class OrderExecutor(AgentExecutor):
    """Fixed version: a bad order id and an unreachable Catalog Agent both fail honestly via
    `TaskUpdater.failed()`, instead of raising an unhandled exception. See README for why this
    matters — both gaps looked identical (a raised `InternalError`) before being fixed."""

    def __init__(self, mcp_server: MCPServer, catalog_url: str):
        self._mcp_server = mcp_server
        self._catalog_url = catalog_url

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = h.new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.submit()
        await updater.start_work()

        try:
            order_id = int(context.get_user_input().strip())
        except ValueError:
            reply = updater.new_agent_message([t.Part(text="order id must be a whole number")])
            await updater.failed(message=reply)
            return

        # --- MCP: this agent's own tool backend ---
        async with MCPClient(self._mcp_server) as mcp_client:
            items_result = await mcp_client.call_tool("get_order_items", {"order_id": order_id})
            if items_result.is_error:
                reply = updater.new_agent_message([t.Part(text=items_result.content[0].text)])
                await updater.failed(message=reply)
                return
            items = items_result.structured_content["result"]
            order_result = await mcp_client.call_tool("get_order", {"order_id": order_id})
            order = order_result.structured_content

        category = items[0]["category"]
        delivered_on = order["created_at"]

        # --- A2A: delegate to a different agent for what this one doesn't know ---
        try:
            catalog_client = await create_client(self._catalog_url)
        except AgentCardResolutionError:
            reply = updater.new_agent_message(
                [t.Part(text="couldn't confirm return policy: catalog agent is unreachable")]
            )
            await updater.failed(message=reply)
            return

        delegated_message = t.Message(
            message_id=f"delegated-for-{task.id}", role=t.Role.ROLE_USER, parts=[t.Part(text=category)],
        )
        delegated_request = t.SendMessageRequest(message=delegated_message)
        window_days = None
        async for event in catalog_client.send_message(delegated_request):
            if event.task.status.state == t.TaskState.TASK_STATE_FAILED:
                reason = event.task.status.message.parts[0].text
                reply = updater.new_agent_message([t.Part(text=f"couldn't confirm return policy: {reason}")])
                await updater.failed(message=reply)
                return
            window_days = int(event.task.status.message.parts[0].text)

        days_elapsed = (TODAY - date.fromisoformat(delivered_on)).days
        returnable = days_elapsed <= window_days
        reply_text = (
            f"order {order_id}: {category}, delivered {delivered_on}, {days_elapsed} days ago, "
            f"{window_days}-day window -> returnable={returnable}"
        )
        reply = updater.new_agent_message([t.Part(text=reply_text)])
        await updater.complete(message=reply)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def build_order_card(base_url: str) -> t.AgentCard:
    return t.AgentCard(
        name="order-agent",
        description="Answers order return eligibility by delegating to the catalog agent.",
        version="0.2.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        supported_interfaces=[t.AgentInterface(url=f"{base_url}{RPC_URL}", protocol_binding="JSONRPC")],
        capabilities=t.AgentCapabilities(streaming=False),
        skills=[
            t.AgentSkill(id="check_return_eligibility", name="Check return eligibility",
                         description="order id -> eligibility", tags=["orders"]),
        ],
    )


def build_order_app(
    base_url: str = "http://127.0.0.1:8101",
    catalog_url: str = "http://127.0.0.1:8102",
    shop_db_path: str = "shop.db",
) -> FastAPI:
    """Build the Order Agent's FastAPI app, wrapping a real thilimcp MCP server."""
    mcp_server = build_server(shop_db_path, reseed=True)
    card = build_order_card(base_url)
    handler = DefaultRequestHandler(
        agent_executor=OrderExecutor(mcp_server, catalog_url), task_store=InMemoryTaskStore(), agent_card=card,
    )
    app = FastAPI()
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=RPC_URL),
    )
    return app
