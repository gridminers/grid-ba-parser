from app.extraction import extract_key_values, extract_table_blocks


SAMPLE_TEXT = """
Projekttitel    20 kV Stromversorgungsleitungen Am Hafen
beantr. Gruppe | Projekt-ID    PROJ-001429
Geschaeftsjahr  2024
Ausfuehrungszeit (von - bis)  01/04/2024   30/04/2024
Genehmigungs-Nr. 080/24
PSP-Element 2H.02.1224.104.012
Materialkosten (netto) 3.012,11 EUR
Fremdleistungen 0 EUR
Gesamtkosten 28.362,57 EUR
"""


def test_extract_known_key_values_from_irregular_text():
    fields = extract_key_values(SAMPLE_TEXT, page=1)
    by_label = {field.label: field for field in fields}

    assert by_label["PSP-Element"].value_normalized == "2H.02.1224.104.012"
    assert by_label["Projekt-ID"].value_normalized == "PROJ-001429"
    assert by_label["Genehmigungs-Nr."].value_normalized == "080/24"
    assert by_label["Geschaeftsjahr"].value_normalized == "2024"


def test_extract_cost_like_table_rows():
    tables = extract_table_blocks(SAMPLE_TEXT, page=1)
    assert len(tables) == 1
    labels = {row["label"] for row in tables[0].rows}
    assert "Materialkosten (netto)" in labels
    assert "Gesamtkosten" in labels
