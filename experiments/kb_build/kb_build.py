"""Turns the scraped City Bank knowledge file into the Polygon one (T-116, T-117).

    python -m experiments.kb_build.kb_build \
        --source planning/knowledge_base/POLYGON_BANK_KNOWLEDGE_BASE.md \
        --cards planning/knowledge_base/POLYGON_BANK_CARD_NAMES.md \
        --out planning/knowledge_base/POLYGON_BANK_KNOWLEDGE_BASE_POLYGON.md

Steps, in order, on every page (a `###` section ending in a `Source:` line):
  clean   drop the website footer / customer-care block repeated on many pages, remove a cut-off "..." line
          when the page also has the full version (otherwise mark it), say where a product page has no fee table
  rename  City Bank's card names -> the Polygon names in the card mapping file, then the bank and its sub-brands,
          and City Bank's own hotline, email and website -> placeholders (never another bank's contact details)
Only names and contact details change: fees, rates, limits, rules, offers and partners stay City Bank's, and the
file's header says so. `Source:` lines keep the original City Bank URL (provenance, not shown to customers).
"""
import argparse
import re
from dataclasses import dataclass, field

SOURCE = re.compile(r"^Source:\s*\S+\s*$")

# The customer-care block the City Bank site repeats at the foot of many product pages.
_FOOTER = re.compile(
    r"(?:^Take a look at the most commonly asked questions\.[^\n]*\n)?"
    r"^We are here to help, anytime!\n"
    r"Customer Care\n"
    r"Available 24 hours a day, 7 days a week\n"
    r"[^\n]*\n"                      # the hotline number
    r"locally\n"
    r"[^\n]*\n"                      # the local number
    r"From overseas\n"
    r"Email Us\n"
    r"[^\n]*\n?",                    # "Available 24 hours a day..., usually respond in a day."
    re.MULTILINE)

# The bank and its sub-brands. Order matters: the specific names come before the general "City <Word>" rule.
# `City Corporation` / `City Council` are real city bodies, not the bank, and are left alone.
GENERIC_RENAMES = [
    (re.compile(r"\bCity Bank PLC\b"), "Polygon Bank"),
    (re.compile(r"\bCity Banks?\b"), "Polygon Bank"),
    (re.compile(r"\bAt City(?=[,.])"), "At Polygon Bank"),
    (re.compile(r"\bBank with City\b"), "Bank with Polygon Bank"),
    (re.compile(r"\bCity ?[Mm]ax[xX]\b"), "Polygon Max"),
    (re.compile(r"\bCitygem\b"), "PolygonGem"),
    (re.compile(r"\bCity Alo\b"), "Polygon Digital"),
    (re.compile(r"\bCity Islamic\b"), "Polygon Islamic"),
    (re.compile(r"\bCity ?[Tt]ouch\b"), "PolygonTouch"),
    (re.compile(r"\bCity ?[Cc]or[o]?p\b"), "PolygonCorp"),
    (re.compile(r"\bCityGo\b"), "PolygonGo"),
    (re.compile(r"\bCity AI\b"), "Polygon AI"),
    (re.compile(r"\bCitypay\b"), "PolygonPay"),
    (re.compile(r"\bCity ?(IMPEX|Impex)\b"), r"Polygon \1"),
    (re.compile(r"\bCity (?!Corporation\b|Council\b)(?=[A-Z])"), "Polygon "),
    (re.compile(r"\bCity([A-Z][a-z]+)\b"), r"Polygon\1"),
]
# City Bank's own contact details: replaced, never kept under another bank's name.
CONTACT_RENAMES = [
    (re.compile(r"[\w.+-]+@(?:the)?citybankplc\.com|[\w.+-]+@thecitybank\.com", re.I), "[Polygon Bank email]"),
    (re.compile(r"https?://(?:[\w-]+\.)*(?:citybankplc|thecitybank)\.com[^\s)\]>\"']*", re.I), "[Polygon Bank website]"),
    (re.compile(r"\b(?:[\w-]+\.)*(?:citybankplc|thecitybank)\.com(?:/[^\s)\]>\"']*)?", re.I), "[Polygon Bank website]"),
    (re.compile(r"\+?88[\s-]*0?9[\s-]*611316234\b"), "[Polygon Bank hotline]"),
    (re.compile(r"\+?88[\s-]*0?[\s-]*2[\s-]*8331040\b"), "[Polygon Bank hotline]"),
    (re.compile(r"(?<!\d)16234(?!\d)"), "[Polygon Bank hotline]"),
]
# Characters the site's text came through the scraper wrongly encoded as (an emoji and curly quotes).
MOJIBAKE = [(re.compile(r"ðŸ[^\s]{0,3}\s*"), ""), ("â€™", "’"), ("â€˜", "‘"), ("â€œ", "“"), ("â€\x9d", "”"), ("â€“", "–"), ("â€‘", "-"),
            ("â€”", "—"), ("Â ", " "), ("Â", "")]
FEE_HEADING = re.compile(r"^#{1,6}\s+.*(fee|charge)", re.I | re.M)
FEE_NOTE = ("#### Fees and charges\n"
            "This page does not list fees for this product; the bank's schedule of charges applies.")
FEE_GROUPS = ("Deposit accounts", "Cards", "Loans and finance", "Digital banking and apps", "Business banking services")
CUT_OFF = re.compile(r"(\.\.\.|…)\s*$")


@dataclass
class Report:
    footers_removed: int = 0
    truncated_dropped: int = 0
    truncated_marked: int = 0
    fee_notes_added: int = 0
    contacts_replaced: int = 0
    names_replaced: int = 0
    pages: int = 0
    notes: list[str] = field(default_factory=list)


def split_pages(text: str) -> list[tuple[str, str]]:
    """(kind, text) parts in order: 'page' = a `###` section up to and including its Source line, 'other' = the rest."""
    parts: list[tuple[str, str]] = []
    lines = text.split("\n")
    buf: list[str] = []
    in_page = False
    for line in lines:
        if line.startswith("### ") and not in_page:
            if buf:
                parts.append(("other", "\n".join(buf)))
            buf, in_page = [line], True
        elif line.startswith("## ") and in_page:
            parts.append(("page", "\n".join(buf)))      # a page that never got a Source line: keep it whole
            buf, in_page = [line], False
        elif line.startswith("### ") and in_page:
            parts.append(("page", "\n".join(buf)))
            buf = [line]
        else:
            buf.append(line)
            if in_page and SOURCE.match(line):
                parts.append(("page", "\n".join(buf)))
                buf, in_page = [], False
    if buf:
        parts.append(("page" if in_page else "other", "\n".join(buf)))
    return parts


def clean_page(page: str, group: str | None, report: Report) -> str:
    lines_before = page
    page, n = _FOOTER.subn("", page)
    report.footers_removed += n
    lines = page.split("\n")
    full = [ln for ln in lines if not CUT_OFF.search(ln)]
    kept: list[str] = []
    for ln in lines:
        if CUT_OFF.search(ln) and not ln.startswith(("|", "#")):
            stem = CUT_OFF.sub("", ln).rstrip()
            probe = stem[:40]
            if probe and any(o.startswith(probe) and len(o) > len(stem) for o in full):
                report.truncated_dropped += 1
                continue
            cut = stem.rsplit(" ", 1)[0] if " " in stem else stem     # drop the half-word the site cut through
            kept.append(cut + " …")
            report.truncated_marked += 1
        else:
            kept.append(ln)
    page = "\n".join(kept)
    body, _, source = page.rpartition("\nSource:")
    is_product = bool(re.search(r"/p(-ca)?/", source))
    if is_product and group in FEE_GROUPS and not re.search(r"^\|---", body, re.M) and not FEE_HEADING.search(body):
        page = body.rstrip() + "\n\n" + FEE_NOTE + "\n\nSource:" + source
        report.fee_notes_added += 1
    return page if page != lines_before else lines_before


def parse_card_mapping(card_md: str) -> dict[str, str]:
    """City Bank card name (and every other spelling it has) -> Polygon name, from the card mapping file."""
    pairs: dict[str, str] = {}
    for _n, _t, original, polygon in re.findall(
            r"^\| (\d+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| [^|]+ \| `[^`]+` \|$", card_md, re.M):
        if polygon.strip():
            pairs[original.strip()] = polygon.strip()
    section = card_md.split("## 2. Other spellings")[1].split("## 3.")[0] if "## 2. Other spellings" in card_md else ""
    for original, others, polygon in re.findall(r"^\| ([^|]+) \| ([^|]+) \| ([^|]+) \|$", section, re.M):
        if original.startswith(("Original", "---")):
            continue
        for variant in others.split(";"):
            variant = re.sub(r"\s*\(fees page\)", "", variant).strip()
            if variant and variant not in ("SME Card", "Visa Platinum", "City Go"):
                pairs[variant] = polygon.strip()
    pairs["City Go"] = "PolygonGo"
    pairs.pop("Visa Infinite", None)      # the bare network tier name stays as it is
    return pairs


def rename_text(text: str, card_names: dict[str, str], report: Report) -> str:
    held: list[str] = []

    def hold(replacement: str) -> str:
        held.append(replacement)
        return f"\x00{len(held) - 1}\x00"

    out: list[str] = []
    for line in text.split("\n"):
        if SOURCE.match(line):
            out.append(line)
            continue
        line = line.replace("\xa0", " ").replace("\u2009", " ").replace("\u202f", " ")
        for bad, good in MOJIBAKE:
            line = bad.sub(good, line) if hasattr(bad, "sub") else line.replace(bad, good)
        for pattern, replacement in CONTACT_RENAMES:
            line, n = pattern.subn(lambda m, r=replacement: hold(r), line)
            report.contacts_replaced += n
        for old in sorted(card_names, key=len, reverse=True):
            line, n = re.subn(r"(?<![\w])(?:City Bank\s+)?" + re.escape(old) + r"(?![\w])",
                              lambda m, r=card_names[old]: hold(r), line)
            report.names_replaced += n
        for pattern, replacement in GENERIC_RENAMES:
            line, n = pattern.subn(lambda m, r=replacement: hold(m.expand(r)), line)
            report.names_replaced += n
        out.append(line)
    return re.sub(r"\x00(\d+)\x00", lambda m: held[int(m.group(1))], "\n".join(out))


HEADER = """# Polygon Bank knowledge base

> Draft. Names are Polygon's, but everything else was written for another bank (City Bank PLC) and has not been
> rewritten: every fee, rate, limit, eligibility rule, offer, partner (airlines, lounges, hotels, merchants) and the
> scheduled charges is that bank's. City Bank's hotline, email and website were replaced by placeholders in square
> brackets. Replace all of it with Polygon's own before customers rely on it. `Source:` lines point to the original page.
"""


def build(source_md: str, card_md: str) -> tuple[str, Report]:
    report = Report()
    card_names = parse_card_mapping(card_md)
    group = None
    out: list[str] = []
    for kind, part in split_pages(source_md):
        if kind == "page":
            report.pages += 1
            part = clean_page(part, group, report)
        else:
            for line in part.split("\n"):
                if line.startswith("## "):
                    group = line[3:].strip()
        out.append(part)
    text = "\n".join(out)
    # Build notes, not knowledge: the title block, the contents list and the "could not be gathered" appendix.
    text = re.sub(r"\A# .*?(?=^## )", "", text, count=1, flags=re.S | re.M)
    text = re.sub(r"^## Contents\n.*?(?=^## )", "", text, count=1, flags=re.S | re.M)
    text = re.sub(r"^## What could not be gathered\n.*\Z", "", text, count=1, flags=re.S | re.M)
    text = rename_text(text, card_names, report)
    return HEADER + "\n" + text.strip("\n") + "\n", report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--cards", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    text, report = build(open(args.source, encoding="utf-8").read(), open(args.cards, encoding="utf-8").read())
    open(args.out, "w", encoding="utf-8").write(text)
    print(f"{report.pages} pages | footers removed {report.footers_removed} | cut-off lines dropped "
          f"{report.truncated_dropped}, marked {report.truncated_marked} | fee notes added {report.fee_notes_added} | "
          f"contact details replaced {report.contacts_replaced} | names replaced {report.names_replaced}")


if __name__ == "__main__":
    main()
