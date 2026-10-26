"""Markdown-aware chunking (T-111): every chunk says where it is, tables keep their header, Source lines become metadata."""
from app.chunking import MIN_CHUNK_CHARS, chunk_document

PAGES = """# Bank knowledge base

## Cards

### Visa Debit Card

A debit card for everyday spending, accepted at shops and ATMs around the world.

#### Fees and Charges
| Particulars | Amount |
|---|---|
| Annual fee | BDT 700 |
| Card replacement | BDT 400 |

#### Eligibility
Any account holder.

Source: https://example.test/p/visa-debit-card

### Home Loan

Borrow up to 70% of a property's value.

Source: https://example.test/p/home-loan
"""


def _chunks(text=PAGES, name="kb.md"):
    return chunk_document(name, text.encode())


def test_every_chunk_names_its_place_and_the_document_title_is_left_out():
    chunks = _chunks()
    assert chunks and all(c.text.startswith("[") for c in chunks)
    fees = next(c for c in chunks if c.section == "Fees and Charges")
    assert fees.text.startswith("[Cards > Visa Debit Card > Fees and Charges]\n")
    assert "Bank knowledge base" not in fees.text
    assert fees.heading_path == ["Bank knowledge base", "Cards", "Visa Debit Card", "Fees and Charges"]


def test_product_group_and_source_url_come_from_the_headings_and_the_source_line():
    chunks = _chunks()
    fees = next(c for c in chunks if c.section == "Fees and Charges")
    assert (fees.product, fees.group, fees.source_url) == ("Visa Debit Card", "Cards", "https://example.test/p/visa-debit-card")
    loan = next(c for c in chunks if c.product == "Home Loan")
    assert loan.source_url == "https://example.test/p/home-loan"
    assert not any("Source:" in c.text for c in chunks)          # metadata, not something to embed


def test_a_table_stays_with_its_header_row():
    fees = next(c for c in _chunks() if c.section == "Fees and Charges")
    assert "| Particulars | Amount |\n|---|---|\n| Annual fee | BDT 700 |" in fees.text


def test_a_long_table_is_cut_into_groups_that_each_repeat_the_header():
    rows = "\n".join(f"| Fee number {i} | BDT {i * 10} |" for i in range(60))
    chunks = _chunks(f"## Fees\n\n### Card\n\n#### Table\n| Particulars | Amount |\n|---|---|\n{rows}\n\nSource: http://x\n")
    table_chunks = [c for c in chunks if "| Fee number" in c.text]
    assert len(table_chunks) > 1
    assert all("| Particulars | Amount |\n|---|---|" in c.text for c in table_chunks)
    assert sum(c.text.count("| Fee number") for c in table_chunks) == 60      # no row lost or repeated


def test_a_tiny_section_is_folded_into_its_neighbour_in_the_same_block():
    chunks = _chunks("## G\n\n### P\n\nFirst sentence of the page.\n\nTiny.\n\nSource: http://x\n")
    assert len(chunks) == 1 and "Tiny." in chunks[0].text


def test_no_chunk_is_a_bare_heading():
    assert all(len(c.text.split("\n", 1)[-1].strip()) > 0 for c in _chunks())
    assert MIN_CHUNK_CHARS == 80


def test_a_file_without_page_headings_keeps_its_source_line_as_text():
    chunks = _chunks("## Fees\n\nSome text about fees.\n\nSource: http://x\n")
    assert any("Source: http://x" in c.text for c in chunks)
    assert all(c.product is None and c.source_url is None for c in chunks)


def test_a_hash_inside_a_code_block_is_not_a_heading():
    chunks = _chunks("## Guide\n\n### Steps\n\nRun this:\n\n```\n# not a heading\nls\n```\n\nSource: http://x\n")
    assert [c.section for c in chunks] == ["Steps"]
    assert "# not a heading" in chunks[0].text


def test_plain_text_is_chunked_as_before_with_no_markdown_fields():
    chunks = chunk_document("notes.txt", b"A plain note about refunds. " * 40)
    assert len(chunks) > 1
    assert all(c.section is None and c.product is None and c.heading_path == [] for c in chunks)
    assert chunks[0].chunk_index == 0 and chunks[1].chunk_index == 1


def test_the_real_knowledge_file_chunks_cleanly():
    import pathlib
    path = pathlib.Path(__file__).resolve().parent.parent / "planning" / "knowledge_base" / "POLYGON_BANK_KNOWLEDGE_BASE.md"
    if not path.exists():
        return
    chunks = chunk_document(path.name, path.read_bytes())
    assert len(chunks) > 1000
    assert all(c.text.startswith("[") for c in chunks)
    assert sum(len(c.text) > 800 for c in chunks) <= len(chunks) * 0.01      # almost nothing near the model's limit
    assert sum(bool(c.product) for c in chunks) > len(chunks) * 0.9
    assert not any("Source: https://www.citybankplc.com" in c.text for c in chunks)
