"""Parse INTENT_IMPLEMENTATION_STATUS.md into one record per endpoint row."""
import re
from dataclasses import dataclass
from pathlib import Path

DOC = Path(__file__).resolve().parents[2] / "planning" / "input" / "INTENT_IMPLEMENTATION_STATUS.md"
_SECTION_RE = re.compile(r"^## ([A-Z_]+)\b")
_REF_RE = re.compile(r"`([a-z_]+)`\s*/\s*`([a-z_]+)`")


@dataclass
class DocRow:
    intent: str
    name: str
    status: str
    ref: tuple[str, str] | None   # (category, service) when the doc names it

    @property
    def key(self) -> str:
        return f"{self.intent}|{self.name}"

    @property
    def skipped(self) -> bool:
        return self.status.lstrip().startswith("❌")


def parse(path: Path = DOC) -> list[DocRow]:
    rows, intent = [], None
    for line in path.read_text().splitlines():
        section = _SECTION_RE.match(line)
        if section:
            intent = section.group(1)
            continue
        if not intent or not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2 or cells[0] in ("#", "Endpoint") or set(cells[0]) <= {"-", " "}:
            continue
        name, status = cells
        ref = _REF_RE.search(status)
        rows.append(DocRow(intent, name, status, (ref.group(1), ref.group(2)) if ref else None))
    return rows


if __name__ == "__main__":
    for row in parse():
        print(f"{row.intent:22} {'SKIP' if row.skipped else '    '} {row.name:55} {row.ref or ''}")
