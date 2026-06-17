from app.extraction import validate_draft_fields
from app.models import ExtractedField


def test_validate_flags_empty_label_and_low_confidence():
    fields = [
        ExtractedField(label="", value_raw="x", page=1, confidence=0.8),
        ExtractedField(label="PSP-Element", value_raw=None, page=1, confidence=0.2),
    ]
    errors, warnings = validate_draft_fields(fields)

    assert "fields[0].label is empty" in errors
    assert any("low confidence" in warning for warning in warnings)
