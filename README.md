# thilia2a

**A small, hackable Returns Eligibility Assistant.** Two A2A agents — one that knows everything
about an order, one that knows every category's return-policy window — that answer one real
question, **"is this order still returnable?"**, by delegating to each other mid-task. Neither
agent can answer it alone, by design.

> ⚠️ Educational reference implementation, not production. Error handling, auth, and persistence
> are deliberately minimal — the point is to see every moving part of A2A, not to harden it.

## 📚 Built lesson-by-lesson in a Learn Fast course

`thilia2a` is the reference implementation for the **[Learn Fast](https://learnfast.thili.ai)
course "Build an A2A Agent."** You don't import a framework — you build both agents yourself,
from a cheap one-process shortcut to a real, delegated, honestly-failing multi-agent system.

| Lesson | You build | Files |
|---|---|---|
| 1 · The assistant doesn't exist yet | the "obviously simpler" one-process version, named as the anti-pattern it is | — (no files carried forward) |
| 2 · Agent cards | both agents' `AgentCard`s, served with no logic behind them | `catalog/agent.py`, `order/agent.py` (`build_*_card`) |
| 3 · The policy half | `CatalogExecutor`, a real executor behind the Catalog Agent's card | `catalog/agent.py`, `catalog/seed.py` |
| 4 · The order half | `OrderExecutor` wrapping `thilimcp`'s exact MCP server | `order/agent.py` |
| 5 · The task lifecycle | `return_immediately=True` + polling `get_task()` | — (same executors, no new files) |
| 6 · The actual answer | `OrderExecutor` becomes an A2A client of the Catalog Agent, mid-task | `order/agent.py` |
| 7 · Honest failure | three failure shapes, two of them fixed with targeted `except` clauses | `order/agent.py` |
| 8 · Proof it works | a ~20-case grading run, scored against independently-computed verdicts | `tests/conformance.py` |

Every lesson's agents are the same `build_catalog_app()` / `build_order_app()` — the executor
behind each card gets real logic added to it; neither function is rewritten from scratch.

## Quickstart (no API key)

```bash
pip install -e ".[dev]"
python examples/quickstart.py
pytest tests/conformance.py -q
```

```python
import asyncio
from thilia2a import ask, build_catalog_app, build_order_app, parse_returnable
import threading, time, uvicorn

async def main():
    threading.Thread(target=lambda: uvicorn.run(build_catalog_app(), port=8102, log_level="warning"), daemon=True).start()
    threading.Thread(target=lambda: uvicorn.run(build_order_app(), port=8101, log_level="warning"), daemon=True).start()
    time.sleep(2)
    state, text = await ask("79")
    print(state, text, parse_returnable(text))

asyncio.run(main())
```

## Why two agents, not one function

The cheap version — both pieces of logic, one process, one import — works perfectly and is the
wrong answer the moment the order logic and the policy logic are owned, deployed, or trusted
separately. See lesson 1: it's the exact "giant agent" anti-pattern drawn out explicitly, not a
hypothetical.

## Why `OrderExecutor` speaks two protocols

MCP reaches `order/agent.py`'s own tool backend — the identical server `lfmcpserver`'s course
built, unmodified except for one new tool (`get_order_items`, added here because this agent
genuinely needs the order-to-category link that course's own lessons never did). A2A reaches the
Catalog Agent, a different agent this one has never imported. Same `execute()`, two layers, two
different jobs. See lesson 4 and lesson 6.

## Why two failure shapes needed fixing, and one didn't

A deliberate `TaskUpdater.failed(...)` call was already honest from lesson 3 onward — a `Task`
with `state=FAILED` the caller can check, no exception. An unhandled `ValueError` on malformed
input, and an unhandled `AgentCardResolutionError` when the Catalog Agent is unreachable, both
raised the *same* generic `InternalError` to the caller — indistinguishable crash shapes for two
completely different causes. `order/agent.py`'s `OrderExecutor` catches both by name now and
reports each honestly. See lesson 7.

## License

MIT © 2026 thili.ai
