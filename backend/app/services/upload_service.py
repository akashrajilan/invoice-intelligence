from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile, status
from starlette.concurrency import run_in_threadpool

from app.config import settings
from app.schemas import UploadResponse
from app.services.database import database
from app.services.invoice_extractor import extract_invoice_fields_hybrid
from app.services.ocr_service import extract_document_text


ALLOWED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
}


async def validate_upload(file: UploadFile) -> UploadResponse:
    filename = file.filename or ""
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Upload a PDF, PNG, JPG, or JPEG invoice.",
        )

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="The file content type is not supported.",
        )

    content = await file.read()
    size_bytes = len(content)
    max_size = settings.max_upload_size_mb * 1024 * 1024

    if size_bytes == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )

    if size_bytes > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"The file must be {settings.max_upload_size_mb} MB or smaller.",
        )

    file_hash = sha256(content).hexdigest()
    duplicate_of = await run_in_threadpool(database.find_duplicate, file_hash)

    extraction = await run_in_threadpool(
        extract_document_text,
        content,
        extension,
    )
    invoice = await run_in_threadpool(extract_invoice_fields_hybrid, extraction.text)
    document_id = str(uuid4())

    if duplicate_of is None:
        await run_in_threadpool(
            database.save_invoice,
            document_id=document_id,
            filename=filename,
            file_hash=file_hash,
            extraction_method=extraction.method,
            invoice=invoice,
            raw_text=extraction.text,
        )

    return UploadResponse(
        document_id=document_id,
        filename=filename,
        content_type=file.content_type,
        size_bytes=size_bytes,
        status="processed",
        message="Document text extracted successfully.",
        page_count=extraction.page_count,
        extraction_method=extraction.method,
        extracted_characters=len(extraction.text),
        raw_text=extraction.text,
        invoice=invoice,
        duplicate=duplicate_of is not None,
        duplicate_of=duplicate_of,
    )
