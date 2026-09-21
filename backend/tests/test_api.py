import os
import tempfile
from pathlib import Path

TEST_DATABASE = Path(tempfile.gettempdir()) / "invoice_intelligence_tests.db"
if TEST_DATABASE.exists():
    TEST_DATABASE.unlink()
os.environ["DATABASE_PATH"] = str(TEST_DATABASE)

import fitz
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def make_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), text)
    content = document.tobytes()
    document.close()
    return content


def test_health_check() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["database"] == "available"
    assert isinstance(body["ocr_available"], bool)
    assert isinstance(body["llm_enabled"], bool)


def test_upload_pdf() -> None:
    pdf = make_pdf(
        "Acme Technologies\nInvoice No: INV-1001\nInvoice Date: 2026-09-21\n"
        "Due Date: 2026-10-05\nConsulting 2 50.00 100.00\n"
        "Subtotal: USD 100.00\nTax: USD 25.00\nTotal: USD 125.00"
    )
    response = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("invoice.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["filename"] == "invoice.pdf"
    assert body["status"] == "processed"
    assert body["document_id"]
    assert body["page_count"] == 1
    assert body["extraction_method"] == "embedded_text"
    assert "INV-1001" in body["raw_text"]
    assert body["invoice"]["invoice_number"]["value"] == "INV-1001"
    assert body["invoice"]["currency"]["value"] == "USD"
    assert body["invoice"]["total"]["value"] == 125.0
    assert body["invoice"]["totals_valid"] is True
    assert body["invoice"]["extraction_engine"] == "deterministic"


def test_total_mismatch_warning() -> None:
    pdf = make_pdf(
        "Sample Vendor\nInvoice No: X-44\nInvoice Date: 2026-09-21\n"
        "Subtotal: 100.00\nTax: 10.00\nTotal: 150.00"
    )
    response = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("invoice.pdf", pdf, "application/pdf")},
    )
    assert response.status_code == 200
    invoice = response.json()["invoice"]
    assert invoice["totals_valid"] is False
    assert any("does not match" in warning for warning in invoice["warnings"])


def test_duplicate_invoice_detection() -> None:
    pdf = make_pdf(
        "Duplicate Test Company\nInvoice No: DUP-9001\nInvoice Date: 2026-09-22\n"
        "Total: USD 20.00"
    )
    first = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("original.pdf", pdf, "application/pdf")},
    )
    second = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("copy.pdf", pdf, "application/pdf")},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["duplicate"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["duplicate_of"] == first.json()["document_id"]


def test_invoice_history() -> None:
    response = client.get("/api/v1/invoices?limit=10")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] >= 1
    assert len(body["items"]) >= 1
    assert "document_id" in body["items"][0]


def test_invoice_detail_and_exports() -> None:
    pdf = make_pdf(
        "Export Vendor\nInvoice No: EXP-101\nInvoice Date: 2026-09-23\n"
        "Service 1 75.00 75.00\nSubtotal: USD 75.00\nTax: USD 0.00\nTotal: USD 75.00"
    )
    upload = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("export.pdf", pdf, "application/pdf")},
    )
    document_id = upload.json()["document_id"]

    detail = client.get(f"/api/v1/invoices/{document_id}")
    assert detail.status_code == 200
    assert detail.json()["invoice"]["invoice_number"]["value"] == "EXP-101"

    json_export = client.get(f"/api/v1/invoices/{document_id}/export?format=json")
    assert json_export.status_code == 200
    assert json_export.headers["content-type"].startswith("application/json")
    assert "attachment" in json_export.headers["content-disposition"]

    csv_export = client.get(f"/api/v1/invoices/{document_id}/export?format=csv")
    assert csv_export.status_code == 200
    assert csv_export.headers["content-type"].startswith("text/csv")
    assert "invoice_number,EXP-101" in csv_export.text


def test_delete_invoice() -> None:
    pdf = make_pdf("Delete Vendor\nInvoice No: DEL-1\nInvoice Date: 2026-09-24\nTotal: 10.00")
    upload = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("delete.pdf", pdf, "application/pdf")},
    )
    document_id = upload.json()["document_id"]

    deleted = client.delete(f"/api/v1/invoices/{document_id}")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] is True
    assert client.get(f"/api/v1/invoices/{document_id}").status_code == 404


def test_reject_unsupported_file() -> None:
    response = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("invoice.txt", b"not an invoice", "text/plain")},
    )
    assert response.status_code == 415


def test_reject_empty_file() -> None:
    response = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("invoice.pdf", b"", "application/pdf")},
    )
    assert response.status_code == 400


def test_reject_damaged_pdf() -> None:
    response = client.post(
        "/api/v1/invoices/upload",
        files={"file": ("invoice.pdf", b"not a pdf", "application/pdf")},
    )
    assert response.status_code == 422
