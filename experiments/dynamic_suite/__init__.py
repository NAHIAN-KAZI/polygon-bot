"""Dynamic live QA suite driven by planning/input/INTENT_IMPLEMENTATION_STATUS.md.

  doc_rows      parse the status doc into (intent, endpoint row, status)
  mapping       map each row to the bot's (category, service) -- reviewed JSON cache
  questions     the model writes 5 customer messages per row (cached JSON)
  run_single    send every question to the live /chat, check route + reply
  run_multi     simulated customers hold long multi-turn conversations across intents

Run inside the backend container (needs app.* and the bank's dev platform), e.g.
  docker compose run --rm --no-deps -T -v "$PWD/experiments:/app/experiments" \
    -e EVAL_USERNAME=... -e EVAL_PASSWORD=... backend python -m experiments.dynamic_suite.run_single
"""
