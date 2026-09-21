import re

from app.config import settings
from app.schemas import ExtractedField, LineItem, StructuredInvoice


MONEY = r"(?:[$€£₹]|USD|EUR|GBP|INR)?\s*([0-9][0-9,]*(?:\.\d{1,2})?)"
DATE = r"([0-9]{1,4}[./-][0-9]{1,2}[./-][0-9]{1,4})"


def _amount(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return round(float(value.replace(",", "")), 2)
    except ValueError:
        return None


def _match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip(" :-#")
    return None


def _field(value: str | float | None, confidence: float) -> ExtractedField:
    return ExtractedField(value=value, confidence=confidence if value is not None else 0)


def _vendor_name(lines: list[str]) -> ExtractedField:
    excluded = re.compile(
        r"^(invoice|tax invoice|receipt|bill to|ship to|date|total|www\.|https?://)",
        re.IGNORECASE,
    )
    for line in lines[:8]:
        if len(line) >= 3 and not excluded.search(line) and not re.search(r"\d{3,}", line):
            return _field(line[:120], 0.65)
    return _field(None, 0)


def _currency(text: str) -> ExtractedField:
    indicators = [
        (r"₹|\bINR\b", "INR"),
        (r"\$|\bUSD\b", "USD"),
        (r"€|\bEUR\b", "EUR"),
        (r"£|\bGBP\b", "GBP"),
    ]
    for pattern, currency in indicators:
        if re.search(pattern, text, re.IGNORECASE):
            return _field(currency, 0.95)
    return _field(None, 0)


def _extract_line_items(lines: list[str]) -> list[LineItem]:
    items: list[LineItem] = []
    pattern = re.compile(
        r"^(.+?)\s+(\d+(?:\.\d+)?)\s+(?:[$€£₹]|USD|EUR|GBP|INR)?\s*"
        r"([0-9][0-9,]*(?:\.\d{1,2})?)\s+(?:[$€£₹]|USD|EUR|GBP|INR)?\s*"
        r"([0-9][0-9,]*(?:\.\d{1,2})?)$",
        re.IGNORECASE,
    )
    excluded = re.compile(r"subtotal|tax|vat|gst|total|balance|amount due", re.IGNORECASE)

    for line in lines:
        if excluded.search(line):
            continue
        match = pattern.match(line)
        if not match:
            continue
        description, quantity, unit_price, amount = match.groups()
        if len(description.strip()) < 2:
            continue
        items.append(
            LineItem(
                description=description.strip(),
                quantity=_amount(quantity),
                unit_price=_amount(unit_price),
                amount=_amount(amount) or 0,
                confidence=0.82,
            )
        )
    return items[:100]


def extract_invoice_fields(text: str) -> StructuredInvoice:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]
    normalized = "\n".join(lines)

    invoice_number = _match(
        [
            r"invoice\s*(?:number|no\.?|#)\s*[:#-]?\s*([A-Z0-9][A-Z0-9/-]*)",
            r"invoice\s+([A-Z]{1,5}-?[0-9][A-Z0-9/-]*)",
        ],
        normalized,
    )
    invoice_date = _match(
        [rf"invoice\s*date\s*[:#-]?\s*{DATE}", rf"\bdate\s*[:#-]?\s*{DATE}"],
        normalized,
    )
    due_date = _match([rf"due\s*date\s*[:#-]?\s*{DATE}"], normalized)

    subtotal = _amount(_match([rf"\bsubtotal\s*[:#-]?\s*{MONEY}"], normalized))
    tax = _amount(
        _match(
            [rf"\b(?:tax|vat|gst)(?:\s*\([^)]*\)|\s*[0-9.]+%)?\s*[:#-]?\s*{MONEY}"],
            normalized,
        )
    )
    total = _amount(
        _match(
            [
                rf"\b(?:grand\s+total|amount\s+due|balance\s+due)\s*[:#-]?\s*{MONEY}",
                rf"\btotal\s*[:#-]?\s*{MONEY}",
            ],
            normalized,
        )
    )

    warnings: list[str] = []
    if not invoice_number:
        warnings.append("Invoice number was not detected.")
    if not invoice_date:
        warnings.append("Invoice date was not detected.")
    if total is None:
        warnings.append("Invoice total was not detected.")

    totals_valid: bool | None = None
    if subtotal is not None and tax is not None and total is not None:
        totals_valid = abs((subtotal + tax) - total) <= 0.05
        if not totals_valid:
            warnings.append("Subtotal plus tax does not match the detected total.")

    line_items = _extract_line_items(lines)
    if not line_items:
        warnings.append("No line items were confidently detected.")

    return StructuredInvoice(
        vendor_name=_vendor_name(lines),
        invoice_number=_field(invoice_number, 0.94),
        invoice_date=_field(invoice_date, 0.9),
        due_date=_field(due_date, 0.9),
        currency=_currency(normalized),
        subtotal=_field(subtotal, 0.92),
        tax=_field(tax, 0.9),
        total=_field(total, 0.94),
        line_items=line_items,
        totals_valid=totals_valid,
        warnings=warnings,
        extraction_engine="deterministic",
    )


def extract_invoice_fields_hybrid(text: str) -> StructuredInvoice:
    deterministic = extract_invoice_fields(text)
    if not settings.groq_api_key:
        return deterministic

    try:
        from app.services.llm_extractor import extract_with_groq, merge_invoice_results

        llm_result = extract_with_groq(text)
        return merge_invoice_results(deterministic, llm_result)
    except Exception:
        fallback = deterministic.model_copy(deep=True)
        fallback.warnings.append(
            "AI-assisted extraction was unavailable; deterministic extraction was used."
        )
        fallback.extraction_engine = "deterministic-fallback"
        return fallback
