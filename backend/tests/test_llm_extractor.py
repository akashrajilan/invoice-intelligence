from app.schemas import ExtractedField, StructuredInvoice
from app.config import settings
from app.services.invoice_extractor import extract_invoice_fields_hybrid
from app.services.llm_extractor import LLMInvoiceData, LLMLineItem, _build_invoice, merge_invoice_results


def empty_field() -> ExtractedField:
    return ExtractedField(value=None, confidence=0)


def test_build_llm_invoice() -> None:
    data = LLMInvoiceData(
        vendor_name="Example Ltd",
        invoice_number="AI-42",
        invoice_date="2026-09-25",
        due_date=None,
        currency="USD",
        subtotal=100,
        tax=10,
        total=110,
        line_items=[LLMLineItem(description="Analysis", quantity=2, unit_price=50, amount=100)],
    )
    invoice = _build_invoice(data)
    assert invoice.invoice_number.value == "AI-42"
    assert invoice.totals_valid is True
    assert invoice.extraction_engine == "groq-structured-output"


def test_merge_uses_deterministic_value_when_llm_field_is_missing() -> None:
    deterministic = StructuredInvoice(
        vendor_name=ExtractedField(value="Fallback Vendor", confidence=0.65),
        invoice_number=ExtractedField(value="DET-1", confidence=0.9),
        invoice_date=empty_field(), due_date=empty_field(), currency=empty_field(),
        subtotal=empty_field(), tax=empty_field(), total=empty_field(),
    )
    llm = StructuredInvoice(
        vendor_name=empty_field(),
        invoice_number=ExtractedField(value="LLM-2", confidence=0.88),
        invoice_date=empty_field(), due_date=empty_field(), currency=empty_field(),
        subtotal=empty_field(), tax=empty_field(), total=empty_field(),
        extraction_engine="groq-structured-output",
    )
    merged = merge_invoice_results(deterministic, llm)
    assert merged.vendor_name.value == "Fallback Vendor"
    assert merged.invoice_number.value == "LLM-2"


def test_hybrid_extraction_falls_back_when_groq_fails(monkeypatch) -> None:
    monkeypatch.setattr(settings, "groq_api_key", "test-key")

    def fail_extraction(_text: str):
        raise TimeoutError("simulated timeout")

    monkeypatch.setattr("app.services.llm_extractor.extract_with_groq", fail_extraction)
    result = extract_invoice_fields_hybrid(
        "Fallback Inc\nInvoice No: F-1\nInvoice Date: 2026-09-26\nTotal: USD 25.00"
    )
    assert result.invoice_number.value == "F-1"
    assert result.extraction_engine == "deterministic-fallback"
    assert any("unavailable" in warning for warning in result.warnings)
