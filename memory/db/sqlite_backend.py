"""
SQLite Backend with sqlite-vec for Vector Search.

This backend provides a serverless, file-based memory database using SQLite
with the sqlite-vec extension for vector similarity search.

Features:
- No server required (embedded database)
- Vector search via sqlite-vec extension  
- Persistent storage in a single file
- Good for development and single-user scenarios

Note: Does not support hybrid search - falls back to vector-only search.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from memory.db.base import (
    ContainerType,
    DatabaseCapabilities,
    EmbeddingProvider,
    MemoryDatabase,
    SearchResult,
)


# SQL schemas for each container
SCHEMAS = {
    ContainerType.INTERACTIONS: """
        CREATE TABLE IF NOT EXISTS interactions (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            session_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            content TEXT NOT NULL,
            summary TEXT,
            metadata TEXT,  -- JSON blob
            content_vector BLOB,  -- sqlite-vec vector
            summary_vector BLOB,  -- sqlite-vec vector
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_interactions_user ON interactions(user_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_session ON interactions(session_id);
        CREATE INDEX IF NOT EXISTS idx_interactions_timestamp ON interactions(timestamp);
    """,
    ContainerType.INSIGHTS: """
        CREATE TABLE IF NOT EXISTS insights (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            insight_type TEXT NOT NULL,  -- 'session' or 'long_term'
            session_ids TEXT,  -- JSON array
            insight_text TEXT NOT NULL,
            insight_vector BLOB,  -- sqlite-vec vector
            confidence REAL,
            importance TEXT,
            category TEXT,
            reflection_flag TEXT,
            processed INTEGER DEFAULT 0,  -- boolean as int
            source_insight_ids TEXT,  -- JSON array for long_term
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_insights_user ON insights(user_id);
        CREATE INDEX IF NOT EXISTS idx_insights_type ON insights(insight_type);
        CREATE INDEX IF NOT EXISTS idx_insights_processed ON insights(processed);
    """,
    ContainerType.SESSION_SUMMARIES: """
        CREATE TABLE IF NOT EXISTS session_summaries (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT,
            summary TEXT DEFAULT '',
            summary_vector BLOB,  -- sqlite-vec vector
            key_topics TEXT,  -- JSON array
            extracted_insights TEXT,  -- JSON array
            status TEXT DEFAULT 'active',
            reflection_status TEXT DEFAULT 'pending',
            cumulative_summary TEXT DEFAULT '',  -- Running session summary
            turn_count INTEGER DEFAULT 0,  -- Number of turns in session
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_summaries_user ON session_summaries(user_id);
        CREATE INDEX IF NOT EXISTS idx_summaries_status ON session_summaries(status);
    """,
}


def _serialize_vector(vector: List[float]) -> bytes:
    """Serialize a vector to bytes for sqlite-vec storage."""
    import struct
    return struct.pack(f'{len(vector)}f', *vector)


def _deserialize_vector(data: bytes) -> List[float]:
    """Deserialize bytes back to a vector."""
    import struct
    count = len(data) // 4  # 4 bytes per float32
    return list(struct.unpack(f'{count}f', data))


class SQLiteDatabase(MemoryDatabase):
    """
    SQLite backend for Agent Memory Service.
    
    Uses sqlite-vec extension for vector similarity search.
    Falls back to cosine similarity in Python if extension not available.
    """
    
    def __init__(
        self,
        db_path: str = "agent_memory.db",
        embedding_provider: Optional[EmbeddingProvider] = None,
        vector_dimensions: int = 1536
    ):
        """
        Initialize SQLite database backend.
        
        Args:
            db_path: Path to SQLite database file
            embedding_provider: Provider for generating embeddings
            vector_dimensions: Dimension of embedding vectors (default: 1536)
        """
        super().__init__(embedding_provider)
        self.db_path = Path(db_path)
        self.vector_dimensions = vector_dimensions
        self._conn: Optional[sqlite3.Connection] = None
        self._vec_available = False
    
    async def initialize(self) -> None:
        """Initialize database and create tables."""
        # Ensure parent directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Connect to database
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        
        # Try to load sqlite-vec extension
        self._vec_available = self._try_load_vec_extension()
        
        # Create tables
        for container_type, schema in SCHEMAS.items():
            self._conn.executescript(schema)
        
        # Create virtual tables for vector search if extension available
        if self._vec_available:
            self._create_vector_indexes()
        
        self._conn.commit()
    
    def _try_load_vec_extension(self) -> bool:
        """Try to load sqlite-vec extension."""
        try:
            # First try the sqlite-vec Python package (preferred method)
            try:
                import sqlite_vec
                self._conn.enable_load_extension(True)
                sqlite_vec.load(self._conn)
                self._conn.enable_load_extension(False)
                print("Loaded sqlite-vec via Python package")
                return True
            except ImportError:
                pass
            except Exception as e:
                print(f"sqlite-vec package load failed: {e}")
            
            # Fallback: try manual extension loading
            self._conn.enable_load_extension(True)
            # Try common locations for sqlite-vec
            ext_paths = [
                "vec0",  # Installed in PATH
                "./vec0",
                "./sqlite-vec/vec0",
                os.path.expanduser("~/.local/lib/vec0"),
            ]
            for ext_path in ext_paths:
                try:
                    self._conn.load_extension(ext_path)
                    print(f"Loaded sqlite-vec from {ext_path}")
                    return True
                except sqlite3.OperationalError:
                    continue
            print("sqlite-vec extension not found, using Python fallback for vector search")
            return False
        except Exception as e:
            print(f"Could not enable extensions: {e}")
            return False
    
    def _create_vector_indexes(self) -> None:
        """Create virtual tables for vector search using sqlite-vec."""
        # Note: sqlite-vec uses virtual tables for vector indexing
        # Create virtual tables linked to main tables
        try:
            # Create vector index for interactions content
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_interactions_content
                USING vec0(
                    id TEXT PRIMARY KEY,
                    content_vector float[{self.vector_dimensions}]
                );
            """)
            
            # Create vector index for interactions summary
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_interactions_summary
                USING vec0(
                    id TEXT PRIMARY KEY,
                    summary_vector float[{self.vector_dimensions}]
                );
            """)
            
            # Create vector index for insights
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_insights
                USING vec0(
                    id TEXT PRIMARY KEY,
                    insight_vector float[{self.vector_dimensions}]
                );
            """)
            
            # Create vector index for session summaries
            self._conn.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS vec_summaries
                USING vec0(
                    id TEXT PRIMARY KEY,
                    summary_vector float[{self.vector_dimensions}]
                );
            """)
            
            self._conn.commit()
        except sqlite3.OperationalError as e:
            print(f"Could not create vector indexes: {e}")
            self._vec_available = False
    
    async def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def get_capabilities(self) -> DatabaseCapabilities:
        """Get database capabilities."""
        return DatabaseCapabilities(
            supports_vector_search=True,  # Always supported (with or without extension)
            supports_hybrid_search=False,  # SQLite doesn't support hybrid
            supports_full_text_search=False,  # Could add FTS5 later
            supports_transactions=True,
            vector_dimensions=self.vector_dimensions,
            max_batch_size=500,
            backend_name="sqlite",
            backend_version="sqlite-vec" if self._vec_available else "python-fallback"
        )
    
    def _get_table_name(self, container: ContainerType) -> str:
        """Get table name for container type."""
        return container.value
    
    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        """Convert SQLite row to dictionary, parsing JSON fields."""
        result = dict(row)
        
        # Parse JSON fields
        json_fields = ["metadata", "session_ids", "key_topics", 
                       "extracted_insights", "source_insight_ids"]
        for field in json_fields:
            if field in result and result[field]:
                try:
                    result[field] = json.loads(result[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        
        # Convert processed from int to bool
        if "processed" in result:
            result["processed"] = bool(result["processed"])
        
        # Don't return vector blobs in regular queries
        for key in list(result.keys()):
            if key.endswith("_vector") and isinstance(result[key], bytes):
                del result[key]
        
        return result
    
    async def upsert(
        self,
        container: ContainerType,
        document: Dict[str, Any],
        partition_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Insert or update a document."""
        if "id" not in document:
            raise ValueError("Document must have an 'id' field")
        
        table = self._get_table_name(container)
        doc = document.copy()
        
        # Set timestamps
        now = datetime.utcnow().isoformat()
        doc["updated_at"] = now
        if "created_at" not in doc:
            doc["created_at"] = now
        
        # Serialize JSON fields
        json_fields = ["metadata", "session_ids", "key_topics",
                       "extracted_insights", "source_insight_ids"]
        for field in json_fields:
            if field in doc and doc[field] is not None:
                if isinstance(doc[field], (list, dict)):
                    doc[field] = json.dumps(doc[field])
        
        # Serialize vector fields
        vector_fields = ["content_vector", "summary_vector", "insight_vector"]
        for field in vector_fields:
            if field in doc and doc[field] is not None:
                if isinstance(doc[field], list):
                    doc[field] = _serialize_vector(doc[field])
        
        # Convert boolean to int
        if "processed" in doc:
            doc["processed"] = 1 if doc["processed"] else 0
        
        # Build upsert query
        columns = list(doc.keys())
        placeholders = ["?" for _ in columns]
        updates = [f"{col} = excluded.{col}" for col in columns if col != "id"]
        
        query = f"""
            INSERT INTO {table} ({', '.join(columns)})
            VALUES ({', '.join(placeholders)})
            ON CONFLICT(id) DO UPDATE SET {', '.join(updates)}
        """
        
        self._conn.execute(query, [doc[col] for col in columns])
        self._conn.commit()
        
        # Update vector index if available
        if self._vec_available:
            await self._update_vector_index(container, doc)
        
        return document
    
    async def _update_vector_index(
        self,
        container: ContainerType,
        doc: Dict[str, Any]
    ) -> None:
        """Update vector indexes for a document."""
        doc_id = doc["id"]
        
        if container == ContainerType.INTERACTIONS:
            if "content_vector" in doc and doc["content_vector"]:
                # vec0 virtual tables may not support INSERT OR REPLACE
                # Delete first, then insert
                self._conn.execute("DELETE FROM vec_interactions_content WHERE id = ?", (doc_id,))
                self._conn.execute("""
                    INSERT INTO vec_interactions_content(id, content_vector)
                    VALUES (?, ?)
                """, (doc_id, doc["content_vector"]))
            if "summary_vector" in doc and doc["summary_vector"]:
                self._conn.execute("DELETE FROM vec_interactions_summary WHERE id = ?", (doc_id,))
                self._conn.execute("""
                    INSERT INTO vec_interactions_summary(id, summary_vector)
                    VALUES (?, ?)
                """, (doc_id, doc["summary_vector"]))
        
        elif container == ContainerType.INSIGHTS:
            if "insight_vector" in doc and doc["insight_vector"]:
                self._conn.execute("DELETE FROM vec_insights WHERE id = ?", (doc_id,))
                self._conn.execute("""
                    INSERT INTO vec_insights(id, insight_vector)
                    VALUES (?, ?)
                """, (doc_id, doc["insight_vector"]))
        
        elif container == ContainerType.SESSION_SUMMARIES:
            if "summary_vector" in doc and doc["summary_vector"]:
                # vec0 virtual tables may not support INSERT OR REPLACE
                # Delete first, then insert
                self._conn.execute("DELETE FROM vec_summaries WHERE id = ?", (doc_id,))
                self._conn.execute("""
                    INSERT INTO vec_summaries(id, summary_vector)
                    VALUES (?, ?)
                """, (doc_id, doc["summary_vector"]))
        
        self._conn.commit()
    
    async def batch_upsert(
        self,
        container: ContainerType,
        documents: List[Dict[str, Any]],
        partition_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Insert or update multiple documents."""
        results = []
        for doc in documents:
            result = await self.upsert(container, doc, partition_key)
            results.append(result)
        return results
    
    async def get_by_id(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get document by ID."""
        table = self._get_table_name(container)
        cursor = self._conn.execute(
            f"SELECT * FROM {table} WHERE id = ?",
            (document_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_dict(row)
        return None
    
    async def delete(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None
    ) -> bool:
        """Delete document by ID."""
        table = self._get_table_name(container)
        cursor = self._conn.execute(
            f"DELETE FROM {table} WHERE id = ?",
            (document_id,)
        )
        self._conn.commit()
        
        # Also delete from vector indexes
        if self._vec_available:
            await self._delete_from_vector_index(container, document_id)
        
        return cursor.rowcount > 0
    
    async def _delete_from_vector_index(
        self,
        container: ContainerType,
        document_id: str
    ) -> None:
        """Delete from vector indexes."""
        if container == ContainerType.INTERACTIONS:
            self._conn.execute(
                "DELETE FROM vec_interactions_content WHERE id = ?",
                (document_id,)
            )
            self._conn.execute(
                "DELETE FROM vec_interactions_summary WHERE id = ?",
                (document_id,)
            )
        elif container == ContainerType.INSIGHTS:
            self._conn.execute(
                "DELETE FROM vec_insights WHERE id = ?",
                (document_id,)
            )
        elif container == ContainerType.SESSION_SUMMARIES:
            self._conn.execute(
                "DELETE FROM vec_summaries WHERE id = ?",
                (document_id,)
            )
        self._conn.commit()
    
    async def query(
        self,
        container: ContainerType,
        filters: Dict[str, Any],
        order_by: Optional[str] = None,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Query documents with filters."""
        table = self._get_table_name(container)
        
        # Build WHERE clause
        conditions = []
        params = []
        for key, value in filters.items():
            if value is None:
                conditions.append(f"{key} IS NULL")
            else:
                conditions.append(f"{key} = ?")
                params.append(value)
        
        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)
        
        # Build ORDER BY clause
        order_clause = ""
        if order_by:
            if order_by.startswith("-"):
                order_clause = f"ORDER BY {order_by[1:]} DESC"
            else:
                order_clause = f"ORDER BY {order_by} ASC"
        
        # Build LIMIT clause
        limit_clause = ""
        if limit:
            limit_clause = f"LIMIT {limit}"
        
        query = f"SELECT * FROM {table} {where_clause} {order_clause} {limit_clause}"
        
        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()
        
        return [self._row_to_dict(row) for row in rows]
    
    async def vector_search(
        self,
        container: ContainerType,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[SearchResult]:
        """Perform vector similarity search."""
        if self._vec_available:
            return await self._vector_search_native(
                container, query_embedding, vector_field, top_k, filters
            )
        else:
            return await self._vector_search_fallback(
                container, query_embedding, vector_field, top_k, filters
            )
    
    async def _vector_search_native(
        self,
        container: ContainerType,
        query_embedding: List[float],
        vector_field: str,
        top_k: int,
        filters: Optional[Dict[str, Any]]
    ) -> List[SearchResult]:
        """Vector search using sqlite-vec extension."""
        table = self._get_table_name(container)
        
        # Determine which vector index to use
        if container == ContainerType.INTERACTIONS:
            if vector_field == "summary_vector":
                vec_table = "vec_interactions_summary"
            else:
                vec_table = "vec_interactions_content"
        elif container == ContainerType.INSIGHTS:
            vec_table = "vec_insights"
            vector_field = "insight_vector"
        else:
            vec_table = "vec_summaries"
            vector_field = "summary_vector"
        
        # Serialize query vector
        query_blob = _serialize_vector(query_embedding)
        
        # Build query with KNN search
        # sqlite-vec uses: SELECT ... FROM vec_table WHERE ... ORDER BY distance
        filter_clause = ""
        params = [query_blob, top_k]
        
        if filters:
            filter_conditions = []
            for key, value in filters.items():
                filter_conditions.append(f"t.{key} = ?")
                params.append(value)
            if filter_conditions:
                filter_clause = "WHERE " + " AND ".join(filter_conditions)
        
        query = f"""
            SELECT t.*, v.distance
            FROM {vec_table} v
            JOIN {table} t ON v.id = t.id
            {filter_clause}
            WHERE v.{vector_field} MATCH ?
            ORDER BY v.distance
            LIMIT ?
        """
        
        try:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                doc = self._row_to_dict(row)
                # Convert distance to similarity (1 - distance for cosine)
                distance = row["distance"] if "distance" in row.keys() else 0
                similarity = 1.0 - distance
                results.append(SearchResult(
                    id=doc["id"],
                    document=doc,
                    score=similarity,
                    score_type="similarity"
                ))
            
            return results
        except sqlite3.OperationalError:
            # Fallback if query fails
            return await self._vector_search_fallback(
                container, query_embedding, vector_field, top_k, filters
            )
    
    async def _vector_search_fallback(
        self,
        container: ContainerType,
        query_embedding: List[float],
        vector_field: str,
        top_k: int,
        filters: Optional[Dict[str, Any]]
    ) -> List[SearchResult]:
        """Vector search using Python cosine similarity (fallback)."""
        import math
        
        table = self._get_table_name(container)
        
        # Build filter clause
        filter_clause = ""
        params = []
        if filters:
            conditions = [f"{key} = ?" for key in filters.keys()]
            filter_clause = "WHERE " + " AND ".join(conditions)
            params = list(filters.values())
        
        # Get all documents with vectors
        query = f"SELECT *, {vector_field} as vec FROM {table} {filter_clause}"
        cursor = self._conn.execute(query, params)
        rows = cursor.fetchall()
        
        # Calculate cosine similarity for each
        results = []
        query_norm = math.sqrt(sum(x * x for x in query_embedding))
        
        for row in rows:
            vec_blob = row["vec"]
            if vec_blob is None:
                continue
            
            doc_vec = _deserialize_vector(vec_blob)
            
            # Cosine similarity
            dot_product = sum(a * b for a, b in zip(query_embedding, doc_vec))
            doc_norm = math.sqrt(sum(x * x for x in doc_vec))
            
            if query_norm > 0 and doc_norm > 0:
                similarity = dot_product / (query_norm * doc_norm)
            else:
                similarity = 0.0
            
            doc = self._row_to_dict(row)
            results.append(SearchResult(
                id=doc["id"],
                document=doc,
                score=similarity,
                score_type="similarity"
            ))
        
        # Sort by similarity descending
        results.sort(key=lambda x: x.score, reverse=True)
        
        return results[:top_k]
