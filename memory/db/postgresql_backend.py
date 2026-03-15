"""
PostgreSQL + pgvector backend for Agent Memory Service.

This backend provides transactional storage, pgvector similarity search, and
simple hybrid retrieval using PostgreSQL full-text search plus vector fusion.
"""

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import asyncpg

from memory.db.base import (
    ContainerType,
    DatabaseCapabilities,
    EmbeddingProvider,
    MemoryDatabase,
    SearchResult,
)


TABLE_NAMES = {
    ContainerType.INTERACTIONS: "interactions",
    ContainerType.INSIGHTS: "insights",
    ContainerType.SESSION_SUMMARIES: "session_summaries",
}

VECTOR_FIELDS = {
    ContainerType.INTERACTIONS: {"content_vector", "summary_vector"},
    ContainerType.INSIGHTS: {"insight_vector"},
    ContainerType.SESSION_SUMMARIES: {"summary_vector"},
}

JSON_FIELDS = {
    ContainerType.INTERACTIONS: {"metadata"},
    ContainerType.INSIGHTS: {"session_ids", "source_insight_ids", "source_session_ids", "mutation_history"},
    ContainerType.SESSION_SUMMARIES: {"key_topics", "extracted_insights"},
}

FILTERABLE_FIELDS = {
    ContainerType.INTERACTIONS: {"id", "user_id", "agent_id", "session_id", "timestamp", "created_at", "updated_at"},
    ContainerType.INSIGHTS: {
        "id",
        "user_id",
        "agent_id",
        "insight_type",
        "category",
        "confidence",
        "importance",
        "processed",
        "date_added",
        "last_accessed",
        "access_count",
        "is_deleted",
        "deleted_at",
        "created_at",
        "updated_at",
    },
    ContainerType.SESSION_SUMMARIES: {
        "id",
        "user_id",
        "agent_id",
        "start_time",
        "end_time",
        "status",
        "reflection_status",
        "turn_count",
        "created_at",
        "updated_at",
    },
}

SCHEMAS = {
    ContainerType.INTERACTIONS: """
        CREATE TABLE IF NOT EXISTS interactions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT 'default',
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            metadata JSONB DEFAULT '{{}}'::jsonb,
            content_vector vector({dims}),
            summary_vector vector({dims}),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pg_interactions_user_agent ON interactions(user_id, agent_id);
        CREATE INDEX IF NOT EXISTS idx_pg_interactions_session ON interactions(session_id);
        CREATE INDEX IF NOT EXISTS idx_pg_interactions_content_fts ON interactions USING GIN (
            to_tsvector('english', coalesce(content, '') || ' ' || coalesce(summary, ''))
        );
    """,
    ContainerType.INSIGHTS: """
        CREATE TABLE IF NOT EXISTS insights (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT 'default',
            insight_type TEXT NOT NULL,
            session_ids JSONB DEFAULT '[]'::jsonb,
            insight_text TEXT NOT NULL,
            insight_vector vector({dims}),
            confidence DOUBLE PRECISION,
            importance TEXT,
            category TEXT,
            reflection_flag TEXT,
            processed BOOLEAN DEFAULT FALSE,
            source_insight_ids JSONB DEFAULT '[]'::jsonb,
            source_session_ids JSONB DEFAULT '[]'::jsonb,
            date_added TEXT,
            last_accessed TEXT,
            access_count INTEGER DEFAULT 0,
            is_deleted BOOLEAN DEFAULT FALSE,
            deleted_at TEXT,
            mutation_history JSONB DEFAULT '[]'::jsonb,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pg_insights_user_agent ON insights(user_id, agent_id);
        CREATE INDEX IF NOT EXISTS idx_pg_insights_type ON insights(insight_type);
        CREATE INDEX IF NOT EXISTS idx_pg_insights_text_fts ON insights USING GIN (
            to_tsvector('english', coalesce(insight_text, '') || ' ' || coalesce(category, ''))
        );
    """,
    ContainerType.SESSION_SUMMARIES: """
        CREATE TABLE IF NOT EXISTS session_summaries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            agent_id TEXT NOT NULL DEFAULT 'default',
            start_time TEXT NOT NULL,
            end_time TEXT,
            summary TEXT DEFAULT '',
            summary_vector vector({dims}),
            key_topics JSONB DEFAULT '[]'::jsonb,
            extracted_insights JSONB DEFAULT '[]'::jsonb,
            status TEXT DEFAULT 'active',
            reflection_status TEXT DEFAULT 'pending',
            cumulative_summary TEXT DEFAULT '',
            turn_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_pg_summaries_user_agent ON session_summaries(user_id, agent_id);
        CREATE INDEX IF NOT EXISTS idx_pg_summaries_status ON session_summaries(status);
        CREATE INDEX IF NOT EXISTS idx_pg_summaries_text_fts ON session_summaries USING GIN (
            to_tsvector('english', coalesce(summary, '') || ' ' || coalesce(cumulative_summary, ''))
        );
    """,
}

SELECT_FIELDS = {
    ContainerType.INTERACTIONS: [
        "id",
        "user_id",
        "agent_id",
        "session_id",
        "timestamp",
        "content",
        "summary",
        "metadata",
        "content_vector::text AS content_vector",
        "summary_vector::text AS summary_vector",
        "created_at",
        "updated_at",
    ],
    ContainerType.INSIGHTS: [
        "id",
        "user_id",
        "agent_id",
        "session_ids",
        "insight_type",
        "insight_text",
        "insight_vector::text AS insight_vector",
        "confidence",
        "importance",
        "category",
        "reflection_flag",
        "processed",
        "source_insight_ids",
        "source_session_ids",
        "date_added",
        "last_accessed",
        "access_count",
        "is_deleted",
        "deleted_at",
        "mutation_history",
        "created_at",
        "updated_at",
    ],
    ContainerType.SESSION_SUMMARIES: [
        "id",
        "user_id",
        "agent_id",
        "start_time",
        "end_time",
        "summary",
        "summary_vector::text AS summary_vector",
        "key_topics",
        "extracted_insights",
        "status",
        "reflection_status",
        "cumulative_summary",
        "turn_count",
        "created_at",
        "updated_at",
    ],
}

HYBRID_TEXT_EXPRESSIONS = {
    ContainerType.INTERACTIONS: "coalesce(content, '') || ' ' || coalesce(summary, '')",
    ContainerType.INSIGHTS: "coalesce(insight_text, '') || ' ' || coalesce(category, '')",
    ContainerType.SESSION_SUMMARIES: "coalesce(summary, '') || ' ' || coalesce(cumulative_summary, '')",
}

REQUIRED_FIELDS = {
    ContainerType.INTERACTIONS: {"user_id", "agent_id", "session_id", "timestamp", "content", "created_at", "updated_at"},
    ContainerType.INSIGHTS: {"user_id", "agent_id", "insight_type", "insight_text", "created_at", "updated_at"},
    ContainerType.SESSION_SUMMARIES: {"user_id", "agent_id", "start_time", "created_at", "updated_at"},
}


class PostgreSQLDatabase(MemoryDatabase):
    """PostgreSQL implementation of the memory database interface."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        pool: Optional[asyncpg.Pool] = None,
        embedding_provider: Optional[EmbeddingProvider] = None,
        vector_dimensions: int = 1536,
    ):
        super().__init__(embedding_provider)
        self.connection_string = connection_string or os.getenv("POSTGRES_CONNECTION_STRING") or os.getenv("DATABASE_URL")
        self.vector_dimensions = vector_dimensions
        self._pool = pool
        self._owns_pool = pool is None
        self._initialized = False

        if self._pool is None and not self.connection_string:
            raise ValueError("PostgreSQL requires connection_string or an existing asyncpg pool.")

    async def initialize(self) -> None:
        """Create pool, extensions, tables, and indexes."""
        if self._initialized:
            return

        if self._pool is None:
            self._pool = await asyncpg.create_pool(self.connection_string, min_size=1, max_size=10)

        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            for container in ContainerType:
                await conn.execute(SCHEMAS[container].format(dims=self.vector_dimensions))

        self._initialized = True

    async def close(self) -> None:
        """Close owned connection pool."""
        if self._owns_pool and self._pool is not None:
            await self._pool.close()
        self._pool = None
        self._initialized = False

    def get_capabilities(self) -> DatabaseCapabilities:
        """Describe backend capabilities."""
        return DatabaseCapabilities(
            supports_vector_search=True,
            supports_hybrid_search=True,
            supports_full_text_search=True,
            supports_transactions=True,
            vector_dimensions=self.vector_dimensions,
            max_batch_size=1000,
            backend_name="postgresql",
            backend_version="pgvector",
        )

    async def upsert(
        self,
        container: ContainerType,
        document: Dict[str, Any],
        partition_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert or update one document."""
        container = self._normalize_container(container)
        if "id" not in document:
            raise ValueError("Document must have an 'id' field")

        async with self._pool.acquire() as conn:
            normalized = await self._normalize_document_for_upsert(conn, container, document)
            table = TABLE_NAMES[container]
            prepared = self._prepare_document(container, normalized)
            columns, placeholders, values = self._build_upsert_values(container, prepared)
            update_columns = [column for column in columns if column != "id"]
            update_clause = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
            sql = (
                f"INSERT INTO {table} ({', '.join(columns)}) "
                f"VALUES ({', '.join(placeholders)}) "
                f"ON CONFLICT (id) DO UPDATE SET {update_clause}"
            )
            await self._execute_upsert(conn, sql, values)
        return document

    async def batch_upsert(
        self,
        container: ContainerType,
        documents: List[Dict[str, Any]],
        partition_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Insert or update multiple documents in a transaction."""
        container = self._normalize_container(container)
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for document in documents:
                    if "id" not in document:
                        raise ValueError("Document must have an 'id' field")

                    normalized = await self._normalize_document_for_upsert(conn, container, document)
                    table = TABLE_NAMES[container]
                    prepared = self._prepare_document(container, normalized)
                    columns, placeholders, values = self._build_upsert_values(container, prepared)
                    update_columns = [column for column in columns if column != "id"]
                    update_clause = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)
                    sql = (
                        f"INSERT INTO {table} ({', '.join(columns)}) "
                        f"VALUES ({', '.join(placeholders)}) "
                        f"ON CONFLICT (id) DO UPDATE SET {update_clause}"
                    )
                    await self._execute_upsert(conn, sql, values)
        return documents

    async def get_by_id(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fetch one document by ID."""
        container = self._normalize_container(container)
        table = TABLE_NAMES[container]
        select_clause = ", ".join(SELECT_FIELDS[container])
        sql = f"SELECT {select_clause} FROM {table} WHERE id = $1"
        row = await self._pool.fetchrow(sql, document_id)
        return None if row is None else self._record_to_dict(container, row)

    async def delete(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None,
    ) -> bool:
        """Delete a document by ID."""
        container = self._normalize_container(container)
        table = TABLE_NAMES[container]
        result = await self._pool.execute(f"DELETE FROM {table} WHERE id = $1", document_id)
        return result.endswith("1")

    async def query(
        self,
        container: ContainerType,
        filters: Dict[str, Any],
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query documents with equality filters."""
        container = self._normalize_container(container)
        self._validate_filter_keys(container, filters)
        table = TABLE_NAMES[container]
        select_clause = ", ".join(SELECT_FIELDS[container])
        where_clause, params, next_index = self._build_where_clause(filters, 1)

        order_clause = ""
        if order_by:
            field_name, direction = self._parse_order_by(order_by)
            order_clause = f" ORDER BY {field_name} {direction}"

        limit_clause = ""
        if limit is not None:
            limit_clause = f" LIMIT ${next_index}"
            params.append(limit)

        sql = f"SELECT {select_clause} FROM {table}{where_clause}{order_clause}{limit_clause}"
        rows = await self._pool.fetch(sql, *params)
        return [self._record_to_dict(container, row) for row in rows]

    async def vector_search(
        self,
        container: ContainerType,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Perform pgvector cosine search."""
        container = self._normalize_container(container)
        self._validate_filter_keys(container, filters)
        table = TABLE_NAMES[container]
        select_clause = ", ".join(SELECT_FIELDS[container])
        params: List[Any] = [self._vector_literal(query_embedding)]
        where_clause, filter_params, next_index = self._build_where_clause(filters or {}, 2)
        params.extend(filter_params)
        params.append(top_k)
        sql = (
            f"SELECT {select_clause}, "
            f"(1 - ({vector_field} <=> $1::vector)) AS similarity_score "
            f"FROM {table}"
            f"{where_clause} "
            f"ORDER BY {vector_field} <=> $1::vector "
            f"LIMIT ${next_index}"
        )
        rows = await self._pool.fetch(sql, *params)
        return [
            SearchResult(
                id=row["id"],
                document=self._record_to_dict(container, row),
                score=float(row["similarity_score"] or 0.0),
                score_type="similarity",
            )
            for row in rows
        ]

    async def hybrid_search(
        self,
        container: ContainerType,
        query_text: str,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        text_fields: Optional[List[str]] = None,
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Combine pgvector cosine similarity with PostgreSQL full-text ranking."""
        container = self._normalize_container(container)
        self._validate_filter_keys(container, filters)
        table = TABLE_NAMES[container]
        select_clause = ", ".join(SELECT_FIELDS[container])
        text_expr = HYBRID_TEXT_EXPRESSIONS[container]
        params: List[Any] = [query_text, self._vector_literal(query_embedding)]
        where_clause, filter_params, next_index = self._build_where_clause(filters or {}, 3)
        params.extend(filter_params)
        params.append(top_k)
        sql = f"""
            WITH ranked AS (
                SELECT
                    {select_clause},
                    ts_rank_cd(
                        to_tsvector('english', {text_expr}),
                        plainto_tsquery('english', $1)
                    ) AS text_score,
                    (1 - ({vector_field} <=> $2::vector)) AS vector_score
                FROM {table}
                {where_clause}
            )
            SELECT *,
                ((COALESCE(text_score, 0) * 0.35) + (COALESCE(vector_score, 0) * 0.65)) AS hybrid_score
            FROM ranked
            ORDER BY hybrid_score DESC
            LIMIT ${next_index}
        """
        rows = await self._pool.fetch(sql, *params)
        return [
            SearchResult(
                id=row["id"],
                document=self._record_to_dict(container, row),
                score=float(row["hybrid_score"] or 0.0),
                score_type="hybrid",
            )
            for row in rows
        ]

    def _prepare_document(self, container: ContainerType, document: Dict[str, Any]) -> Dict[str, Any]:
        """Convert app document to PostgreSQL-friendly values."""
        container = self._normalize_container(container)
        prepared = dict(document)
        for key in VECTOR_FIELDS[container]:
            value = prepared.get(key)
            if value is not None:
                prepared[key] = self._vector_literal(value)
        for key in JSON_FIELDS[container]:
            if key in prepared and prepared[key] is not None:
                prepared[key] = json.dumps(prepared[key])
        return prepared

    def _build_upsert_values(
        self,
        container: ContainerType,
        prepared: Dict[str, Any],
    ) -> tuple[List[str], List[str], List[Any]]:
        """Build column metadata for one upsert statement."""
        container = self._normalize_container(container)
        columns = list(prepared.keys())
        placeholders: List[str] = []
        values: List[Any] = []

        for index, column in enumerate(columns, start=1):
            value = prepared[column]
            values.append(value)
            if column in VECTOR_FIELDS[container] and value is not None:
                placeholders.append(f"${index}::vector")
            elif column in JSON_FIELDS[container]:
                placeholders.append(f"${index}::jsonb")
            else:
                placeholders.append(f"${index}")

        return columns, placeholders, values

    def _validate_filter_keys(self, container: ContainerType, filters: Optional[Dict[str, Any]]) -> None:
        """Reject unsupported filter keys early."""
        container = self._normalize_container(container)
        if not filters:
            return
        unknown = sorted(set(filters) - FILTERABLE_FIELDS[container])
        if unknown:
            raise ValueError(f"Unsupported filter keys for {container.value}: {', '.join(unknown)}")

    def _build_where_clause(self, filters: Dict[str, Any], start_index: int) -> tuple[str, List[Any], int]:
        """Build a parameterized WHERE clause."""
        clauses: List[str] = []
        params: List[Any] = []
        next_index = start_index

        for key, value in filters.items():
            if value is None:
                clauses.append(f"{key} IS NULL")
                continue
            clauses.append(f"{key} = ${next_index}")
            params.append(value)
            next_index += 1

        if not clauses:
            return "", params, next_index
        return " WHERE " + " AND ".join(clauses), params, next_index

    def _parse_order_by(self, order_by: str) -> tuple[str, str]:
        """Convert repo order syntax into SQL order syntax."""
        descending = order_by.startswith("-")
        field_name = order_by[1:] if descending else order_by
        return field_name, "DESC" if descending else "ASC"

    def _record_to_dict(self, container: ContainerType, row: Any) -> Dict[str, Any]:
        """Normalize an asyncpg record into app document form."""
        container = self._normalize_container(container)
        data = dict(row)
        for key in VECTOR_FIELDS[container]:
            if key in data and data[key] is not None:
                data[key] = self._parse_vector(data[key])
        for key in JSON_FIELDS[container]:
            value = data.get(key)
            if isinstance(value, str):
                data[key] = json.loads(value)
        return data

    async def _execute_upsert(self, conn: Any, sql: str, values: List[Any]) -> None:
        """Execute one prepared upsert statement."""
        await conn.execute(sql, *values)

    async def _normalize_document_for_upsert(
        self,
        conn: Any,
        container: ContainerType,
        document: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fill backend-required fields for partial upserts."""
        container = self._normalize_container(container)
        normalized = dict(document)
        now = self._utcnow_iso()
        existing = None

        missing_required = REQUIRED_FIELDS[container] - set(normalized)
        if missing_required:
            existing = await self._fetch_existing_document(conn, container, normalized["id"])
            if existing:
                for key, value in existing.items():
                    normalized.setdefault(key, value)

        normalized.setdefault("created_at", now)
        normalized.setdefault("updated_at", now)
        if container == ContainerType.SESSION_SUMMARIES:
            normalized.setdefault("start_time", now)
        return normalized

    async def _fetch_existing_document(
        self,
        conn: Any,
        container: ContainerType,
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Fetch an existing document for merge-style upserts."""
        container = self._normalize_container(container)
        table = TABLE_NAMES[container]
        select_clause = ", ".join(SELECT_FIELDS[container])
        row = await conn.fetchrow(f"SELECT {select_clause} FROM {table} WHERE id = $1", document_id)
        return None if row is None else self._record_to_dict(container, row)

    def _normalize_container(self, container: ContainerType | str) -> ContainerType:
        """Normalize enum instances that may come from reloaded modules."""
        if isinstance(container, ContainerType):
            return container
        return ContainerType(getattr(container, "value", container))

    def _utcnow_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _vector_literal(self, values: List[float]) -> str:
        """Serialize a Python vector into pgvector literal syntax."""
        return "[" + ",".join(str(value) for value in values) + "]"

    def _parse_vector(self, value: Any) -> List[float]:
        """Parse a pgvector text value back into a Python list."""
        if isinstance(value, list):
            return [float(item) for item in value]
        text = str(value).strip()
        if text.startswith("[") and text.endswith("]"):
            inner = text[1:-1].strip()
            if not inner:
                return []
            return [float(item.strip()) for item in inner.split(",")]
        return [float(text)]
