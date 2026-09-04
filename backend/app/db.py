import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from .schemas import DocumentBlock, DocumentSummary, Requirement


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
    status TEXT NOT NULL CHECK (status IN ('running', 'awaiting_review', 'failed')),
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
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
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
                    :id, :name, :tender_document_id, :bid_document_id, 'running',
                    'extracting_requirements', :model_provider, :model_base_url, :model_name,
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
                """UPDATE reviews SET status = 'awaiting_review',
                    current_stage = 'requirements_extracted', input_tokens = ?,
                    output_tokens = ?, updated_at = ? WHERE id = ?""",
                (input_tokens, output_tokens, updated_at, review_id),
            )

    def fail_review(self, review_id: str, message: str, updated_at: str) -> None:
        with self.connect() as connection:
            connection.execute(
                """UPDATE reviews SET status = 'failed', current_stage = 'failed',
                error_message = ?, updated_at = ? WHERE id = ?""",
                (message, updated_at, review_id),
            )

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
