import json
import sqlite3
from datetime import UTC, datetime
from collections.abc import Iterable
from pathlib import Path

from .schemas import (
    DocumentBlock,
    DocumentSummary,
    Finding,
    Requirement,
    RequirementCheck,
    ReviewHistoryItem,
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    original_name TEXT NOT NULL,
    stored_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_type TEXT NOT NULL CHECK (file_type IN ('docx', 'pdf')),
    file_size INTEGER NOT NULL CHECK (file_size > 0),
    page_count INTEGER NOT NULL CHECK (page_count > 0),
    text_char_count INTEGER NOT NULL CHECK (text_char_count > 0),
    parse_status TEXT NOT NULL CHECK (parse_status IN ('ready', 'failed')),
    parse_warnings TEXT NOT NULL DEFAULT '[]',
    heading_count INTEGER NOT NULL DEFAULT 0,
    paragraph_count INTEGER NOT NULL DEFAULT 0,
    table_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_blocks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_index INTEGER NOT NULL,
    block_type TEXT NOT NULL CHECK (block_type IN ('heading', 'paragraph', 'table')),
    heading_level INTEGER,
    page_number INTEGER,
    location_confidence REAL NOT NULL CHECK (location_confidence BETWEEN 0 AND 1),
    section_path TEXT,
    content TEXT NOT NULL,
    search_text TEXT NOT NULL,
    UNIQUE(document_id, block_index)
);

CREATE INDEX IF NOT EXISTS idx_document_blocks_document
ON document_blocks(document_id, block_index);

CREATE VIRTUAL TABLE IF NOT EXISTS document_blocks_fts USING fts5(
    block_id UNINDEXED,
    document_id UNINDEXED,
    search_text,
    section_path,
    tokenize='trigram'
);

CREATE TABLE IF NOT EXISTS reviews (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    tender_document_id TEXT NOT NULL REFERENCES documents(id),
    bid_document_id TEXT NOT NULL REFERENCES documents(id),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'awaiting_review', 'completed', 'failed')),
    current_stage TEXT NOT NULL,
    model_provider TEXT NOT NULL,
    model_base_url TEXT NOT NULL,
    model_name TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    model_parameters TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    category TEXT NOT NULL CHECK (category IN (
        'qualification', 'disqualification', 'scoring', 'timeline', 'materials'
    )),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    sort_index INTEGER NOT NULL,
    mandatory INTEGER NOT NULL CHECK (mandatory IN (0, 1)),
    source_block_ids TEXT NOT NULL,
    source_excerpt TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1)
);

CREATE INDEX IF NOT EXISTS idx_requirements_review
ON requirements(review_id, sort_index);

CREATE TABLE IF NOT EXISTS requirement_checks (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    requirement_id TEXT NOT NULL REFERENCES requirements(id) ON DELETE CASCADE,
    match_status TEXT NOT NULL CHECK (match_status IN (
        'satisfied', 'partial', 'not_satisfied', 'not_found', 'uncertain'
    )),
    reason TEXT NOT NULL,
    tender_evidence TEXT NOT NULL,
    bid_evidence TEXT NOT NULL,
    searched_block_ids TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    UNIQUE(review_id, requirement_id)
);

CREATE INDEX IF NOT EXISTS idx_requirement_checks_review
ON requirement_checks(review_id, requirement_id);

CREATE TABLE IF NOT EXISTS findings (
    id TEXT PRIMARY KEY,
    review_id TEXT NOT NULL REFERENCES reviews(id) ON DELETE CASCADE,
    requirement_check_id TEXT REFERENCES requirement_checks(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('requirement_risk', 'consistency')),
    category TEXT NOT NULL,
    risk_level TEXT NOT NULL CHECK (risk_level IN ('high', 'medium', 'low')),
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    suggestion TEXT NOT NULL,
    evidence TEXT NOT NULL,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    review_status TEXT NOT NULL DEFAULT 'pending' CHECK (
        review_status IN ('pending', 'confirmed', 'ignored', 'modified')
    ),
    reviewer_note TEXT,
    override TEXT,
    reviewed_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_findings_review
ON findings(review_id, risk_level, category);
"""


class _Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
        self._migrate()

    def _migrate(self) -> None:
        with self.connect() as connection:
            definition = connection.execute("SELECT sql FROM sqlite_master WHERE name='reviews'").fetchone()[0]
            if "'completed'" not in definition:
                backup = self.path.with_suffix('.pre-workflow.bak')
                if not backup.exists():
                    with sqlite3.connect(backup) as destination:
                        connection.backup(destination)
                connection.execute('PRAGMA foreign_keys=OFF')
                connection.execute('BEGIN IMMEDIATE')
                new_sql = definition.replace('CREATE TABLE reviews', 'CREATE TABLE reviews_new').replace(
                    "'running', 'awaiting_review', 'failed'", "'queued', 'running', 'awaiting_review', 'completed', 'failed'")
                connection.execute(new_sql)
                connection.execute('INSERT INTO reviews_new SELECT * FROM reviews')
                connection.execute('DROP TABLE reviews')
                connection.execute('ALTER TABLE reviews_new RENAME TO reviews')
                connection.commit()
                connection.execute('PRAGMA foreign_keys=ON')
            columns = {row[1] for row in connection.execute('PRAGMA table_info(reviews)')}
            for name, declaration in {'progress': 'INTEGER NOT NULL DEFAULT 0', 'run_attempt': 'INTEGER NOT NULL DEFAULT 1', 'report_snapshot': 'TEXT'}.items():
                if name not in columns:
                    connection.execute(f'ALTER TABLE reviews ADD COLUMN {name} {declaration}')
            if connection.execute('PRAGMA foreign_key_check').fetchone():
                raise RuntimeError('数据库外键检查失败')

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, factory=_Connection)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def is_healthy(self) -> bool:
        with self.connect() as connection:
            return connection.execute("SELECT 1").fetchone()[0] == 1

    def has_fts5(self) -> bool:
        with self.connect() as connection:
            try:
                connection.execute("SELECT count(*) FROM document_blocks_fts").fetchone()
                return True
            except sqlite3.OperationalError:
                return False

    def insert_document(self, document: dict, blocks: Iterable[dict]) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO documents (
                    id, original_name, stored_path, sha256, file_type, file_size,
                    page_count, text_char_count, parse_status, parse_warnings,
                    heading_count, paragraph_count, table_count, created_at
                ) VALUES (
                    :id, :original_name, :stored_path, :sha256, :file_type, :file_size,
                    :page_count, :text_char_count, 'ready', :parse_warnings,
                    :heading_count, :paragraph_count, :table_count, :created_at
                )""",
                document,
            )
            for block in blocks:
                connection.execute(
                    """INSERT INTO document_blocks (
                        id, document_id, block_index, block_type, heading_level,
                        page_number, location_confidence, section_path, content, search_text
                    ) VALUES (
                        :id, :document_id, :block_index, :block_type, :heading_level,
                        :page_number, :location_confidence, :section_path, :content, :search_text
                    )""",
                    block,
                )
                connection.execute(
                    """INSERT INTO document_blocks_fts
                    (block_id, document_id, search_text, section_path)
                    VALUES (:id, :document_id, :search_text, :section_path)""",
                    block,
                )

    def get_document(self, document_id: str) -> DocumentSummary | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
        return self._summary(row) if row else None

    def get_all_blocks(self, document_id: str) -> list[DocumentBlock]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM document_blocks WHERE document_id = ?
                ORDER BY block_index""",
                (document_id,),
            ).fetchall()
        return [self._block(row) for row in rows]

    def insert_review(self, review: dict) -> None:
        with self.connect() as connection:
            connection.execute(
                """INSERT INTO reviews (
                    id, name, tender_document_id, bid_document_id, status,
                    current_stage, model_provider, model_base_url, model_name,
                    prompt_version, prompt_hash, model_parameters, created_at, updated_at
                ) VALUES (
                    :id, :name, :tender_document_id, :bid_document_id, 'queued',
                    'queued', :model_provider, :model_base_url, :model_name,
                    :prompt_version, :prompt_hash, :model_parameters, :created_at, :created_at
                )""",
                review,
            )

    def complete_requirement_extraction(
        self,
        review_id: str,
        requirements: Iterable[dict],
        input_tokens: int,
        output_tokens: int,
        updated_at: str,
    ) -> None:
        with self.connect() as connection:
            if connection.execute('SELECT 1 FROM requirements WHERE review_id=?', (review_id,)).fetchone():
                return
            for requirement in requirements:
                connection.execute(
                    """INSERT INTO requirements (
                        id, review_id, category, title, description, sort_index,
                        mandatory, source_block_ids, source_excerpt, confidence
                    ) VALUES (
                        :id, :review_id, :category, :title, :description, :sort_index,
                        :mandatory, :source_block_ids, :source_excerpt, :confidence
                    )""",
                    requirement,
                )
            connection.execute(
                """UPDATE reviews SET current_stage = 'requirements_extracted', input_tokens = ?,
                    output_tokens = ?, updated_at = ? WHERE id = ?""",
                (input_tokens, output_tokens, updated_at, review_id),
            )

    def complete_requirement_matching(
        self,
        review_id: str,
        checks: Iterable[dict],
        input_tokens: int,
        output_tokens: int,
        updated_at: str,
    ) -> None:
        with self.connect() as connection:
            if connection.execute('SELECT 1 FROM requirement_checks WHERE review_id=?', (review_id,)).fetchone():
                return
            for check in checks:
                connection.execute(
                    """INSERT INTO requirement_checks (
                        id, review_id, requirement_id, match_status, reason,
                        tender_evidence, bid_evidence, searched_block_ids, confidence
                    ) VALUES (
                        :id, :review_id, :requirement_id, :match_status, :reason,
                        :tender_evidence, :bid_evidence, :searched_block_ids, :confidence
                    )""",
                    check,
                )
            connection.execute(
                """UPDATE reviews SET current_stage = 'requirements_matched',
                    input_tokens = input_tokens + ?, output_tokens = output_tokens + ?,
                    updated_at = ? WHERE id = ?""",
                (input_tokens, output_tokens, updated_at, review_id),
            )

    def complete_consistency_check(
        self, review_id: str, findings: Iterable[dict], updated_at: str
    ) -> None:
        with self.connect() as connection:
            if connection.execute('SELECT 1 FROM findings WHERE review_id=?', (review_id,)).fetchone():
                return
            for finding in findings:
                connection.execute(
                    """INSERT INTO findings (
                        id, review_id, requirement_check_id, type, category,
                        risk_level, title, description, suggestion, evidence,
                        confidence, review_status
                    ) VALUES (
                        :id, :review_id, :requirement_check_id, :type, :category,
                        :risk_level, :title, :description, :suggestion, :evidence,
                        :confidence, 'pending'
                    )""",
                    finding,
                )
            connection.execute(
                """UPDATE reviews SET current_stage = 'evidence_validated',
                    progress = 90, updated_at = ? WHERE id = ?""",
                (updated_at, review_id),
            )

    def fail_review(self, review_id: str, message: str, updated_at: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE reviews SET status = 'failed',
                error_message = ?, updated_at = ? WHERE id = ?""",
                (message, updated_at, review_id),
            )

    def list_reviews(self, offset: int = 0, limit: int = 20) -> tuple[list[ReviewHistoryItem], int]:
        with self.connect() as connection:
            total = connection.execute("SELECT count(*) FROM reviews").fetchone()[0]
            rows = connection.execute(
                """SELECT r.*, td.original_name AS tender_file_name,
                    bd.original_name AS bid_file_name,
                    count(f.id) AS finding_count,
                    coalesce(sum(CASE WHEN f.review_status != 'ignored' AND coalesce(json_extract(f.override, '$.risk_level'), f.risk_level) = 'high' THEN 1 ELSE 0 END), 0)
                        AS high_risk_count
                FROM reviews r
                JOIN documents td ON td.id = r.tender_document_id
                JOIN documents bd ON bd.id = r.bid_document_id
                LEFT JOIN findings f ON f.review_id = r.id
                GROUP BY r.id
                ORDER BY r.created_at DESC
                LIMIT ? OFFSET ?""",
                (limit, offset),
            ).fetchall()
        return [ReviewHistoryItem(**dict(row)) for row in rows], total

    def list_requirements(self, review_id: str) -> list[Requirement]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM requirements WHERE review_id = ?
                ORDER BY sort_index, id""",
                (review_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["mandatory"] = bool(row["mandatory"])
            item["source_block_ids"] = json.loads(row["source_block_ids"])
            items.append(Requirement(**item))
        return items

    def list_requirement_checks(self, review_id: str) -> list[RequirementCheck]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM requirement_checks WHERE review_id = ?
                ORDER BY rowid""",
                (review_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            for field in ("tender_evidence", "bid_evidence", "searched_block_ids"):
                item[field] = json.loads(row[field])
            items.append(RequirementCheck(**item))
        return items

    def list_findings(self, review_id: str) -> list[Finding]:
        with self.connect() as connection:
            rows = connection.execute(
                """SELECT * FROM findings WHERE review_id = ?
                ORDER BY CASE risk_level WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
                rowid""",
                (review_id,),
            ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(row["evidence"])
            item["override"] = json.loads(row["override"]) if row["override"] else None
            items.append(Finding(**item))
        return items

    def get_review(self, review_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute('SELECT * FROM reviews WHERE id=?', (review_id,)).fetchone()
        return dict(row) if row else None

    def set_stage(self, review_id: str, stage: str, progress: int, status: str = 'running') -> None:
        with self.connect() as connection:
            connection.execute('UPDATE reviews SET current_stage=?, progress=?, status=?, updated_at=? WHERE id=?',
                               (stage, progress, status, datetime.now(UTC).isoformat(), review_id))

    def recover_interrupted(self) -> None:
        with self.connect() as connection:
            connection.execute("UPDATE reviews SET status='failed', error_message='服务中断，请从检查点重试', updated_at=? WHERE status IN ('queued','running')", (datetime.now(UTC).isoformat(),))

    def claim_retry(self, review_id: str) -> bool:
        with self.connect() as connection:
            return connection.execute("UPDATE reviews SET status='queued', error_message=NULL, run_attempt=run_attempt+1, updated_at=? WHERE id=? AND status='failed'",
                                      (datetime.now(UTC).isoformat(), review_id)).rowcount == 1

    def update_finding(self, finding_id: str, update) -> str:
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT f.review_id, r.status FROM findings f JOIN reviews r ON r.id=f.review_id WHERE f.id=?', (finding_id,)).fetchone()
            if not row:
                raise LookupError('问题不存在')
            if row['status'] != 'awaiting_review':
                raise ValueError('仅待人工复核的审查允许修改')
            connection.execute('UPDATE findings SET review_status=?, reviewer_note=?, override=?, reviewed_at=? WHERE id=?',
                               (update.review_status, update.reviewer_note, update.override.model_dump_json() if update.override else None,
                                datetime.now(UTC).isoformat(), finding_id))
            connection.execute('UPDATE reviews SET updated_at=? WHERE id=?', (datetime.now(UTC).isoformat(), row['review_id']))
        return row['review_id']

    def freeze(self, review_id: str, snapshot_builder) -> None:
        with self.connect() as connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT status FROM reviews WHERE id=?', (review_id,)).fetchone()
            if row and row['status'] == 'completed':
                return
            if not row or row['status'] != 'awaiting_review':
                raise ValueError('当前审查不能完成复核')
            if connection.execute("SELECT 1 FROM findings WHERE review_id=? AND review_status='pending'", (review_id,)).fetchone():
                raise ValueError('请先处理所有待确认问题')
            snapshot = snapshot_builder()
            connection.execute("UPDATE reviews SET status='completed', current_stage='completed', progress=100, report_snapshot=?, updated_at=? WHERE id=?",
                               (json.dumps(snapshot, ensure_ascii=False), snapshot['completed_at'], review_id))

    def list_blocks(
        self,
        document_id: str,
        query: str | None,
        offset: int,
        limit: int,
        context: int,
    ) -> tuple[list[DocumentBlock], int]:
        with self.connect() as connection:
            if query:
                if len(query.strip()) < 3:
                    hits = connection.execute(
                        """SELECT block_index FROM document_blocks
                        WHERE document_id = ? AND instr(search_text, ?) > 0
                        ORDER BY block_index LIMIT 50""",
                        (document_id, query.strip()),
                    ).fetchall()
                else:
                    match = '"' + query.replace('"', '""') + '"'
                    hits = connection.execute(
                        """SELECT b.block_index
                        FROM document_blocks_fts f
                        JOIN document_blocks b ON b.id = f.block_id
                        WHERE f.document_id = ? AND document_blocks_fts MATCH ?
                        ORDER BY bm25(document_blocks_fts) LIMIT 50""",
                        (document_id, match),
                    ).fetchall()
                indices = sorted(
                    {
                        index
                        for hit in hits
                        for index in range(
                            max(0, hit["block_index"] - context),
                            hit["block_index"] + context + 1,
                        )
                    }
                )
                total = len(indices)
                page = indices[offset : offset + limit]
                if not page:
                    return [], total
                placeholders = ",".join("?" for _ in page)
                rows = connection.execute(
                    f"""SELECT * FROM document_blocks
                    WHERE document_id = ? AND block_index IN ({placeholders})
                    ORDER BY block_index""",
                    (document_id, *page),
                ).fetchall()
            else:
                total = connection.execute(
                    "SELECT count(*) FROM document_blocks WHERE document_id = ?",
                    (document_id,),
                ).fetchone()[0]
                rows = connection.execute(
                    """SELECT * FROM document_blocks WHERE document_id = ?
                    ORDER BY block_index LIMIT ? OFFSET ?""",
                    (document_id, limit, offset),
                ).fetchall()
        return [self._block(row) for row in rows], total

    @staticmethod
    def _summary(row: sqlite3.Row) -> DocumentSummary:
        return DocumentSummary(
            **dict(row), warnings=json.loads(row["parse_warnings"])
        )

    @staticmethod
    def _block(row: sqlite3.Row) -> DocumentBlock:
        return DocumentBlock(**dict(row))
