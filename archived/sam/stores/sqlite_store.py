"""
SQLite Memory Store Implementation

Local-first storage backend using:
- SQLite for relational data
- FTS5 for full-text search
- sqlite-vec for vector similarity search

This is the default storage engine for SAM.
"""

import asyncio
import sqlite3
import json
import math
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Union, Tuple
from contextlib import asynccontextmanager

from sam.stores.base import BaseMemoryStore
from sam.models.graph import (
    NodeType,
    EdgeType,
    Episode,
    EpisodeCreate,
    Entity,
    EntityCreate,
    Claim,
    ClaimCreate,
    ClaimKind,
    Insight,
    InsightCreate,
    Procedure,
    ProcedureCreate,
    ProcedureStatus,
    Edge,
    EdgeCreate,
    AnchorResult,
)


def _serialize_embedding(embedding: Optional[List[float]]) -> Optional[bytes]:
    """Serialize embedding to bytes for sqlite-vec storage."""
    if embedding is None:
        return None
    import struct
    return struct.pack(f'{len(embedding)}f', *embedding)


def _deserialize_embedding(data: Optional[bytes]) -> Optional[List[float]]:
    """Deserialize embedding from bytes."""
    if data is None:
        return None
    import struct
    n = len(data) // 4
    return list(struct.unpack(f'{n}f', data))


class SQLiteMemoryStore(BaseMemoryStore):
    """
    SQLite-based implementation of MemoryStore.
    
    Uses synchronous sqlite3 wrapped in asyncio for simplicity.
    For high-concurrency production use, consider aiosqlite.
    """
    
    def __init__(self, database_url: str = "sqlite:///sam_memory.db"):
        """
        Initialize SQLite store.
        
        Args:
            database_url: SQLite URL (sqlite:///path/to/db.db or :memory:)
        """
        super().__init__(database_url)
        
        # Parse database path from URL
        if database_url.startswith("sqlite:///"):
            self.db_path = database_url[10:]
        elif database_url == ":memory:":
            self.db_path = ":memory:"
        else:
            self.db_path = database_url
        
        self._conn: Optional[sqlite3.Connection] = None
        self._vec_available = False
    
    def _get_conn(self) -> sqlite3.Connection:
        """Get or create connection."""
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA journal_mode = WAL")
        return self._conn
    
    async def initialize(self) -> None:
        """Create database schema and indexes."""
        if self._initialized:
            return
        
        conn = self._get_conn()
        
        # Try to load sqlite-vec extension
        try:
            conn.enable_load_extension(True)
            # Try common locations for sqlite-vec
            for vec_path in ["vec0", "sqlite-vec", "./vec0.so", "./vec0.dll"]:
                try:
                    conn.load_extension(vec_path)
                    self._vec_available = True
                    break
                except sqlite3.OperationalError:
                    continue
        except Exception:
            pass  # Extension loading not supported
        
        # Create tables
        conn.executescript("""
            -- Episodes table
            CREATE TABLE IF NOT EXISTS episodes (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                raw_content TEXT DEFAULT '',
                summary TEXT,
                token_count INTEGER DEFAULT 0,
                turn_count INTEGER DEFAULT 0,
                is_open INTEGER DEFAULT 1,
                key_topics TEXT DEFAULT '[]',
                embedding BLOB,
                strength REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_episodes_tenant ON episodes(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_episodes_tenant_open ON episodes(tenant_id, is_open);
            CREATE INDEX IF NOT EXISTS idx_episodes_created ON episodes(created_at);
            
            -- Entities table
            CREATE TABLE IF NOT EXISTS entities (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                aliases TEXT DEFAULT '[]',
                mention_count INTEGER DEFAULT 0,
                embedding BLOB,
                strength REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_entities_tenant ON entities(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_entities_tenant_name ON entities(tenant_id, name);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_entities_tenant_name_type 
                ON entities(tenant_id, name, entity_type);
            
            -- Claims table
            CREATE TABLE IF NOT EXISTS claims (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                content TEXT NOT NULL,
                claim_kind TEXT DEFAULT 'stable',
                confidence REAL DEFAULT 0.5,
                evidence_count INTEGER DEFAULT 1,
                source_episode_id TEXT,
                embedding BLOB,
                strength REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                FOREIGN KEY (source_episode_id) REFERENCES episodes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_claims_tenant ON claims(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_claims_episode ON claims(source_episode_id);
            
            -- Insights table
            CREATE TABLE IF NOT EXISTS insights (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                content TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                validation_count INTEGER DEFAULT 0,
                source_claim_ids TEXT DEFAULT '[]',
                embedding BLOB,
                strength REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_insights_tenant ON insights(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_insights_confidence ON insights(tenant_id, confidence);
            
            -- Procedures table
            CREATE TABLE IF NOT EXISTS procedures (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                steps TEXT DEFAULT '[]',
                status TEXT DEFAULT 'candidate',
                source_insight_ids TEXT DEFAULT '[]',
                execution_count INTEGER DEFAULT 0,
                success_count INTEGER DEFAULT 0,
                embedding BLOB,
                strength REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                last_accessed TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_procedures_tenant ON procedures(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_procedures_status ON procedures(tenant_id, status);
            
            -- Edges table
            CREATE TABLE IF NOT EXISTS edges (
                id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                edge_type TEXT NOT NULL,
                weight REAL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_edges_tenant ON edges(tenant_id);
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_type ON edges(edge_type);
        """)
        
        # Create FTS5 virtual tables for full-text search (standalone, not external content)
        # Using standalone FTS tables avoids issues with external content sync
        conn.executescript("""
            -- FTS for episodes
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts USING fts5(
                id, raw_content, summary, key_topics
            );
            
            -- FTS for entities
            CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
                id, name, aliases
            );
            
            -- FTS for claims
            CREATE VIRTUAL TABLE IF NOT EXISTS claims_fts USING fts5(
                id, content
            );
            
            -- FTS for insights
            CREATE VIRTUAL TABLE IF NOT EXISTS insights_fts USING fts5(
                id, content
            );
        """)
        
        # Create triggers to keep FTS in sync (using DELETE+INSERT for updates)
        conn.executescript("""
            -- Episode FTS triggers
            CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
                INSERT INTO episodes_fts(id, raw_content, summary, key_topics) 
                VALUES (new.id, new.raw_content, new.summary, new.key_topics);
            END;
            CREATE TRIGGER IF NOT EXISTS episodes_au AFTER UPDATE ON episodes BEGIN
                DELETE FROM episodes_fts WHERE id = old.id;
                INSERT INTO episodes_fts(id, raw_content, summary, key_topics) 
                VALUES (new.id, new.raw_content, new.summary, new.key_topics);
            END;
            CREATE TRIGGER IF NOT EXISTS episodes_ad AFTER DELETE ON episodes BEGIN
                DELETE FROM episodes_fts WHERE id = old.id;
            END;
            
            -- Entity FTS triggers
            CREATE TRIGGER IF NOT EXISTS entities_ai AFTER INSERT ON entities BEGIN
                INSERT INTO entities_fts(id, name, aliases) 
                VALUES (new.id, new.name, new.aliases);
            END;
            CREATE TRIGGER IF NOT EXISTS entities_au AFTER UPDATE ON entities BEGIN
                DELETE FROM entities_fts WHERE id = old.id;
                INSERT INTO entities_fts(id, name, aliases) 
                VALUES (new.id, new.name, new.aliases);
            END;
            CREATE TRIGGER IF NOT EXISTS entities_ad AFTER DELETE ON entities BEGIN
                DELETE FROM entities_fts WHERE id = old.id;
            END;
            
            -- Claim FTS triggers
            CREATE TRIGGER IF NOT EXISTS claims_ai AFTER INSERT ON claims BEGIN
                INSERT INTO claims_fts(id, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS claims_au AFTER UPDATE ON claims BEGIN
                DELETE FROM claims_fts WHERE id = old.id;
                INSERT INTO claims_fts(id, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS claims_ad AFTER DELETE ON claims BEGIN
                DELETE FROM claims_fts WHERE id = old.id;
            END;
            
            -- Insight FTS triggers
            CREATE TRIGGER IF NOT EXISTS insights_ai AFTER INSERT ON insights BEGIN
                INSERT INTO insights_fts(id, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS insights_au AFTER UPDATE ON insights BEGIN
                DELETE FROM insights_fts WHERE id = old.id;
                INSERT INTO insights_fts(id, content) VALUES (new.id, new.content);
            END;
            CREATE TRIGGER IF NOT EXISTS insights_ad AFTER DELETE ON insights BEGIN
                DELETE FROM insights_fts WHERE id = old.id;
            END;
        """)
        
        conn.commit()
        self._initialized = True
    
    async def close(self) -> None:
        """Close database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        self._initialized = False
    
    # =========================================================================
    # Episode Operations
    # =========================================================================
    
    async def create_episode(self, episode: EpisodeCreate) -> Episode:
        """Create a new Episode."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        ep = Episode(
            tenant_id=episode.tenant_id,
            source=episode.source,
            metadata=episode.metadata,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
        )
        
        conn.execute("""
            INSERT INTO episodes (id, tenant_id, source, raw_content, summary,
                token_count, turn_count, is_open, key_topics, embedding, strength,
                created_at, last_accessed, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ep.id, ep.tenant_id, ep.source, ep.raw_content, ep.summary,
            ep.token_count, ep.turn_count, 1 if ep.is_open else 0,
            json.dumps(ep.key_topics), None, ep.strength,
            now, now, json.dumps(ep.metadata)
        ))
        conn.commit()
        
        return ep
    
    async def get_episode(self, episode_id: str, tenant_id: str) -> Optional[Episode]:
        """Get Episode by ID."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM episodes WHERE id = ? AND tenant_id = ?
        """, (episode_id, tenant_id)).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_episode(row)
    
    async def get_open_episode(self, tenant_id: str) -> Optional[Episode]:
        """Get the current open Episode for a tenant."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM episodes 
            WHERE tenant_id = ? AND is_open = 1
            ORDER BY created_at DESC LIMIT 1
        """, (tenant_id,)).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_episode(row)
    
    async def append_to_episode(
        self, 
        episode_id: str, 
        tenant_id: str,
        content: str, 
        token_count: int,
        turn_count: int = 1
    ) -> Episode:
        """Append content to an open Episode."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        # Get current episode
        ep = await self.get_episode(episode_id, tenant_id)
        if ep is None:
            raise ValueError(f"Episode {episode_id} not found")
        if not ep.is_open:
            raise ValueError(f"Episode {episode_id} is closed")
        
        # Append content
        new_content = ep.raw_content + ("\n" if ep.raw_content else "") + content
        new_token_count = ep.token_count + token_count
        new_turn_count = ep.turn_count + turn_count
        
        conn.execute("""
            UPDATE episodes 
            SET raw_content = ?, token_count = ?, turn_count = ?, last_accessed = ?
            WHERE id = ? AND tenant_id = ?
        """, (new_content, new_token_count, new_turn_count, now, episode_id, tenant_id))
        conn.commit()
        
        ep.raw_content = new_content
        ep.token_count = new_token_count
        ep.turn_count = new_turn_count
        ep.last_accessed = datetime.fromisoformat(now)
        
        return ep
    
    async def close_episode(
        self, 
        episode_id: str, 
        tenant_id: str,
        summary: Optional[str] = None,
        key_topics: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None
    ) -> Episode:
        """Close an Episode."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        conn.execute("""
            UPDATE episodes 
            SET is_open = 0, summary = ?, key_topics = ?, embedding = ?, last_accessed = ?
            WHERE id = ? AND tenant_id = ?
        """, (
            summary, 
            json.dumps(key_topics or []),
            _serialize_embedding(embedding),
            now,
            episode_id, 
            tenant_id
        ))
        conn.commit()
        
        return await self.get_episode(episode_id, tenant_id)
    
    async def list_episodes(
        self, 
        tenant_id: str, 
        limit: int = 10,
        include_open: bool = True
    ) -> List[Episode]:
        """List recent Episodes."""
        conn = self._get_conn()
        
        if include_open:
            query = """
                SELECT * FROM episodes WHERE tenant_id = ?
                ORDER BY created_at DESC LIMIT ?
            """
            rows = conn.execute(query, (tenant_id, limit)).fetchall()
        else:
            query = """
                SELECT * FROM episodes WHERE tenant_id = ? AND is_open = 0
                ORDER BY created_at DESC LIMIT ?
            """
            rows = conn.execute(query, (tenant_id, limit)).fetchall()
        
        return [self._row_to_episode(row) for row in rows]
    
    def _row_to_episode(self, row: sqlite3.Row) -> Episode:
        """Convert database row to Episode model."""
        return Episode(
            id=row["id"],
            tenant_id=row["tenant_id"],
            node_type=NodeType.EPISODE,
            source=row["source"],
            raw_content=row["raw_content"] or "",
            summary=row["summary"],
            token_count=row["token_count"],
            turn_count=row["turn_count"],
            is_open=bool(row["is_open"]),
            key_topics=json.loads(row["key_topics"]) if row["key_topics"] else [],
            embedding=_deserialize_embedding(row["embedding"]),
            strength=row["strength"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed=datetime.fromisoformat(row["last_accessed"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    # =========================================================================
    # Entity Operations
    # =========================================================================
    
    async def create_entity(self, entity: EntityCreate) -> Entity:
        """Create a new Entity."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        ent = Entity(
            tenant_id=entity.tenant_id,
            name=entity.name,
            entity_type=entity.entity_type,
            aliases=entity.aliases,
            metadata=entity.metadata,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
        )
        
        conn.execute("""
            INSERT INTO entities (id, tenant_id, name, entity_type, aliases,
                mention_count, embedding, strength, created_at, last_accessed, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ent.id, ent.tenant_id, ent.name, ent.entity_type,
            json.dumps(ent.aliases), ent.mention_count, None, ent.strength,
            now, now, json.dumps(ent.metadata)
        ))
        conn.commit()
        
        return ent
    
    async def get_entity(self, entity_id: str, tenant_id: str) -> Optional[Entity]:
        """Get Entity by ID."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM entities WHERE id = ? AND tenant_id = ?
        """, (entity_id, tenant_id)).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_entity(row)
    
    async def find_entity_by_name(
        self, 
        name: str, 
        tenant_id: str,
        entity_type: Optional[str] = None
    ) -> Optional[Entity]:
        """Find Entity by name."""
        conn = self._get_conn()
        
        if entity_type:
            row = conn.execute("""
                SELECT * FROM entities 
                WHERE tenant_id = ? AND LOWER(name) = LOWER(?) AND entity_type = ?
            """, (tenant_id, name, entity_type)).fetchone()
        else:
            row = conn.execute("""
                SELECT * FROM entities 
                WHERE tenant_id = ? AND LOWER(name) = LOWER(?)
            """, (tenant_id, name)).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_entity(row)
    
    async def get_or_create_entity(
        self,
        name: str,
        entity_type: str,
        tenant_id: str,
        aliases: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Entity:
        """Get existing Entity or create new one."""
        existing = await self.find_entity_by_name(name, tenant_id, entity_type)
        if existing:
            return existing
        
        return await self.create_entity(EntityCreate(
            tenant_id=tenant_id,
            name=name,
            entity_type=entity_type,
            aliases=aliases or [],
            metadata=metadata or {}
        ))
    
    async def update_entity_embedding(
        self,
        entity_id: str,
        tenant_id: str,
        embedding: List[float]
    ) -> Entity:
        """Update Entity's embedding."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        conn.execute("""
            UPDATE entities SET embedding = ?, last_accessed = ?
            WHERE id = ? AND tenant_id = ?
        """, (_serialize_embedding(embedding), now, entity_id, tenant_id))
        conn.commit()
        
        return await self.get_entity(entity_id, tenant_id)
    
    async def increment_entity_mention(
        self,
        entity_id: str,
        tenant_id: str
    ) -> Entity:
        """Increment Entity's mention count."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        conn.execute("""
            UPDATE entities SET mention_count = mention_count + 1, last_accessed = ?
            WHERE id = ? AND tenant_id = ?
        """, (now, entity_id, tenant_id))
        conn.commit()
        
        return await self.get_entity(entity_id, tenant_id)
    
    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert database row to Entity model."""
        return Entity(
            id=row["id"],
            tenant_id=row["tenant_id"],
            node_type=NodeType.ENTITY,
            name=row["name"],
            entity_type=row["entity_type"],
            aliases=json.loads(row["aliases"]) if row["aliases"] else [],
            mention_count=row["mention_count"],
            embedding=_deserialize_embedding(row["embedding"]),
            strength=row["strength"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed=datetime.fromisoformat(row["last_accessed"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    # =========================================================================
    # Claim Operations
    # =========================================================================
    
    async def create_claim(self, claim: ClaimCreate) -> Claim:
        """Create a new Claim."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        # Serialize embedding if provided
        embedding_blob = _serialize_embedding(claim.embedding) if claim.embedding else None
        
        cl = Claim(
            tenant_id=claim.tenant_id,
            content=claim.content,
            claim_kind=claim.claim_kind,
            confidence=claim.confidence,
            source_episode_id=claim.source_episode_id,
            embedding=claim.embedding,
            metadata=claim.metadata,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
        )
        
        conn.execute("""
            INSERT INTO claims (id, tenant_id, content, claim_kind, confidence,
                evidence_count, source_episode_id, embedding, strength,
                created_at, last_accessed, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            cl.id, cl.tenant_id, cl.content, cl.claim_kind.value if isinstance(cl.claim_kind, ClaimKind) else cl.claim_kind,
            cl.confidence, cl.evidence_count, cl.source_episode_id, embedding_blob, cl.strength,
            now, now, json.dumps(cl.metadata)
        ))
        conn.commit()
        
        # Create ABOUT edges to entities
        for entity_id in claim.entity_ids:
            await self.create_edge(EdgeCreate(
                tenant_id=claim.tenant_id,
                source_id=cl.id,
                target_id=entity_id,
                edge_type=EdgeType.ABOUT
            ))
        
        return cl
    
    async def get_claim(self, claim_id: str, tenant_id: str) -> Optional[Claim]:
        """Get Claim by ID."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM claims WHERE id = ? AND tenant_id = ?
        """, (claim_id, tenant_id)).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_claim(row)
    
    async def get_claims_for_entity(
        self, 
        entity_id: str, 
        tenant_id: str,
        limit: int = 50
    ) -> List[Claim]:
        """Get all Claims about a specific Entity."""
        conn = self._get_conn()
        
        rows = conn.execute("""
            SELECT c.* FROM claims c
            JOIN edges e ON e.source_id = c.id
            WHERE e.target_id = ? AND e.edge_type = ? AND c.tenant_id = ?
            ORDER BY c.confidence DESC, c.last_accessed DESC
            LIMIT ?
        """, (entity_id, EdgeType.ABOUT.value, tenant_id, limit)).fetchall()
        
        return [self._row_to_claim(row) for row in rows]
    
    async def find_similar_claims(
        self,
        embedding: List[float],
        tenant_id: str,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[tuple[Claim, float]]:
        """Find similar Claims using vector similarity."""
        # For now, return empty list if sqlite-vec not available
        # TODO: Implement fallback or require sqlite-vec
        if not self._vec_available:
            return []
        
        # TODO: Implement vector similarity search with sqlite-vec
        return []
    
    async def update_claim_confidence(
        self,
        claim_id: str,
        tenant_id: str,
        confidence_delta: float,
        increment_evidence: bool = True
    ) -> Claim:
        """Update Claim confidence."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        if increment_evidence:
            conn.execute("""
                UPDATE claims 
                SET confidence = MIN(1.0, MAX(0.0, confidence + ?)),
                    evidence_count = evidence_count + 1,
                    last_accessed = ?
                WHERE id = ? AND tenant_id = ?
            """, (confidence_delta, now, claim_id, tenant_id))
        else:
            conn.execute("""
                UPDATE claims 
                SET confidence = MIN(1.0, MAX(0.0, confidence + ?)),
                    last_accessed = ?
                WHERE id = ? AND tenant_id = ?
            """, (confidence_delta, now, claim_id, tenant_id))
        
        conn.commit()
        return await self.get_claim(claim_id, tenant_id)
    
    def _row_to_claim(self, row: sqlite3.Row) -> Claim:
        """Convert database row to Claim model."""
        return Claim(
            id=row["id"],
            tenant_id=row["tenant_id"],
            node_type=NodeType.CLAIM,
            content=row["content"],
            claim_kind=ClaimKind(row["claim_kind"]),
            confidence=row["confidence"],
            evidence_count=row["evidence_count"],
            source_episode_id=row["source_episode_id"],
            embedding=_deserialize_embedding(row["embedding"]),
            strength=row["strength"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed=datetime.fromisoformat(row["last_accessed"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    # =========================================================================
    # Insight Operations
    # =========================================================================
    
    async def create_insight(self, insight: InsightCreate) -> Insight:
        """Create a new Insight."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        ins = Insight(
            tenant_id=insight.tenant_id,
            content=insight.content,
            confidence=insight.confidence,
            source_claim_ids=insight.source_claim_ids,
            metadata=insight.metadata,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
        )
        
        conn.execute("""
            INSERT INTO insights (id, tenant_id, content, confidence, validation_count,
                source_claim_ids, embedding, strength, created_at, last_accessed, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ins.id, ins.tenant_id, ins.content, ins.confidence, ins.validation_count,
            json.dumps(ins.source_claim_ids), None, ins.strength,
            now, now, json.dumps(ins.metadata)
        ))
        conn.commit()
        
        # Create DERIVED_FROM edges to source claims
        for claim_id in insight.source_claim_ids:
            await self.create_edge(EdgeCreate(
                tenant_id=insight.tenant_id,
                source_id=ins.id,
                target_id=claim_id,
                edge_type=EdgeType.DERIVED_FROM
            ))
        
        return ins
    
    async def get_insight(self, insight_id: str, tenant_id: str) -> Optional[Insight]:
        """Get Insight by ID."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM insights WHERE id = ? AND tenant_id = ?
        """, (insight_id, tenant_id)).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_insight(row)
    
    async def list_insights(
        self,
        tenant_id: str,
        min_confidence: float = 0.0,
        limit: int = 50
    ) -> List[Insight]:
        """List Insights ordered by confidence."""
        conn = self._get_conn()
        
        rows = conn.execute("""
            SELECT * FROM insights 
            WHERE tenant_id = ? AND confidence >= ?
            ORDER BY confidence DESC, last_accessed DESC
            LIMIT ?
        """, (tenant_id, min_confidence, limit)).fetchall()
        
        return [self._row_to_insight(row) for row in rows]
    
    async def update_insight(
        self,
        insight_id: str,
        tenant_id: str,
        confidence: Optional[float] = None,
        source_claim_ids: Optional[List[str]] = None,
        validation_count: Optional[int] = None
    ) -> Optional[Insight]:
        """Update an existing Insight."""
        conn = self._get_conn()
        
        updates = []
        params = []
        
        if confidence is not None:
            updates.append("confidence = ?")
            params.append(confidence)
        
        if source_claim_ids is not None:
            updates.append("source_claim_ids = ?")
            params.append(json.dumps(source_claim_ids))
        
        if validation_count is not None:
            updates.append("validation_count = ?")
            params.append(validation_count)
        
        if not updates:
            return await self.get_insight(insight_id, tenant_id)
        
        updates.append("last_accessed = ?")
        params.append(datetime.utcnow().isoformat())
        
        params.extend([insight_id, tenant_id])
        
        conn.execute(f"""
            UPDATE insights SET {', '.join(updates)}
            WHERE id = ? AND tenant_id = ?
        """, params)
        conn.commit()
        
        return await self.get_insight(insight_id, tenant_id)
    
    async def find_similar_insights(
        self,
        embedding: List[float],
        tenant_id: str,
        limit: int = 10,
        min_similarity: float = 0.7
    ) -> List[Insight]:
        """Find similar Insights by embedding."""
        conn = self._get_conn()
        
        # Get all insights with embeddings
        rows = conn.execute("""
            SELECT * FROM insights 
            WHERE tenant_id = ? AND embedding IS NOT NULL
        """, (tenant_id,)).fetchall()
        
        if not rows:
            return []
        
        # Compute similarities
        results = []
        for row in rows:
            insight_embedding = _deserialize_embedding(row["embedding"])
            if insight_embedding:
                similarity = self._cosine_similarity(embedding, insight_embedding)
                if similarity >= min_similarity:
                    results.append((self._row_to_insight(row), similarity))
        
        # Sort by similarity and return insights only
        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:limit]]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        import math
        if len(a) != len(b):
            return 0.0
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)
    
    def _row_to_insight(self, row: sqlite3.Row) -> Insight:
        """Convert database row to Insight model."""
        return Insight(
            id=row["id"],
            tenant_id=row["tenant_id"],
            node_type=NodeType.INSIGHT,
            content=row["content"],
            confidence=row["confidence"],
            validation_count=row["validation_count"],
            source_claim_ids=json.loads(row["source_claim_ids"]) if row["source_claim_ids"] else [],
            embedding=_deserialize_embedding(row["embedding"]),
            strength=row["strength"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed=datetime.fromisoformat(row["last_accessed"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    # =========================================================================
    # Procedure Operations
    # =========================================================================
    
    async def create_procedure(self, procedure: ProcedureCreate) -> Procedure:
        """Create a new Procedure."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        proc = Procedure(
            tenant_id=procedure.tenant_id,
            name=procedure.name,
            description=procedure.description,
            steps=procedure.steps,
            source_insight_ids=procedure.source_insight_ids,
            metadata=procedure.metadata,
            created_at=datetime.utcnow(),
            last_accessed=datetime.utcnow(),
        )
        
        conn.execute("""
            INSERT INTO procedures (id, tenant_id, name, description, steps, status,
                source_insight_ids, execution_count, success_count, embedding, strength,
                created_at, last_accessed, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            proc.id, proc.tenant_id, proc.name, proc.description,
            json.dumps(proc.steps), proc.status.value if isinstance(proc.status, ProcedureStatus) else proc.status,
            json.dumps(proc.source_insight_ids), proc.execution_count, proc.success_count,
            None, proc.strength, now, now, json.dumps(proc.metadata)
        ))
        conn.commit()
        
        return proc
    
    async def get_procedure(self, procedure_id: str, tenant_id: str) -> Optional[Procedure]:
        """Get Procedure by ID."""
        conn = self._get_conn()
        row = conn.execute("""
            SELECT * FROM procedures WHERE id = ? AND tenant_id = ?
        """, (procedure_id, tenant_id)).fetchone()
        
        if row is None:
            return None
        
        return self._row_to_procedure(row)
    
    async def list_active_procedures(
        self,
        tenant_id: str,
        limit: int = 20
    ) -> List[Procedure]:
        """List active Procedures."""
        conn = self._get_conn()
        
        rows = conn.execute("""
            SELECT * FROM procedures 
            WHERE tenant_id = ? AND status = ?
            ORDER BY execution_count DESC
            LIMIT ?
        """, (tenant_id, ProcedureStatus.ACTIVE.value, limit)).fetchall()
        
        return [self._row_to_procedure(row) for row in rows]
    
    def _row_to_procedure(self, row: sqlite3.Row) -> Procedure:
        """Convert database row to Procedure model."""
        return Procedure(
            id=row["id"],
            tenant_id=row["tenant_id"],
            node_type=NodeType.PROCEDURE,
            name=row["name"],
            description=row["description"],
            steps=json.loads(row["steps"]) if row["steps"] else [],
            status=ProcedureStatus(row["status"]),
            source_insight_ids=json.loads(row["source_insight_ids"]) if row["source_insight_ids"] else [],
            execution_count=row["execution_count"],
            success_count=row["success_count"],
            embedding=_deserialize_embedding(row["embedding"]),
            strength=row["strength"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_accessed=datetime.fromisoformat(row["last_accessed"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    # =========================================================================
    # Edge Operations
    # =========================================================================
    
    async def create_edge(self, edge: EdgeCreate) -> Edge:
        """Create a new Edge."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        e = Edge(
            tenant_id=edge.tenant_id,
            source_id=edge.source_id,
            target_id=edge.target_id,
            edge_type=edge.edge_type,
            weight=edge.weight,
            metadata=edge.metadata,
            created_at=datetime.utcnow(),
        )
        
        conn.execute("""
            INSERT INTO edges (id, tenant_id, source_id, target_id, edge_type, weight,
                created_at, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            e.id, e.tenant_id, e.source_id, e.target_id,
            e.edge_type.value if isinstance(e.edge_type, EdgeType) else e.edge_type,
            e.weight, now, json.dumps(e.metadata)
        ))
        conn.commit()
        
        return e
    
    async def get_or_create_edge(
        self,
        edge: EdgeCreate,
        strengthen_on_exist: bool = True,
        strengthen_amount: float = 0.1
    ) -> Tuple[Edge, bool]:
        """
        Get existing edge or create new one.
        
        If edge already exists and strengthen_on_exist=True, increases weight.
        This implements co-occurrence based edge strengthening.
        
        Args:
            edge: Edge to create
            strengthen_on_exist: Whether to increase weight if edge exists
            strengthen_amount: How much to increase weight (added to current)
            
        Returns:
            Tuple of (Edge, was_created)
        """
        conn = self._get_conn()
        
        # Check if edge already exists
        row = conn.execute("""
            SELECT * FROM edges 
            WHERE tenant_id = ? AND source_id = ? AND target_id = ? AND edge_type = ?
        """, (
            edge.tenant_id, edge.source_id, edge.target_id,
            edge.edge_type.value if isinstance(edge.edge_type, EdgeType) else edge.edge_type
        )).fetchone()
        
        if row:
            existing_edge = self._row_to_edge(row)
            
            if strengthen_on_exist:
                # Strengthen the edge (cap at 5.0)
                new_weight = min(5.0, existing_edge.weight + strengthen_amount)
                conn.execute("""
                    UPDATE edges SET weight = ? WHERE id = ?
                """, (new_weight, existing_edge.id))
                conn.commit()
                existing_edge.weight = new_weight
            
            return existing_edge, False
        else:
            # Create new edge
            new_edge = await self.create_edge(edge)
            return new_edge, True
    
    async def update_edge_weight(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        edge_type: EdgeType,
        new_weight: float
    ) -> bool:
        """
        Update weight of an existing edge.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            tenant_id: Tenant ID
            edge_type: Type of edge
            new_weight: New weight value
            
        Returns:
            True if edge was updated, False if not found
        """
        conn = self._get_conn()
        
        result = conn.execute("""
            UPDATE edges SET weight = ?
            WHERE tenant_id = ? AND source_id = ? AND target_id = ? AND edge_type = ?
        """, (
            new_weight, tenant_id, source_id, target_id,
            edge_type.value if isinstance(edge_type, EdgeType) else edge_type
        ))
        conn.commit()
        
        return result.rowcount > 0
    
    async def strengthen_edge(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        edge_type: EdgeType,
        amount: float = 0.1,
        max_weight: float = 5.0
    ) -> Optional[float]:
        """
        Increase edge weight by a fixed amount (co-occurrence strengthening).
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            tenant_id: Tenant ID
            edge_type: Type of edge
            amount: Amount to increase weight by
            max_weight: Maximum weight cap
            
        Returns:
            New weight if edge exists, None otherwise
        """
        conn = self._get_conn()
        
        # Get current weight
        row = conn.execute("""
            SELECT weight FROM edges
            WHERE tenant_id = ? AND source_id = ? AND target_id = ? AND edge_type = ?
        """, (
            tenant_id, source_id, target_id,
            edge_type.value if isinstance(edge_type, EdgeType) else edge_type
        )).fetchone()
        
        if not row:
            return None
        
        new_weight = min(max_weight, row["weight"] + amount)
        
        conn.execute("""
            UPDATE edges SET weight = ?
            WHERE tenant_id = ? AND source_id = ? AND target_id = ? AND edge_type = ?
        """, (
            new_weight, tenant_id, source_id, target_id,
            edge_type.value if isinstance(edge_type, EdgeType) else edge_type
        ))
        conn.commit()
        
        return new_weight
    
    async def get_edge(
        self,
        source_id: str,
        target_id: str,
        tenant_id: str,
        edge_type: Optional[EdgeType] = None
    ) -> Optional[Edge]:
        """
        Get a specific edge between two nodes.
        
        Args:
            source_id: Source node ID
            target_id: Target node ID
            tenant_id: Tenant ID
            edge_type: Optional edge type filter
            
        Returns:
            Edge if found, None otherwise
        """
        conn = self._get_conn()
        
        if edge_type:
            row = conn.execute("""
                SELECT * FROM edges
                WHERE tenant_id = ? AND source_id = ? AND target_id = ? AND edge_type = ?
            """, (
                tenant_id, source_id, target_id,
                edge_type.value if isinstance(edge_type, EdgeType) else edge_type
            )).fetchone()
        else:
            row = conn.execute("""
                SELECT * FROM edges
                WHERE tenant_id = ? AND source_id = ? AND target_id = ?
            """, (tenant_id, source_id, target_id)).fetchone()
        
        return self._row_to_edge(row) if row else None

    async def get_edges_from(
        self,
        source_id: str,
        tenant_id: str,
        edge_type: Optional[EdgeType] = None
    ) -> List[Edge]:
        """Get all edges from a node."""
        conn = self._get_conn()
        
        if edge_type:
            rows = conn.execute("""
                SELECT * FROM edges WHERE source_id = ? AND tenant_id = ? AND edge_type = ?
            """, (source_id, tenant_id, edge_type.value)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM edges WHERE source_id = ? AND tenant_id = ?
            """, (source_id, tenant_id)).fetchall()
        
        return [self._row_to_edge(row) for row in rows]
    
    async def get_edges_to(
        self,
        target_id: str,
        tenant_id: str,
        edge_type: Optional[EdgeType] = None
    ) -> List[Edge]:
        """Get all edges to a node."""
        conn = self._get_conn()
        
        if edge_type:
            rows = conn.execute("""
                SELECT * FROM edges WHERE target_id = ? AND tenant_id = ? AND edge_type = ?
            """, (target_id, tenant_id, edge_type.value)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM edges WHERE target_id = ? AND tenant_id = ?
            """, (target_id, tenant_id)).fetchall()
        
        return [self._row_to_edge(row) for row in rows]
    
    async def get_neighbors(
        self,
        node_id: str,
        tenant_id: str,
        edge_type: Optional[EdgeType] = None,
        direction: str = "outgoing"
    ) -> List[str]:
        """Get neighbor node IDs."""
        neighbors = []
        
        if direction in ("outgoing", "both"):
            edges = await self.get_edges_from(node_id, tenant_id, edge_type)
            neighbors.extend([e.target_id for e in edges])
        
        if direction in ("incoming", "both"):
            edges = await self.get_edges_to(node_id, tenant_id, edge_type)
            neighbors.extend([e.source_id for e in edges])
        
        return list(set(neighbors))
    
    async def get_node_degree(self, node_id: str, tenant_id: str) -> int:
        """Get total degree of a node."""
        conn = self._get_conn()
        
        row = conn.execute("""
            SELECT COUNT(*) as degree FROM edges 
            WHERE tenant_id = ? AND (source_id = ? OR target_id = ?)
        """, (tenant_id, node_id, node_id)).fetchone()
        
        return row["degree"] if row else 0
    
    def _row_to_edge(self, row: sqlite3.Row) -> Edge:
        """Convert database row to Edge model."""
        return Edge(
            id=row["id"],
            tenant_id=row["tenant_id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            edge_type=EdgeType(row["edge_type"]),
            weight=row["weight"],
            created_at=datetime.fromisoformat(row["created_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )
    
    # =========================================================================
    # Generic Node Operations
    # =========================================================================
    
    async def get_node(
        self,
        node_id: str,
        tenant_id: str
    ) -> Optional[Union[Episode, Entity, Claim, Insight, Procedure]]:
        """Get any node by ID."""
        # Try each table in order
        for table, converter in [
            ("episodes", self._row_to_episode),
            ("entities", self._row_to_entity),
            ("claims", self._row_to_claim),
            ("insights", self._row_to_insight),
            ("procedures", self._row_to_procedure),
        ]:
            conn = self._get_conn()
            row = conn.execute(f"""
                SELECT * FROM {table} WHERE id = ? AND tenant_id = ?
            """, (node_id, tenant_id)).fetchone()
            
            if row is not None:
                return converter(row)
        
        return None
    
    async def update_node_strength(
        self,
        node_id: str,
        tenant_id: str,
        strength: float
    ) -> None:
        """Update a node's strength."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        for table in ["episodes", "entities", "claims", "insights", "procedures"]:
            result = conn.execute(f"""
                UPDATE {table} SET strength = ?, last_accessed = ?
                WHERE id = ? AND tenant_id = ?
            """, (strength, now, node_id, tenant_id))
            
            if result.rowcount > 0:
                conn.commit()
                return
    
    async def touch_node(self, node_id: str, tenant_id: str) -> None:
        """Update last_accessed timestamp."""
        conn = self._get_conn()
        now = datetime.utcnow().isoformat()
        
        for table in ["episodes", "entities", "claims", "insights", "procedures"]:
            result = conn.execute(f"""
                UPDATE {table} SET last_accessed = ?
                WHERE id = ? AND tenant_id = ?
            """, (now, node_id, tenant_id))
            
            if result.rowcount > 0:
                conn.commit()
                return
    
    # =========================================================================
    # Retrieval Operations
    # =========================================================================
    
    async def hybrid_anchor_search(
        self,
        query_text: str,
        query_embedding: List[float],
        tenant_id: str,
        node_types: Optional[List[NodeType]] = None,
        limit: int = 10,
        lexical_weight: float = 0.3,
        vector_weight: float = 0.7
    ) -> List[AnchorResult]:
        """Hybrid lexical + vector search for anchors."""
        results = []
        conn = self._get_conn()
        
        # Default to searching all types
        if node_types is None:
            node_types = [NodeType.EPISODE, NodeType.ENTITY, NodeType.CLAIM, NodeType.INSIGHT]
        
        # Prepare FTS query - wrap each word in quotes for prefix matching
        # and join with OR for broader matching
        words = query_text.split()
        if words:
            # Use prefix matching with * for each word
            fts_query = " OR ".join(f'"{word}"*' for word in words if word)
        else:
            return []
        
        # Lexical search using FTS5
        fts_tables = {
            NodeType.EPISODE: ("episodes_fts", "episodes", "raw_content"),
            NodeType.ENTITY: ("entities_fts", "entities", "name"),
            NodeType.CLAIM: ("claims_fts", "claims", "content"),
            NodeType.INSIGHT: ("insights_fts", "insights", "content"),
        }
        
        for node_type in node_types:
            if node_type not in fts_tables:
                continue
            
            fts_table, main_table, content_field = fts_tables[node_type]
            
            try:
                # FTS5 search with BM25 ranking
                rows = conn.execute(f"""
                    SELECT m.id, m.{content_field} as content, bm25({fts_table}) as score
                    FROM {fts_table} f
                    JOIN {main_table} m ON f.id = m.id
                    WHERE {fts_table} MATCH ? AND m.tenant_id = ?
                    ORDER BY score
                    LIMIT ?
                """, (fts_query, tenant_id, limit)).fetchall()
                
                for row in rows:
                    # BM25 returns negative scores (lower is better)
                    # Transform to 0-1 range: use sigmoid-like normalization
                    # More negative = better match = higher score
                    raw_score = row["score"]  # Typically -1 to -30 for matches
                    # Map to 0.3-1.0 range (never below lexical weight minimum)
                    normalized_score = 0.3 + 0.7 * (1.0 / (1.0 + abs(raw_score) * 0.1))
                    results.append(AnchorResult(
                        node_id=row["id"],
                        node_type=node_type,
                        score=normalized_score * lexical_weight,
                        content_preview=str(row["content"])[:200] if row["content"] else ""
                    ))
            except sqlite3.OperationalError:
                # FTS query failed (e.g., invalid query syntax)
                continue
        
        # Vector search (Tier 2)
        # Use sqlite-vec if available, otherwise fallback to pure Python
        if query_embedding and any(e != 0.0 for e in query_embedding):
            vector_results = await self._vector_anchor_search(
                query_embedding=query_embedding,
                tenant_id=tenant_id,
                node_types=node_types,
                limit=limit
            )
            
            for vr in vector_results:
                # Apply vector weight
                vr_weighted = AnchorResult(
                    node_id=vr.node_id,
                    node_type=vr.node_type,
                    score=vr.score * vector_weight,
                    content_preview=vr.content_preview
                )
                results.append(vr_weighted)
        
        # Dedupe: keep highest score per node
        seen: Dict[str, AnchorResult] = {}
        for r in results:
            if r.node_id not in seen or r.score > seen[r.node_id].score:
                seen[r.node_id] = r
        
        results = sorted(seen.values(), key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    async def _vector_anchor_search(
        self,
        query_embedding: List[float],
        tenant_id: str,
        node_types: List[NodeType],
        limit: int = 10
    ) -> List[AnchorResult]:
        """
        Vector similarity search for anchors (Tier 2).
        
        Uses sqlite-vec if available, otherwise falls back to 
        pure Python cosine similarity (slower but functional).
        """
        results = []
        conn = self._get_conn()
        
        # Table mappings for vector search
        tables = {
            NodeType.ENTITY: ("entities", "name", "embedding"),
            NodeType.CLAIM: ("claims", "content", "embedding"),
            NodeType.INSIGHT: ("insights", "content", "embedding"),
        }
        
        for node_type in node_types:
            if node_type not in tables:
                continue
            
            table, content_field, embedding_field = tables[node_type]
            
            # Fetch all nodes with embeddings (fallback approach)
            # In production, use sqlite-vec for efficient search
            rows = conn.execute(f"""
                SELECT id, {content_field} as content, {embedding_field} as embedding
                FROM {table}
                WHERE tenant_id = ? AND {embedding_field} IS NOT NULL
                LIMIT 500
            """, (tenant_id,)).fetchall()
            
            for row in rows:
                node_embedding = _deserialize_embedding(row["embedding"])
                if node_embedding is None:
                    continue
                
                # Cosine similarity
                sim = self._cosine_similarity(query_embedding, node_embedding)
                
                if sim >= 0.3:  # Minimum similarity threshold
                    results.append(AnchorResult(
                        node_id=row["id"],
                        node_type=node_type,
                        score=sim,
                        content_preview=str(row["content"])[:200] if row["content"] else ""
                    ))
        
        # Sort by similarity and limit
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(a) != len(b):
            return 0.0
        
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot / (norm_a * norm_b)
    
    # =========================================================================
    # Decay Operations
    # =========================================================================
    
    async def apply_decay(
        self,
        tenant_id: str,
        half_life_days: float = 30.0,
        min_strength: float = 0.01
    ) -> int:
        """Apply time-based decay to node strengths."""
        conn = self._get_conn()
        now = datetime.utcnow()
        updated = 0
        
        for table in ["episodes", "entities", "claims", "insights", "procedures"]:
            rows = conn.execute(f"""
                SELECT id, last_accessed, strength FROM {table}
                WHERE tenant_id = ? AND strength > ?
            """, (tenant_id, min_strength)).fetchall()
            
            for row in rows:
                last_accessed = datetime.fromisoformat(row["last_accessed"])
                days_since = (now - last_accessed).total_seconds() / 86400
                
                # Exponential decay: strength * (0.5 ^ (days / half_life))
                decay_factor = math.pow(0.5, days_since / half_life_days)
                new_strength = row["strength"] * decay_factor
                
                if new_strength < row["strength"]:
                    conn.execute(f"""
                        UPDATE {table} SET strength = ?
                        WHERE id = ? AND tenant_id = ?
                    """, (max(new_strength, min_strength), row["id"], tenant_id))
                    updated += 1
        
        conn.commit()
        return updated
    
    async def prune_weak_nodes(
        self,
        tenant_id: str,
        strength_threshold: float = 0.01
    ) -> int:
        """Remove nodes below strength threshold."""
        conn = self._get_conn()
        pruned = 0
        
        # Prune in reverse dependency order (claims before entities, etc.)
        for table in ["procedures", "insights", "claims", "entities", "episodes"]:
            result = conn.execute(f"""
                DELETE FROM {table}
                WHERE tenant_id = ? AND strength < ?
            """, (tenant_id, strength_threshold))
            pruned += result.rowcount
        
        # Also prune orphaned edges
        conn.execute("""
            DELETE FROM edges WHERE tenant_id = ? AND (
                source_id NOT IN (
                    SELECT id FROM episodes WHERE tenant_id = ?
                    UNION SELECT id FROM entities WHERE tenant_id = ?
                    UNION SELECT id FROM claims WHERE tenant_id = ?
                    UNION SELECT id FROM insights WHERE tenant_id = ?
                    UNION SELECT id FROM procedures WHERE tenant_id = ?
                )
                OR target_id NOT IN (
                    SELECT id FROM episodes WHERE tenant_id = ?
                    UNION SELECT id FROM entities WHERE tenant_id = ?
                    UNION SELECT id FROM claims WHERE tenant_id = ?
                    UNION SELECT id FROM insights WHERE tenant_id = ?
                    UNION SELECT id FROM procedures WHERE tenant_id = ?
                )
            )
        """, (tenant_id,) + (tenant_id,) * 10)
        
        conn.commit()
        return pruned
