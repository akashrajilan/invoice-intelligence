import csv
import json
from io import StringIO

from app.schemas import InvoiceDetail


def invoice_to_json(detail: InvoiceDetail) -> str:
    return json.dumps(detail.model_dump(), indent=2, ensure_ascii=False)


def invoice_to_csv(detail: InvoiceDetail) -> str:
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["field", "value", "confidence"])

    invoice = detail.invoice
    fields = [
        ("vendor_name", invoice.vendor_name),
        ("invoice_number", invoice.invoice_number),
        ("invoice_date", invoice.invoice_date),
        ("due_date", invoice.due_date),
        ("currency", invoice.currency),
        ("subtotal", invoice.subtotal),
        ("tax", invoice.tax),
        ("total", invoice.total),
    ]
    for name, field in fields:
        writer.writerow([name, field.value if field.value is not None else "", field.confidence])

    writer.writerow([])
    writer.writerow(["line_item_description", "quantity", "unit_price", "amount", "confidence"])
    for item in invoice.line_items:
        writer.writerow(
            [item.description, item.quantity or "", item.unit_price or "", item.amount, item.confidence]
        )
    return output.getvalue()
