"""Keys-free quickstart: stand up both agents and ask the real question.

Run: python examples/quickstart.py
"""
import asyncio
import threading
import time

import uvicorn

from thilia2a import ask, build_catalog_app, build_order_app, parse_returnable


def _run(app, port):
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


async def main():
    catalog_app = build_catalog_app()
    order_app = build_order_app()

    threading.Thread(target=_run, args=(catalog_app, 8102), daemon=True).start()
    threading.Thread(target=_run, args=(order_app, 8101), daemon=True).start()
    time.sleep(2)

    for order_id in ["79", "3", "not-a-number"]:
        state, text = await ask(order_id)
        print(f"order {order_id!r}: {state} -> {text}")
        if state == "TASK_STATE_COMPLETED":
            print("  returnable:", parse_returnable(text))


if __name__ == "__main__":
    asyncio.run(main())
