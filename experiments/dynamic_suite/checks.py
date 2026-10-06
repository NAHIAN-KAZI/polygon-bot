"""Automatic checks on a bot reply, shared by the single-turn and multi-turn runs.
Test-time only: these judge the bot's output, they are not bot logic. Anything they
flag is read by a human; they never mark a reply good, only suspicious."""
import re

from experiments.dynamic_suite.expect import KB, NOT_IN_CHAT

LLM_DOWN = "I'm having trouble right now"
_SOURCE_LEAK = re.compile(r"\b(api|endpoint|database|json|fetched|according to the (data|facts|records)|the facts|"
                          r"the data (shows|says)|our records show|system (shows|says|returned))\b", re.I)
_CLAIMS_DONE = re.compile(r"\b(has been|have been|is now|was|were) (changed|updated|frozen|blocked|cancelled|"
                          r"submitted|sent|transferred|completed|activated)\b|\bsuccessfully\b|\ball done\b", re.I)
_FOREIGN = re.compile(r"[$€£₹]|\b(USD|EUR)\b")
_MARKDOWN = re.compile(r"(?<!\*)\*\*(?![*\d])|^\s*[-*#] ", re.M)
def _service_ids() -> re.Pattern | None:
    """Ids the bank's service catalog uses (account_info, frezz_unfrezz...) must never be
    shown to a customer. Read from the saved catalog snapshot, when there is one."""
    import json
    from pathlib import Path
    snap = Path(__file__).resolve().parents[1] / "results" / "taxonomy_snapshot.json"
    if not snap.exists():
        return None
    ids = set()
    for cat in json.loads(snap.read_text()).get("categories", []):
        ids.add(cat["id"])
        ids.update(svc["id"] for svc in cat.get("services", []))
    ids = {i for i in ids if "_" in i}
    return re.compile(r"\b(" + "|".join(sorted(map(re.escape, ids))) + r")\b") if ids else None


_INTERNAL_ID = _service_ids()
_UNMASKED = re.compile(r"(?<![\d•*])\d{9,}(?!\d)")


def reply_flags(text: str, result_type: str) -> list[str]:
    flags = []
    if not text.strip():
        flags.append("empty_reply")
    if LLM_DOWN in text:
        flags.append("llm_down")
    if _FOREIGN.search(text):
        flags.append("foreign_currency")
    if _MARKDOWN.search(text):
        flags.append("markdown")
    if _SOURCE_LEAK.search(text):
        flags.append("mentions_source")
    if _UNMASKED.search(text):
        flags.append("long_number")
    if len(text) > 900:
        flags.append("too_long")
    if _INTERNAL_ID and _INTERNAL_ID.search(text):
        flags.append("internal_id_in_text")
    return flags


def claims_done(text: str) -> bool:
    return bool(_CLAIMS_DONE.search(text))


_NOT_OFFERED_OK = ("UNKNOWN_SERVICE", "CLARIFICATION_REQUIRED", "KB_ANSWER")


def judge(expected, text: str, result: dict) -> tuple[str, str]:
    """(PASS|CLARIFY|UNAVAILABLE|FAIL|ERROR, why)"""
    rtype, cat, svc, sub = result.get("type"), result.get("category"), result.get("service"), result.get("subservice")
    if rtype == "AUTH_REQUIRED":
        return "ERROR", "auth_required (token)"
    if rtype == "TRANSPORT_ERROR":
        return "ERROR", result.get("error", "request failed")
    if expected == NOT_IN_CHAT:
        if rtype in _NOT_OFFERED_OK:
            return ("FAIL", "claims it was done") if claims_done(text) else ("PASS", rtype)
        return "FAIL", f"routed to {cat}/{svc} ({rtype}) but chat doesn't offer this"
    if expected == KB:
        return ("PASS", rtype) if rtype in ("KB_ANSWER", "CLARIFICATION_REQUIRED") else ("FAIL", f"{rtype} {cat}/{svc}")
    want_cat, want_svc, *want_sub = expected
    if (cat, svc) == (want_cat, want_svc):
        if want_sub and sub and sub != want_sub[0]:
            return "FAIL", f"right service, wrong subservice {sub} (wanted {want_sub[0]})"
        return ("UNAVAILABLE", "bank call failed") if rtype == "SERVICE_UNAVAILABLE" else ("PASS", rtype)
    if rtype == "CLARIFICATION_REQUIRED":
        return "CLARIFY", "asked a question instead of routing"
    return "FAIL", f"{rtype} {cat}/{svc} (wanted {want_cat}/{want_svc})"
