"""The Catalog Agent — knows return-policy windows by product category. Does not know anything
about any customer's order; that's the Order Agent's job, reached over A2A, never imported.
"""
import sqlite3

import a2a.helpers as h
import a2a.types as t
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes.agent_card_routes import create_agent_card_routes
from a2a.server.routes.fastapi_routes import add_a2a_routes_to_fastapi
from a2a.server.routes.jsonrpc_routes import create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from fastapi import FastAPI

from .seed import seed_catalog

RPC_URL = "/a2a/v1"


class CatalogExecutor(AgentExecutor):
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = h.new_task_from_user_message(context.message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.submit()
        await updater.start_work()

        category = context.get_user_input().strip()
        row = self._conn.execute(
            "SELECT window_days FROM return_policy WHERE category = ?", (category,)
        ).fetchone()
        if row is None:
            reply = updater.new_agent_message([t.Part(text=f"unknown category: {category!r}")])
            await updater.failed(message=reply)
            return

        reply = updater.new_agent_message([t.Part(text=str(row["window_days"]))])
        await updater.complete(message=reply)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise NotImplementedError


def build_catalog_card(base_url: str) -> t.AgentCard:
    return t.AgentCard(
        name="catalog-agent",
        description="Knows return-policy windows by product category. Does not know any order.",
        version="0.1.0",
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        supported_interfaces=[t.AgentInterface(url=f"{base_url}{RPC_URL}", protocol_binding="JSONRPC")],
        capabilities=t.AgentCapabilities(streaming=False),
        skills=[
            t.AgentSkill(id="return_window", name="Return window", description="category -> days", tags=["policy"]),
        ],
    )


def build_catalog_app(base_url: str = "http://127.0.0.1:8102", db_path: str = "catalog.db") -> FastAPI:
    """Build the Catalog Agent's FastAPI app: a real executor behind a real card."""
    conn = seed_catalog(db_path)
    card = build_catalog_card(base_url)
    handler = DefaultRequestHandler(
        agent_executor=CatalogExecutor(conn), task_store=InMemoryTaskStore(), agent_card=card,
    )
    app = FastAPI()
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=RPC_URL),
    )
    return app
