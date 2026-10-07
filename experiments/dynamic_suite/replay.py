"""Replay the questions that did not pass in a run_single .jsonl through routing and the
freeze grounding only (offline: saved service list, no bank, no reply writing), and print
what the bot would route to now. For iterating on prompts quickly.

  python -m experiments.dynamic_suite.replay <run.jsonl> [--statuses FAIL,CLARIFY] [--only 4.2,3.2]
"""
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path

import app.banking.taxonomy as taxonomy_module
from app.banking import ui_actions
from app.banking.routing import classify
from app.routes.chat import _ground_freeze_request, _ground_requested_action, _ground_transfer_destination
from experiments.dynamic_suite.checks import judge
from experiments.dynamic_suite.route_only import SNAPSHOT, as_result

QUESTIONS = Path(__file__).with_name("questions.json")


async def main():
    src = Path(sys.argv[1])
    arg = lambda name: set(sys.argv[sys.argv.index(name) + 1].split(",")) if name in sys.argv else set()
    statuses, only = arg("--statuses") or {"FAIL"}, arg("--only")
    cached = json.loads(SNAPSHOT.read_text())
    if not any(c['id'] == ui_actions.CATEGORY for c in cached['categories']):  # snapshot predates the registry
        cached['categories'].append(ui_actions.catalog_category())
    taxonomy_module._cache = cached
    taxonomy_module._index = taxonomy_module._build_index(cached["categories"])
    expected = json.loads(QUESTIONS.read_text())
    out = Counter()
    for line in src.read_text().splitlines():
        r = json.loads(line)
        if r["status"] not in statuses or (only and r["row"] not in only):
            continue
        want = expected[r["row"]]["expected"]
        want = tuple(want) if isinstance(want, list) else want
        routed = await classify(r["question"], [])
        routed = await _ground_freeze_request(routed, r["question"], [])
        routed = await _ground_transfer_destination(routed, r["question"])
        routed = await _ground_requested_action(routed, r["question"])
        result = as_result(routed)
        status, why = judge(want, "", result)
        out[status] += 1
        print(f"{status:8} {r['row']:8} {r['style']:9} {r['question'][:58]!r:62} -> {result.get('type')} "
              f"{result.get('category')}/{result.get('service')}", flush=True)
    print("\nnow:", dict(out))


if __name__ == "__main__":
    asyncio.run(main())
