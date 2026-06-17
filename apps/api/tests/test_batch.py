from app.batch import export_mock_db_payload, mock_db_payload
from app.models import DocumentDraft, DocumentRecord, ExtractedField
from app.storage import LocalStore


def test_mock_db_payload_uses_label_and_normalized_values():
    record = DocumentRecord(filename="test.pdf", sha256="abc", source_path="/tmp/test.pdf")
    draft = DocumentDraft(
        document_id=record.id,
        fields=[
            ExtractedField(
                label="PSP-Element",
                value_raw="2H.02.1224.104.012",
                value_normalized="2H.02.1224.104.012",
                page=1,
                confidence=0.9,
            )
        ],
    )

    payload = mock_db_payload(record, draft)

    assert payload.document_id == record.id
    assert payload.fields[0].label == "PSP-Element"
    assert payload.fields[0].sanitized_value == "2H.02.1224.104.012"
    assert payload.fields[0].value_normalized == "2H.02.1224.104.012"


def test_export_mock_db_payload_writes_json(tmp_path):
    store = LocalStore(tmp_path)
    record = DocumentRecord(filename="test.pdf", sha256="abc", source_path="/tmp/test.pdf")
    store.save_document(record)
    store.save_draft(
        DocumentDraft(
            document_id=record.id,
            fields=[
                ExtractedField(
                    label="Gesamtkosten",
                    value_raw="1.234,00 EUR",
                    value_normalized="1234.00",
                    page=1,
                    confidence=0.8,
                )
            ],
        )
    )

    result = export_mock_db_payload(store=store, document_id=record.id)

    assert result.status == "exported"
    assert result.fields == 1
    assert result.export_path is not None
    assert "Gesamtkosten" in tmp_path.joinpath("mock_db_exports", f"{record.id}.json").read_text(
        encoding="utf-8"
    )
