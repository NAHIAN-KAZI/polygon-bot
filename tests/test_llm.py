"""Tests for app/llm.py.

No existing test file covered this module before TASKS.md T-51, so these
follow the project's general prompt-content regression conventions used in
tests/test_routing.py (asserting exact strings appear in a built prompt) --
plain assertions against the module-level constants, no mocking needed since
these are static strings, not something to drive through httpx.
"""
from app.llm import SYSTEM_PROMPT_NO_CONTEXT, SYSTEM_PROMPT_WITH_CONTEXT


# --- T-51: never reveal the retrieval mechanism -----------------------------
#
# Both system prompts got a new explicit rule banning the words
# "context"/"document(s)"/"provided"/"retrieval" as meta-references, so the
# customer is never told they're talking to a document-lookup system. These
# lock in the rule's key phrases verbatim in both prompts so a future edit
# can't silently drop or reword it. Actual LLM output text is inherently
# non-deterministic and out of scope here -- this only locks in the prompt.


def test_system_prompt_with_context_bans_retrieval_reveal_words():
    assert (
        "STRICT RULE — NEVER REVEAL THE RETRIEVAL MECHANISM: "
        "if the context below does not fully answer the question, never use the words 'context', "
        "'document', 'documents', 'provided', 'retrieval', or any other phrase that reveals this "
        "is a document-lookup system"
    ) in SYSTEM_PROMPT_WITH_CONTEXT


def test_system_prompt_with_context_gives_natural_language_example():
    assert (
        "for example, 'I don't have that "
        "information available right now' is fine; 'I don't have information in the context "
        "provided' is not"
    ) in SYSTEM_PROMPT_WITH_CONTEXT


def test_system_prompt_no_context_bans_retrieval_reveal_words():
    assert (
        "STRICT RULE — NEVER REVEAL THE RETRIEVAL MECHANISM: never use the words 'context', "
        "'document', 'documents', 'provided', 'retrieval', or any other phrase that reveals this "
        "is a document-lookup system"
    ) in SYSTEM_PROMPT_NO_CONTEXT


def test_system_prompt_no_context_gives_natural_language_example():
    assert (
        "for example, 'I don't have that "
        "information available right now' is fine; 'I don't have information in the context "
        "provided' is not"
    ) in SYSTEM_PROMPT_NO_CONTEXT
