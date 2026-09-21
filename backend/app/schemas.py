from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "healthy"
    service: str
    database: str = "available"
    ocr_available: bool
    llm_enabled: bool


class UploadResponse(BaseModel):
    document_id: str
    filename: str
    content_type: str
    size_bytes: int = Field(ge=1)
    status: str
    message: str
    page_count: int = Field(ge=1)
    extraction_method: str
    extracted_characters: int = Field(ge=0)
    raw_text: str
    invoice: "StructuredInvoice"
    duplicate: bool = False
    duplicate_of: str | None = None


class ExtractionResult(BaseModel):
    text: str
    page_count: int = Field(ge=1)
    method: str


class ExtractedField(BaseModel):
    value: str | float | None = None
    confidence: float = Field(ge=0, le=1)


class LineItem(BaseModel):
    description: str
    quantity: float | None = None
    unit_price: float | None = None
    amount: float
    confidence: float = Field(ge=0, le=1)


class StructuredInvoice(BaseModel):
    vendor_name: ExtractedField
    invoice_number: ExtractedField
    invoice_date: ExtractedField
    due_date: ExtractedField
    currency: ExtractedField
    subtotal: ExtractedField
    tax: ExtractedField
    total: ExtractedField
    line_items: list[LineItem] = Field(default_factory=list)
    totals_valid: bool | None = None
    warnings: list[str] = Field(default_factory=list)
    extraction_engine: str = "deterministic"


class InvoiceHistoryItem(BaseModel):
    document_id: str
    filename: str
    vendor_name: str | None = None
    invoice_number: str | None = None
    total: float | None = None
    currency: str | None = None
    extraction_method: str
    created_at: str


class InvoiceHistoryResponse(BaseModel):
    items: list[InvoiceHistoryItem]
    total: int = Field(ge=0)


class InvoiceDetail(BaseModel):
    document_id: str
    filename: str
    extraction_method: str
    created_at: str
    invoice: StructuredInvoice
    raw_text: str


class DeleteResponse(BaseModel):
    deleted: bool
    document_id: str
