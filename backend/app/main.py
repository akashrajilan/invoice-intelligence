import shutil
from pathlib import Path

from fastapi import HTTPException, status
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.config import settings
from app.schemas import (
    DeleteResponse,
    HealthResponse,
    InvoiceDetail,
    InvoiceHistoryResponse,
    UploadResponse,
)
from app.services.database import database
from app.services.export_service import invoice_to_csv, invoice_to_json
from app.services.upload_service import validate_upload


app = FastAPI(
    title=settings.app_name,
    description="Upload and process invoices and receipts.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_check() -> HealthResponse:
    return HealthResponse(
        service=settings.app_name,
        ocr_available=shutil.which("tesseract") is not None,
        llm_enabled=bool(settings.groq_api_key),
    )


@app.post(
    "/api/v1/invoices/upload",
    response_model=UploadResponse,
    tags=["invoices"],
)
async def upload_invoice(file: UploadFile = File(...)) -> UploadResponse:
    return await validate_upload(file)


@app.get(
    "/api/v1/invoices",
    response_model=InvoiceHistoryResponse,
    tags=["invoices"],
)
async def invoice_history(
    limit: int = Query(default=50, ge=1, le=100),
) -> InvoiceHistoryResponse:
    items = database.list_invoices(limit=limit)
    return InvoiceHistoryResponse(items=items, total=database.count_invoices())


def _get_invoice_or_404(document_id: str) -> InvoiceDetail:
    detail = database.get_invoice(document_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )
    return detail


@app.get(
    "/api/v1/invoices/{document_id}",
    response_model=InvoiceDetail,
    tags=["invoices"],
)
async def invoice_detail(document_id: str) -> InvoiceDetail:
    return _get_invoice_or_404(document_id)


@app.get("/api/v1/invoices/{document_id}/export", tags=["invoices"])
async def export_invoice(
    document_id: str,
    format: str = Query(pattern="^(json|csv)$"),
) -> Response:
    detail = _get_invoice_or_404(document_id)
    safe_id = "".join(char for char in document_id if char.isalnum() or char in "-_")
    if format == "json":
        return Response(
            content=invoice_to_json(detail),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="invoice-{safe_id}.json"'},
        )
    return Response(
        content=invoice_to_csv(detail),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="invoice-{safe_id}.csv"'},
    )


@app.delete(
    "/api/v1/invoices/{document_id}",
    response_model=DeleteResponse,
    tags=["invoices"],
)
async def delete_invoice(document_id: str) -> DeleteResponse:
    deleted = database.delete_invoice(document_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invoice not found.",
        )
    return DeleteResponse(deleted=True, document_id=document_id)


# The production container includes the compiled React app. Mounting it last
# keeps every API route above reachable while serving the portfolio UI at `/`.
frontend_dist = Path(__file__).resolve().parent.parent / "frontend_dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
