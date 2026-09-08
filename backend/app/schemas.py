from typing import Literal, TypeAlias

from pydantic import BaseModel, Field, model_validator


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


RequirementCategory: TypeAlias = Literal[
    "qualification", "disqualification", "scoring", "timeline", "materials"
]


class ReviewCreate(BaseModel):
    tender_document_id: str
    bid_document_id: str
    name: str | None = Field(default=None, max_length=100)
    external_processing_consent: bool = False


class RequirementDraft(BaseModel):
    category: RequirementCategory
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    mandatory: bool
    source_block_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class Requirement(RequirementDraft):
    id: str
    review_id: str
    sort_index: int
    source_excerpt: str


MatchStatus: TypeAlias = Literal[
    "satisfied", "partial", "not_satisfied", "not_found", "uncertain"
]


class RequirementMatchDraft(BaseModel):
    requirement_id: str
    match_status: MatchStatus
    reason: str = Field(min_length=1, max_length=1000)
    bid_evidence_block_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)


class Evidence(BaseModel):
    block_id: str
    page_number: int | None
    excerpt: str
    document_role: Literal["tender", "bid"] | None = None
    location_confidence: float = Field(default=1, ge=0, le=1)


class RequirementCheck(BaseModel):
    id: str
    review_id: str
    requirement_id: str
    match_status: MatchStatus
    reason: str
    tender_evidence: list[Evidence]
    bid_evidence: list[Evidence]
    searched_block_ids: list[str]
    confidence: float


ConsistencyCategory: TypeAlias = Literal["amount", "date", "project_name", "duration"]


class FindingDraft(BaseModel):
    type: Literal["consistency", "requirement_risk"] = "consistency"
    category: ConsistencyCategory | RequirementCategory
    requirement_check_id: str | None = None
    risk_level: Literal["high", "medium", "low"]
    title: str
    description: str
    suggestion: str
    evidence: list[Evidence] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class Finding(FindingDraft):
    id: str
    review_id: str
    review_status: Literal["pending", "confirmed", "ignored", "modified"]
    reviewer_note: str | None = None
    override: dict | None = None
    reviewed_at: str | None = None


class FindingOverride(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=2000)
    risk_level: Literal["high", "medium", "low"]
    suggestion: str = Field(min_length=1, max_length=2000)


class FindingUpdate(BaseModel):
    review_status: Literal["pending", "confirmed", "ignored", "modified"]
    reviewer_note: str = Field(default="", max_length=2000)
    override: FindingOverride | None = None

    @model_validator(mode="after")
    def validate_override(self):
        if self.review_status == "modified" and self.override is None:
            raise ValueError("修改结论时必须填写修改内容")
        if self.review_status != "modified" and self.override is not None:
            raise ValueError("仅修改状态允许覆盖原始结论")
        return self


class ReviewRunResponse(BaseModel):
    id: str
    name: str
    status: Literal["queued", "running", "awaiting_review", "completed", "failed"]
    current_stage: str
    progress: int = 0
    run_attempt: int = 1
    error_message: str | None = None
    tender_document_id: str
    bid_document_id: str
    created_at: str
    updated_at: str
    model_name: str
    input_tokens: int
    output_tokens: int
    requirements: list[Requirement]
    requirement_checks: list[RequirementCheck]
    findings: list[Finding]


class ReviewHistoryItem(BaseModel):
    id: str
    name: str
    status: Literal["queued", "running", "awaiting_review", "completed", "failed"]
    current_stage: str
    model_name: str
    input_tokens: int
    output_tokens: int
    finding_count: int
    high_risk_count: int
    created_at: str
    updated_at: str
    tender_file_name: str
    bid_file_name: str
    error_message: str | None = None


class ReviewHistoryResponse(BaseModel):
    items: list[ReviewHistoryItem]
    total: int


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
