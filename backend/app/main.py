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
from .model import (
    REVIEW_PROMPT_VERSION,
    ModelError,
    check_model,
    extract_requirements,
    match_requirements,
    review_prompt_hash,
)
from .parser import ParseError, find_libreoffice, parse_document, validate_file
from .rules import run_consistency_rules
from .schemas import (
    BlockListResponse,
    DocumentSummary,
    HealthResponse,
    ModelCheckResponse,
    ReviewCreate,
    ReviewHistoryResponse,
    ReviewRunResponse,
)


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
        model_configured=bool(
            settings.model_base_url and settings.model_api_key and settings.model_name
        ),
        model_provider=settings.model_provider,
        model_name=settings.model_name or None,
    )


@app.post("/api/model/check", response_model=ModelCheckResponse)
def model_check() -> ModelCheckResponse:
    try:
        reply = check_model(settings)
    except ModelError as exc:
        raise ApiError(502, "model_unavailable", str(exc)) from exc
    return ModelCheckResponse(
        provider=settings.model_provider,
        model=settings.model_name,
        reply=reply,
    )


@app.post("/api/reviews", response_model=ReviewRunResponse, status_code=201)
def create_review(body: ReviewCreate) -> ReviewRunResponse:
    if body.tender_document_id == body.bid_document_id:
        raise ApiError(422, "documents_must_differ", "招标文件和投标文件不能相同")
    tender = database.get_document(body.tender_document_id)
    bid = database.get_document(body.bid_document_id)
    if not tender or not bid:
        raise ApiError(404, "document_not_found", "招标文件或投标文件不存在")

    review_id = str(uuid4())
    created_at = datetime.now(UTC).isoformat()
    review_name = body.name or f"{tender.original_name} / {bid.original_name}"[:100]
    database.insert_review(
        {
            "id": review_id,
            "name": review_name,
            "tender_document_id": tender.id,
            "bid_document_id": bid.id,
            "model_provider": settings.model_provider,
            "model_base_url": settings.model_base_url,
            "model_name": settings.model_name,
            "prompt_version": REVIEW_PROMPT_VERSION,
            "prompt_hash": review_prompt_hash(),
            "model_parameters": json.dumps(
                {
                    "temperature": settings.model_temperature,
                    "batch_chars": settings.model_batch_chars,
                }
            ),
            "created_at": created_at,
        }
    )
    blocks = database.get_all_blocks(tender.id)
    block_map = {block.id: block for block in blocks}
    try:
        drafts, input_tokens, output_tokens = extract_requirements(blocks, settings)
        requirement_rows = []
        for draft in drafts:
            evidence = [block_map[block_id] for block_id in draft.source_block_ids]
            requirement_rows.append(
                {
                    "id": str(uuid4()),
                    "review_id": review_id,
                    **draft.model_dump(),
                    "sort_index": min(block.block_index for block in evidence),
                    "mandatory": int(draft.mandatory),
                    "source_block_ids": json.dumps(draft.source_block_ids),
                    "source_excerpt": "\n".join(block.content for block in evidence)[:1000],
                }
            )
        updated_at = datetime.now(UTC).isoformat()
        database.complete_requirement_extraction(
            review_id,
            requirement_rows,
            input_tokens,
            output_tokens,
            updated_at,
        )
        requirements = database.list_requirements(review_id)
        bid_blocks = database.get_all_blocks(bid.id)
        matches, match_input_tokens, match_output_tokens = match_requirements(
            requirements, bid_blocks, settings
        )
        requirement_map = {requirement.id: requirement for requirement in requirements}
        check_rows = []
        for match in matches:
            requirement = requirement_map[match.draft.requirement_id]
            candidate_map = {block.id: block for block in match.candidates}
            check_rows.append(
                {
                    "id": str(uuid4()),
                    "review_id": review_id,
                    "requirement_id": requirement.id,
                    "match_status": match.draft.match_status,
                    "reason": match.draft.reason,
                    "tender_evidence": json.dumps(
                        [
                            {
                                "block_id": block_id,
                                "page_number": block_map[block_id].page_number,
                                "excerpt": block_map[block_id].content[:500],
                            }
                            for block_id in requirement.source_block_ids
                        ],
                        ensure_ascii=False,
                    ),
                    "bid_evidence": json.dumps(
                        [
                            {
                                "block_id": block_id,
                                "page_number": candidate_map[block_id].page_number,
                                "excerpt": candidate_map[block_id].content[:500],
                            }
                            for block_id in match.draft.bid_evidence_block_ids
                        ],
                        ensure_ascii=False,
                    ),
                    "searched_block_ids": json.dumps(
                        [block.id for block in match.candidates]
                    ),
                    "confidence": match.draft.confidence,
                }
            )
        database.complete_requirement_matching(
            review_id,
            check_rows,
            match_input_tokens,
            match_output_tokens,
            datetime.now(UTC).isoformat(),
        )
        finding_rows = [
            {
                "id": str(uuid4()),
                "review_id": review_id,
                **finding.model_dump(exclude={"evidence"}),
                "evidence": json.dumps(
                    [item.model_dump() for item in finding.evidence], ensure_ascii=False
                ),
            }
            for finding in run_consistency_rules(blocks, bid_blocks)
        ]
        database.complete_consistency_check(
            review_id, finding_rows, datetime.now(UTC).isoformat()
        )
    except ModelError as exc:
        database.fail_review(review_id, str(exc), datetime.now(UTC).isoformat())
        raise ApiError(502, "review_run_failed", str(exc)) from exc
    except sqlite3.Error as exc:
        database.fail_review(review_id, "要求保存失败", datetime.now(UTC).isoformat())
        raise ApiError(500, "storage_failed", "要求保存失败") from exc

    return ReviewRunResponse(
        id=review_id,
        name=review_name,
        status="awaiting_review",
        current_stage="consistency_checked",
        model_name=settings.model_name,
        input_tokens=input_tokens + match_input_tokens,
        output_tokens=output_tokens + match_output_tokens,
        requirements=database.list_requirements(review_id),
        requirement_checks=database.list_requirement_checks(review_id),
        findings=database.list_findings(review_id),
    )


@app.get("/api/reviews", response_model=ReviewHistoryResponse)
def list_reviews(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
) -> ReviewHistoryResponse:
    items, total = database.list_reviews(offset, limit)
    return ReviewHistoryResponse(items=items, total=total)


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
