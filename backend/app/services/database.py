import json
import sqlite3
from pathlib import Path

from app.config import settings
from app.schemas import InvoiceDetail, InvoiceHistoryItem, StructuredInvoice


class InvoiceDatabase:
    def __init__(self, database_path: str) -> None:
        self.database_path = database_path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL UNIQUE,
                    vendor_name TEXT,
                    invoice_number TEXT,
                    total REAL,
                    currency TEXT,
                    extraction_method TEXT NOT NULL,
                    structured_json TEXT NOT NULL,
                    raw_text TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_invoices_created_at ON invoices(created_at DESC)"
            )

    def find_duplicate(self, file_hash: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT document_id FROM invoices WHERE file_hash = ?",
                (file_hash,),
            ).fetchone()
        return row["document_id"] if row else None

    def save_invoice(
        self,
        *,
        document_id: str,
        filename: str,
        file_hash: str,
        extraction_method: str,
        invoice: StructuredInvoice,
        raw_text: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO invoices (
                    document_id, filename, file_hash, vendor_name, invoice_number,
                    total, currency, extraction_method, structured_json, raw_text
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    filename,
                    file_hash,
                    invoice.vendor_name.value,
                    invoice.invoice_number.value,
                    invoice.total.value,
                    invoice.currency.value,
                    extraction_method,
                    json.dumps(invoice.model_dump()),
                    raw_text,
                ),
            )

    def list_invoices(self, limit: int = 50) -> list[InvoiceHistoryItem]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT document_id, filename, vendor_name, invoice_number, total,
                       currency, extraction_method, created_at
                FROM invoices
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [InvoiceHistoryItem(**dict(row)) for row in rows]

    def count_invoices(self) -> int:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM invoices").fetchone()
        return int(row["count"])

    def get_invoice(self, document_id: str) -> InvoiceDetail | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT document_id, filename, extraction_method, structured_json,
                       raw_text, created_at
                FROM invoices
                WHERE document_id = ?
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            return None
        return InvoiceDetail(
            document_id=row["document_id"],
            filename=row["filename"],
            extraction_method=row["extraction_method"],
            created_at=row["created_at"],
            invoice=StructuredInvoice.model_validate(json.loads(row["structured_json"])),
            raw_text=row["raw_text"],
        )

    def delete_invoice(self, document_id: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                "DELETE FROM invoices WHERE document_id = ?",
                (document_id,),
            )
        return cursor.rowcount > 0


database = InvoiceDatabase(settings.database_path)
