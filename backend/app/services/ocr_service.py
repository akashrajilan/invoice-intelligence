from io import BytesIO

import fitz
import pytesseract
from fastapi import HTTPException, status
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.schemas import ExtractionResult


MIN_EMBEDDED_TEXT_LENGTH = 20


def _ocr_pdf_page(page: fitz.Page) -> str:
    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
    return pytesseract.image_to_string(image).strip()


def _extract_pdf(content: bytes) -> ExtractionResult:
    try:
        document = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The PDF is damaged or cannot be read.",
        ) from exc

    if document.page_count == 0:
        document.close()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The PDF does not contain any pages.",
        )

    page_texts: list[str] = []
    methods: set[str] = set()
    try:
        for page in document:
            embedded_text = page.get_text("text").strip()
            if len(embedded_text) >= MIN_EMBEDDED_TEXT_LENGTH:
                page_texts.append(embedded_text)
                methods.add("embedded_text")
            else:
                page_texts.append(_ocr_pdf_page(page))
                methods.add("ocr")
    finally:
        page_count = document.page_count
        document.close()

    text = "\n\n".join(part for part in page_texts if part).strip()
    method = "hybrid" if len(methods) > 1 else next(iter(methods), "ocr")
    return ExtractionResult(
        text=text[: settings.max_extracted_chars],
        page_count=page_count,
        method=method,
    )


def _extract_image(content: bytes) -> ExtractionResult:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            if image.mode not in {"RGB", "L"}:
                image = image.convert("RGB")
            text = pytesseract.image_to_string(image).strip()
    except (UnidentifiedImageError, OSError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The image is damaged or cannot be read.",
        ) from exc

    return ExtractionResult(
        text=text[: settings.max_extracted_chars],
        page_count=1,
        method="ocr",
    )


def extract_document_text(content: bytes, extension: str) -> ExtractionResult:
    if extension == ".pdf":
        result = _extract_pdf(content)
    else:
        result = _extract_image(content)

    if not result.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No readable text was found in the document.",
        )

    return result
