import json

from groq import Groq
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.config import settings
from app.schemas import ExtractedField, LineItem, StructuredInvoice


class LLMLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str
    quantity: float | None
    unit_price: float | None
    amount: float


class LLMInvoiceData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    currency: str | None
    subtotal: float | None
    tax: float | None
    total: float | None
    line_items: list[LLMLineItem]


SYSTEM_PROMPT = """You extract invoice data from OCR text.
Use only information explicitly present in the supplied text.
Never calculate or invent missing values. Return null for missing scalar fields.
Keep dates in the format shown in the document. Currency must be an ISO code when identifiable.
Exclude subtotal, tax, and total rows from line_items."""


def _field(value: str | float | None) -> ExtractedField:
    return ExtractedField(value=value, confidence=0.88 if value is not None else 0)


def _build_invoice(data: LLMInvoiceData) -> StructuredInvoice:
    warnings: list[str] = []
    if data.invoice_number is None:
        warnings.append("Invoice number was not detected.")
    if data.invoice_date is None:
        warnings.append("Invoice date was not detected.")
    if data.total is None:
        warnings.append("Invoice total was not detected.")
    if not data.line_items:
        warnings.append("No line items were confidently detected.")

    totals_valid: bool | None = None
    if data.subtotal is not None and data.tax is not None and data.total is not None:
        totals_valid = abs((data.subtotal + data.tax) - data.total) <= 0.05
        if not totals_valid:
            warnings.append("Subtotal plus tax does not match the detected total.")

    return StructuredInvoice(
        vendor_name=_field(data.vendor_name),
        invoice_number=_field(data.invoice_number),
        invoice_date=_field(data.invoice_date),
        due_date=_field(data.due_date),
        currency=_field(data.currency),
        subtotal=_field(data.subtotal),
        tax=_field(data.tax),
        total=_field(data.total),
        line_items=[
            LineItem(
                description=item.description,
                quantity=item.quantity,
                unit_price=item.unit_price,
                amount=item.amount,
                confidence=0.88,
            )
            for item in data.line_items
        ],
        totals_valid=totals_valid,
        warnings=warnings,
        extraction_engine="groq-structured-output",
    )


def extract_with_groq(text: str) -> StructuredInvoice:
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    client = Groq(
        api_key=settings.groq_api_key,
        timeout=settings.groq_timeout_seconds,
    )
    response = client.chat.completions.create(
        model=settings.groq_model,
        temperature=0,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text[: settings.max_extracted_chars]},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "invoice_extraction",
                "strict": True,
                "schema": LLMInvoiceData.model_json_schema(),
            },
        },
    )
    content = response.choices[0].message.content or "{}"
    try:
        data = LLMInvoiceData.model_validate(json.loads(content))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("Groq returned an invalid invoice structure.") from exc
    return _build_invoice(data)


def merge_invoice_results(
    deterministic: StructuredInvoice,
    llm: StructuredInvoice,
) -> StructuredInvoice:
    field_names = [
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "due_date",
        "currency",
        "subtotal",
        "tax",
        "total",
    ]
    merged = llm.model_copy(deep=True)
    for name in field_names:
        if getattr(merged, name).value is None and getattr(deterministic, name).value is not None:
            setattr(merged, name, getattr(deterministic, name))
    if not merged.line_items and deterministic.line_items:
        merged.line_items = deterministic.line_items
    return merged
