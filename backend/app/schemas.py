from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    database: Literal["ok"] = "ok"
    sqlite_fts5: bool
    libreoffice: bool
    model_configured: bool
    model_provider: str
    model_name: str | None


class ModelCheckResponse(BaseModel):
    ok: Literal[True] = True
    provider: str
    model: str
    reply: str


class DocumentSummary(BaseModel):
    id: str
    original_name: str
    file_type: Literal["docx", "pdf"]
    file_size: int
    sha256: str
    page_count: int
    text_char_count: int
    parse_status: Literal["ready", "failed"]
    warnings: list[str] = Field(default_factory=list)
    heading_count: int
    paragraph_count: int
    table_count: int
    created_at: str


class DocumentBlock(BaseModel):
    id: str
    block_index: int
    block_type: Literal["heading", "paragraph", "table"]
    heading_level: int | None
    page_number: int | None
    location_confidence: float = Field(ge=0, le=1)
    section_path: str | None
    content: str


class BlockListResponse(BaseModel):
    items: list[DocumentBlock]
    total: int
