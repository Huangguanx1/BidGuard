import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import sqlite3
from fastapi import FastAPI, File, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import Database
from .parser import ParseError, find_libreoffice, parse_document, validate_file
from .schemas import BlockListResponse, DocumentSummary, HealthResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


settings = get_settings()
settings.app_data_dir.mkdir(parents=True, exist_ok=True)
uploads_dir = settings.app_data_dir / "uploads"
uploads_dir.mkdir(parents=True, exist_ok=True)
database = Database(settings.app_data_dir / "bidguard.db")

app = FastAPI(title="BidGuard AI API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApiError)
async def handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"detail": exc.message, "code": exc.code},
    )


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        database="ok" if database.is_healthy() else "ok",
        sqlite_fts5=database.has_fts5(),
        libreoffice=find_libreoffice(settings) is not None,
        model_configured=bool(settings.model_base_url and settings.model_name),
        model_provider=settings.model_provider,
        model_name=settings.model_name or None,
    )


@app.post("/api/documents", response_model=DocumentSummary, status_code=201)
async def upload_document(file: UploadFile = File(...)) -> DocumentSummary:
    original_name = Path(file.filename or "").name
    suffix = Path(original_name).suffix.lower()
    data = await file.read(settings.max_upload_bytes + 1)
    try:
        validate_file(data, suffix, settings)
    except ParseError as exc:
        raise ApiError(422, "invalid_document", str(exc)) from exc

    document_id = str(uuid4())
    stored_path = uploads_dir / f"{document_id}{suffix}"
    stored_path.write_bytes(data)
    try:
        parsed = parse_document(stored_path, suffix, settings)
        counts = {
            kind: sum(block.block_type == kind for block in parsed.blocks)
            for kind in ("heading", "paragraph", "table")
        }
        created_at = datetime.now(UTC).isoformat()
        document = {
            "id": document_id,
            "original_name": original_name,
            "stored_path": str(stored_path.relative_to(settings.app_data_dir)),
            "sha256": hashlib.sha256(data).hexdigest(),
            "file_type": suffix.removeprefix("."),
            "file_size": len(data),
            "page_count": parsed.page_count,
            "text_char_count": parsed.text_char_count,
            "parse_warnings": json.dumps(parsed.warnings, ensure_ascii=False),
            "heading_count": counts["heading"],
            "paragraph_count": counts["paragraph"],
            "table_count": counts["table"],
            "created_at": created_at,
        }
        blocks = [
            {
                "id": str(uuid4()),
                "document_id": document_id,
                "block_index": index,
                **vars(block),
            }
            for index, block in enumerate(parsed.blocks)
        ]
        database.insert_document(document, blocks)
    except (ParseError, sqlite3.Error) as exc:
        stored_path.unlink(missing_ok=True)
        code = "parse_failed" if isinstance(exc, ParseError) else "storage_failed"
        raise ApiError(422 if isinstance(exc, ParseError) else 500, code, str(exc)) from exc
    return database.get_document(document_id)  # type: ignore[return-value]


@app.get("/api/documents/{document_id}", response_model=DocumentSummary)
def get_document(document_id: str) -> DocumentSummary:
    document = database.get_document(document_id)
    if not document:
        raise ApiError(404, "document_not_found", "文档不存在")
    return document


@app.get("/api/documents/{document_id}/blocks", response_model=BlockListResponse)
def get_document_blocks(
    document_id: str,
    q: str | None = Query(default=None, max_length=100),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    context: int = Query(default=1, ge=0, le=3),
) -> BlockListResponse:
    if not database.get_document(document_id):
        raise ApiError(404, "document_not_found", "文档不存在")
    try:
        items, total = database.list_blocks(document_id, q, offset, limit, context)
    except sqlite3.OperationalError as exc:
        raise ApiError(422, "invalid_search", "检索词无法处理") from exc
    return BlockListResponse(items=items, total=total)
