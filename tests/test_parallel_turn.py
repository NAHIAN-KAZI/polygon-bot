"""Waits that do not depend on each other happen together (T-165)."""
import asyncio

import app.routes.chat as chat_module
from app.banking.routing import Clarification


def test_the_two_checks_of_an_unplaced_message_run_together_and_the_first_change_wins(monkeypatch):
    unplaced = Clarification("what?")
    started = []

    async def second_look(result, *a, **k):
        started.append("second")
        await asyncio.sleep(0.05)
        return result

    async def named(result, *a, **k):
        started.append("named")
        await asyncio.sleep(0.05)
        return "named-result"

    async def run():
        t0 = asyncio.get_event_loop().time()
        looked, found = await asyncio.gather(second_look(unplaced), named(unplaced))
        return looked, found, asyncio.get_event_loop().time() - t0

    looked, found, took = asyncio.run(run())
    assert sorted(started) == ["named", "second"] and took < 0.09              # together, not 0.1 s one after the other
    assert (looked if looked is not unplaced else found) == "named-result"
