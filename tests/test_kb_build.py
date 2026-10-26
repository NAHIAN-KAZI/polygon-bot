"""Turning the scraped City Bank knowledge file into the Polygon one (T-116, T-117)."""
from experiments.kb_build.kb_build import Report, build, clean_page, parse_card_mapping, rename_text, split_pages

CARDS = """
| # | Card type | City Bank name (original) | Suggested Polygon name | Suggestion | City Bank page |
|---|---|---|---|---|---|
| 1 | Credit - Visa | Visa Platinum Card | Polygon Visa Platinum Card | Yes - core | `/p/visa-platinum` |
| 2 | Credit - Visa | Visa Infinite | Polygon Visa Infinite Credit Card | Yes - core | `/p-ca/visa-infinite` |
| 3 | Credit - other | CityGo | PolygonGo | Yes - core | `/p-ca/city-go` |

## 2. Other spellings to replace too

| Original name | Other spellings found on the site | Replace all with |
|---|---|---|
| Visa Infinite | City Visa Infinite Credit Card | Polygon Visa Infinite Credit Card |

## 3. Brand words
"""

FOOTER = ("Take a look at the most commonly asked questions. We are here to help\n"
          "We are here to help, anytime!\nCustomer Care\nAvailable 24 hours a day, 7 days a week\n16234\nlocally\n"
          "+88 02 8331040\nFrom overseas\nEmail Us\nAvailable 24 hours a day, 7 days a week. Usually respond in a day.\n")


def _page(body: str, source: str = "https://www.citybankplc.com/p/visa-platinum") -> str:
    return f"### Visa Platinum Card\n\n{body}\n\nSource: {source}"


def test_the_repeated_customer_care_block_is_removed_and_the_rest_kept():
    r = Report()
    out = clean_page(_page("Spend anywhere.\n" + FOOTER + "\n#### Eligibility\nAny account holder."), "Cards", r)
    assert r.footers_removed == 1
    assert "Customer Care" not in out and "From overseas" not in out
    assert "Spend anywhere." in out and "#### Eligibility\nAny account holder." in out


def test_a_cut_off_line_is_dropped_when_the_page_has_the_full_line():
    r = Report()
    body = "#### Features\nEnjoy hassle-free international ATM, POS and e-com...\n\n#### More\nEnjoy hassle-free international ATM, POS and e-commerce transactions"
    out = clean_page(_page(body), "Cards", r)
    assert r.truncated_dropped == 1 and "e-com..." not in out and "e-commerce transactions" in out


def test_a_cut_off_line_with_no_full_version_is_trimmed_to_a_whole_word_and_marked():
    r = Report()
    out = clean_page(_page("Online banking service, SMS Alert & Call Center Fa..."), "Cards", r)
    assert r.truncated_marked == 1
    assert "Online banking service, SMS Alert & Call Center …" in out and "Fa..." not in out


def test_a_product_page_without_fees_says_so_but_a_page_with_a_fee_table_does_not():
    r = Report()
    assert "does not list fees" in clean_page(_page("A card."), "Cards", r) and r.fee_notes_added == 1
    table = clean_page(_page("#### Fees and Charges\n| a | b |\n|---|---|\n| 1 | 2 |"), "Cards", Report())
    assert "does not list fees" not in table
    assert "does not list fees" not in clean_page(_page("A card."), "Insurance (bancassurance)", Report())    # no fee note for insurance
    assert "does not list fees" not in clean_page(_page("An overview.", "https://www.citybankplc.com/cards"), "Cards", Report())


def test_the_card_mapping_includes_other_spellings_and_keeps_the_bare_network_tier():
    names = parse_card_mapping(CARDS)
    assert names["Visa Platinum Card"] == "Polygon Visa Platinum Card"
    assert names["City Visa Infinite Credit Card"] == "Polygon Visa Infinite Credit Card"
    assert "Visa Infinite" not in names
    assert names["City Go"] == "PolygonGo"


def test_card_names_the_bank_and_its_sub_brands_are_renamed_without_doubling():
    names = parse_card_mapping(CARDS)
    r = Report()
    text = ("Apply for the City Bank Visa Platinum Card at any City Bank PLC branch. Use CityTouch or Citytouch, "
            "CityCorp, City Alo, City Islamic and City Brokerage Limited. A Visa Infinite holder gets lounge access. "
            "Dhaka North City Corporation, Select City/Town.")
    out = rename_text(text, names, r)
    assert "Polygon Visa Platinum Card" in out and "Polygon Bank Polygon" not in out
    assert "any Polygon Bank branch" in out
    assert "PolygonTouch or PolygonTouch" in out and "PolygonCorp" in out
    assert "Polygon Digital" in out and "Polygon Islamic" in out and "Polygon Brokerage Limited" in out
    assert "A Visa Infinite holder" in out                                     # the bare tier name stays
    assert "Dhaka North City Corporation" in out and "Select City/Town" in out   # not the bank


def test_city_banks_contact_details_become_placeholders_but_a_partners_do_not():
    out = rename_text("Call 16234 or +88 02 8331040 or +880 2 8331040, mail queries@citybankplc.com or eb@thecitybank.com, "
                      "see https://www.citybankplc.com/cards and www.citybankplc.com. Partner: travel@gmail.com.", {}, Report())
    assert out.count("[Polygon Bank hotline]") == 3 and out.count("[Polygon Bank email]") == 2
    assert out.count("[Polygon Bank website]") == 2
    assert "citybank" not in out.lower() and "travel@gmail.com" in out


def test_source_lines_keep_the_original_url():
    out = rename_text("Text about City Bank.\nSource: https://www.citybankplc.com/p/visa-platinum", {}, Report())
    assert out.endswith("Source: https://www.citybankplc.com/p/visa-platinum") and "Polygon Bank" in out


def test_garbled_characters_and_non_breaking_spaces_are_fixed_before_renaming():
    out = rename_text("City Bank’s offer ðŸ“ž call, donâ€™t wait", {}, Report())
    assert out.startswith("Polygon Bank") and "ðŸ" not in out and "â€™" not in out


def test_pages_are_split_on_the_source_line():
    parts = split_pages("## G\n\n### A\ntext\n\nSource: http://x/a\n\n### B\nmore\n\nSource: http://x/b\n")
    assert [k for k, _ in parts].count("page") == 2
    assert parts[1][1].startswith("### A") and parts[1][1].endswith("Source: http://x/a")


def test_the_build_drops_the_build_notes_and_gaps_and_writes_a_draft_header():
    source = ("# Polygon Bank knowledge base: City Bank PLC source material\n\n> note\n\n## Contents\n\n- [Cards](#cards) (1)\n\n"
              "## Cards\n\n" + _page("A card with City Bank branches.") + "\n\n## What could not be gathered\n\n- City Bank publishes fees separately.\n")
    text, report = build(source, CARDS)
    assert text.startswith("# Polygon Bank knowledge base\n\n> Draft.")
    assert "## Contents" not in text and "could not be gathered" not in text and "publishes fees separately" not in text
    assert "## Cards" in text and "Polygon Bank branches" in text
    assert report.pages == 1
