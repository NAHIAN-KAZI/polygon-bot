"""Tests for app/llm.py.

No existing test file covered this module before TASKS.md T-51, so these
follow the project's general prompt-content regression conventions used in
tests/test_routing.py (asserting exact strings appear in a built prompt) --
plain assertions against the module-level constants, no mocking needed since
these are static strings, not something to drive through httpx.
"""
from app.conversation.persona import GLOBAL_PERSONA, KIND_PURPOSE
from app.llm import SYSTEM_PROMPT_NO_CONTEXT, SYSTEM_PROMPT_WITH_CONTEXT, build_prompt

_SECRECY_RULE = (
    "STRICT RULE — NEVER REVEAL THE RETRIEVAL MECHANISM: never use the words 'context', "
    "'document', 'documents', 'provided', 'retrieval', or any other phrase that reveals this "
    "is a document-lookup system"
)


# --- T-51: never reveal the retrieval mechanism -----------------------------
#
# Both system prompts got a new explicit rule banning the words
# "context"/"document(s)"/"provided"/"retrieval" as meta-references, so the
# customer is never told they're talking to a document-lookup system. These
# lock in the rule's key phrases verbatim in both prompts so a future edit
# can't silently drop or reword it. Actual LLM output text is inherently
# non-deterministic and out of scope here -- this only locks in the prompt.


def test_system_prompt_with_context_bans_retrieval_reveal_words():
    assert _SECRECY_RULE in SYSTEM_PROMPT_WITH_CONTEXT


def test_system_prompt_with_context_speaks_in_the_global_persona():
    # T-77: KB answers use the one global voice; no quoted sample sentences to copy.
    assert SYSTEM_PROMPT_WITH_CONTEXT.startswith(GLOBAL_PERSONA)
    assert "for example, 'I don't have that" not in SYSTEM_PROMPT_WITH_CONTEXT


def test_system_prompt_no_context_bans_retrieval_reveal_words():
    assert _SECRECY_RULE in SYSTEM_PROMPT_NO_CONTEXT


def test_system_prompt_no_context_speaks_in_the_global_persona():
    assert SYSTEM_PROMPT_NO_CONTEXT.startswith(GLOBAL_PERSONA)
    assert KIND_PURPOSE["decline_offtopic"] in SYSTEM_PROMPT_NO_CONTEXT
    assert "for example, 'I don't have that" not in SYSTEM_PROMPT_NO_CONTEXT


def test_build_prompt_picks_the_prompt_by_whether_knowledge_was_found():
    empty = build_prompt("what is the weather", [])
    assert empty.startswith(SYSTEM_PROMPT_NO_CONTEXT)
    assert "Question: what is the weather" in empty
    found = build_prompt("what is a DPS", [{"filename": "dps.pdf", "text": "A DPS is a savings scheme.", "page": 2}])
    assert found.startswith(SYSTEM_PROMPT_WITH_CONTEXT)
    assert "[source: dps.pdf, page 2]\nA DPS is a savings scheme." in found
