# 🐘 PostgreSQL + Apache AGE: Graph Memory Implementation

## Overview

**Apache AGE (A Graph Extension)** extends PostgreSQL with graph database capabilities, giving you:
- **Cypher query language** for graph traversal
- **pgvector** for vector similarity search  
- **Full-text search** with tsvector/tsquery
- **SQL** for structured queries
- **All in one database** - no data duplication!

---

## 🏗️ Architecture with PostgreSQL + AGE

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                     PostgreSQL + Apache AGE Architecture                        │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────┐  │
│  │                         PostgreSQL Database                               │  │
│  │                                                                           │  │
│  │   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐  │  │
│  │   │   Tables    │   │  Apache AGE │   │  pgvector   │   │  Full-Text  │  │  │
│  │   │   (SQL)     │   │   (Graph)   │   │  (Vectors)  │   │   Search    │  │  │
│  │   ├─────────────┤   ├─────────────┤   ├─────────────┤   ├─────────────┤  │  │
│  │   │ • Users     │   │ • Nodes     │   │ • HNSW idx  │   │ • tsvector  │  │  │
│  │   │ • Sessions  │   │ • Edges     │   │ • IVFFlat   │   │ • tsquery   │  │  │
│  │   │ • Metadata  │   │ • Cypher    │   │ • cosine    │   │ • GIN idx   │  │  │
│  │   │ • Audit     │   │ • Traversal │   │ • L2 dist   │   │ • Ranking   │  │  │
│  │   └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘  │  │
│  │                                                                           │  │
│  │   ┌───────────────────────────────────────────────────────────────────┐  │  │
│  │   │                    Unified Query Interface                        │  │  │
│  │   │                                                                   │  │  │
│  │   │   SELECT * FROM cypher('memory_graph', $$                        │  │  │
│  │   │       MATCH (u:User)-[:HAS_CHILD]->(c:Person)                    │  │  │
│  │   │       WHERE c.name = 'Emma'                                       │  │  │
│  │   │       RETURN u, c                                                 │  │  │
│  │   │   $$) AS (user agtype, child agtype)                             │  │  │
│  │   │   JOIN nodes n ON n.id = ...                                      │  │  │
│  │   │   ORDER BY n.embedding <=> query_embedding                        │  │  │
│  │   │   LIMIT 10;                                                       │  │  │
│  │   └───────────────────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────────────────────┘  │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 📊 Database Schema

### 1. Core Tables (SQL)

```sql
-- Enable extensions
CREATE EXTENSION IF NOT EXISTS age;
CREATE EXTENSION IF NOT EXISTS vector;

-- Load AGE
LOAD 'age';
SET search_path = ag_catalog, "$user", public;

-- Create the graph
SELECT create_graph('memory_graph');

-- ============================================
-- Core metadata tables (SQL)
-- ============================================

-- Users table
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    external_id VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Sessions table
CREATE TABLE sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES users(id),
    started_at TIMESTAMP DEFAULT NOW(),
    ended_at TIMESTAMP,
    summary TEXT,
    summary_embedding vector(1536),
    status VARCHAR(50) DEFAULT 'active',
    metadata JSONB DEFAULT '{}'
);

-- Node metadata table (links to graph nodes)
CREATE TABLE node_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    graph_node_id BIGINT NOT NULL,  -- AGE vertex id
    user_id UUID REFERENCES users(id),
    node_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    embedding vector(1536),
    keywords TEXT[],
    
    -- Activation tracking
    importance_score FLOAT DEFAULT 0.5,
    access_count INTEGER DEFAULT 0,
    last_accessed TIMESTAMP DEFAULT NOW(),
    
    -- Full-text search
    content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', content)) STORED,
    
    created_at TIMESTAMP DEFAULT NOW(),
    metadata JSONB DEFAULT '{}'
);

-- Indexes
CREATE INDEX idx_node_metadata_user ON node_metadata(user_id);
CREATE INDEX idx_node_metadata_type ON node_metadata(node_type);
CREATE INDEX idx_node_metadata_embedding ON node_metadata USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_node_metadata_tsv ON node_metadata USING GIN (content_tsv);
CREATE INDEX idx_node_metadata_keywords ON node_metadata USING GIN (keywords);
```

### 2. Graph Schema (Apache AGE + Cypher)

```sql
-- ============================================
-- Create vertex labels (node types)
-- ============================================

SELECT create_vlabel('memory_graph', 'Entity');
SELECT create_vlabel('memory_graph', 'Concept');
SELECT create_vlabel('memory_graph', 'Fact');
SELECT create_vlabel('memory_graph', 'Episode');
SELECT create_vlabel('memory_graph', 'Belief');
SELECT create_vlabel('memory_graph', 'User');

-- ============================================
-- Create edge labels (relationship types)
-- ============================================

-- Hierarchical
SELECT create_elabel('memory_graph', 'IS_A');
SELECT create_elabel('memory_graph', 'PART_OF');
SELECT create_elabel('memory_graph', 'CONTAINS');

-- Semantic
SELECT create_elabel('memory_graph', 'RELATED_TO');
SELECT create_elabel('memory_graph', 'SIMILAR_TO');
SELECT create_elabel('memory_graph', 'CONTRASTS_WITH');

-- Causal
SELECT create_elabel('memory_graph', 'CAUSED_BY');
SELECT create_elabel('memory_graph', 'LEADS_TO');

-- Temporal
SELECT create_elabel('memory_graph', 'HAPPENED_BEFORE');
SELECT create_elabel('memory_graph', 'HAPPENED_AFTER');
SELECT create_elabel('memory_graph', 'HAPPENED_DURING');

-- Evidential
SELECT create_elabel('memory_graph', 'SUPPORTS');
SELECT create_elabel('memory_graph', 'CONTRADICTS');
SELECT create_elabel('memory_graph', 'DERIVED_FROM');

-- User-specific
SELECT create_elabel('memory_graph', 'HAS_PROPERTY');
SELECT create_elabel('memory_graph', 'HAS_GOAL');
SELECT create_elabel('memory_graph', 'PREFERS');
SELECT create_elabel('memory_graph', 'OWNS');
SELECT create_elabel('memory_graph', 'WORKS_AT');
SELECT create_elabel('memory_graph', 'HAS_CHILD');

-- Associative
SELECT create_elabel('memory_graph', 'MENTIONED_WITH');
SELECT create_elabel('memory_graph', 'ASSOCIATED_WITH');
```

### 3. Example: Creating Knowledge Graph

```sql
-- Create a user node
SELECT * FROM cypher('memory_graph', $$
    CREATE (u:User {
        external_id: 'user_123',
        name: 'John Doe'
    })
    RETURN u
$$) AS (user agtype);

-- Create an entity (daughter)
SELECT * FROM cypher('memory_graph', $$
    CREATE (e:Entity {
        name: 'Emma',
        entity_type: 'person',
        age: 8,
        relationship: 'daughter'
    })
    RETURN e
$$) AS (entity agtype);

-- Create a concept (college savings)
SELECT * FROM cypher('memory_graph', $$
    CREATE (c:Concept {
        name: 'College Savings Goal',
        domain: 'finance',
        time_horizon: '10 years'
    })
    RETURN c
$$) AS (concept agtype);

-- Create relationships
SELECT * FROM cypher('memory_graph', $$
    MATCH (u:User {external_id: 'user_123'})
    MATCH (e:Entity {name: 'Emma'})
    CREATE (u)-[:HAS_CHILD {since: '2017'}]->(e)
    RETURN u, e
$$) AS (user agtype, entity agtype);

SELECT * FROM cypher('memory_graph', $$
    MATCH (e:Entity {name: 'Emma'})
    MATCH (c:Concept {name: 'College Savings Goal'})
    CREATE (e)-[:HAS_GOAL {priority: 'high'}]->(c)
    RETURN e, c
$$) AS (entity agtype, concept agtype);
```

---

## 🔍 Hybrid Query Patterns

### 1. Graph Traversal + Vector Search

```sql
-- Find semantically similar nodes connected to a specific entity
WITH anchor_node AS (
    SELECT * FROM cypher('memory_graph', $$
        MATCH (e:Entity {name: 'Emma'})-[*1..2]-(connected)
        RETURN id(connected) as node_id
    $$) AS (node_id agtype)
),
connected_metadata AS (
    SELECT nm.*, an.node_id
    FROM node_metadata nm
    JOIN anchor_node an ON nm.graph_node_id = an.node_id::bigint
)
SELECT 
    cm.*,
    cm.embedding <=> $1 AS vector_distance
FROM connected_metadata cm
WHERE cm.embedding IS NOT NULL
ORDER BY cm.embedding <=> $1
LIMIT 10;
```

### 2. Full-Text + Graph Traversal

```sql
-- Find nodes matching keywords, then traverse their connections
WITH keyword_matches AS (
    SELECT graph_node_id, content, 
           ts_rank(content_tsv, plainto_tsquery('english', 'college savings')) as rank
    FROM node_metadata
    WHERE content_tsv @@ plainto_tsquery('english', 'college savings')
    ORDER BY rank DESC
    LIMIT 5
)
SELECT * FROM cypher('memory_graph', $$
    MATCH (n)-[r*1..2]-(connected)
    WHERE id(n) IN $node_ids
    RETURN n, r, connected
$$, (SELECT array_agg(graph_node_id) FROM keyword_matches)) 
AS (node agtype, relationships agtype, connected agtype);
```

### 3. Path Finding Between Nodes

```sql
-- Find shortest path between two concepts
SELECT * FROM cypher('memory_graph', $$
    MATCH path = shortestPath(
        (start:Entity {name: 'Emma'})-[*..4]-(end:Concept {name: '529 Plan'})
    )
    RETURN path, length(path) as hops
$$) AS (path agtype, hops agtype);
```

### 4. Spreading Activation Query

```sql
-- Implement spreading activation with recursive CTE
WITH RECURSIVE activation AS (
    -- Base case: anchor nodes with activation = 1.0
    SELECT 
        graph_node_id,
        1.0 as activation,
        0 as depth,
        ARRAY[graph_node_id] as path
    FROM node_metadata
    WHERE graph_node_id IN (
        SELECT id(n)::bigint FROM cypher('memory_graph', $$
            MATCH (n:Entity {name: 'Emma'})
            RETURN id(n)
        $$) AS (id agtype)
    )
    
    UNION ALL
    
    -- Recursive case: spread to neighbors with decay
    SELECT 
        neighbor.graph_node_id,
        a.activation * 0.7 * COALESCE(edge_weight, 0.5) as activation,
        a.depth + 1 as depth,
        a.path || neighbor.graph_node_id
    FROM activation a
    CROSS JOIN LATERAL (
        SELECT 
            nm.graph_node_id,
            0.8 as edge_weight  -- Could vary by edge type
        FROM cypher('memory_graph', $$
            MATCH (n)-[r]-(neighbor)
            WHERE id(n) = $1
            RETURN id(neighbor) as neighbor_id, type(r) as edge_type
        $$, a.graph_node_id) AS (neighbor_id agtype, edge_type agtype)
        JOIN node_metadata nm ON nm.graph_node_id = neighbor_id::bigint
        WHERE nm.graph_node_id != ALL(a.path)  -- Avoid cycles
    ) neighbor
    WHERE a.depth < 3  -- Max hops
      AND a.activation * 0.7 > 0.1  -- Threshold
)
SELECT 
    graph_node_id,
    MAX(activation) as max_activation,
    MIN(depth) as min_depth
FROM activation
GROUP BY graph_node_id
ORDER BY max_activation DESC;
```

---

## 🐍 Python Implementation

```python
"""
PostgreSQL + Apache AGE Graph Memory Provider

Combines:
- Apache AGE for graph traversal (Cypher)
- pgvector for semantic search
- PostgreSQL full-text search
- SQL for structured queries
"""

import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import asyncpg
from pgvector.asyncpg import register_vector
import json


@dataclass
class GraphNode:
    """Represents a node in the knowledge graph."""
    id: int
    node_type: str
    content: str
    properties: Dict[str, Any]
    embedding: Optional[List[float]] = None
    activation: float = 0.0


@dataclass
class GraphEdge:
    """Represents an edge in the knowledge graph."""
    source_id: int
    target_id: int
    edge_type: str
    weight: float = 1.0
    properties: Dict[str, Any] = None


class PostgresGraphMemory:
    """
    Graph Memory implementation using PostgreSQL + Apache AGE.
    """
    
    def __init__(
        self,
        connection_string: str,
        graph_name: str = "memory_graph"
    ):
        self.connection_string = connection_string
        self.graph_name = graph_name
        self.pool: Optional[asyncpg.Pool] = None
    
    async def connect(self):
        """Initialize connection pool."""
        self.pool = await asyncpg.create_pool(
            self.connection_string,
            min_size=2,
            max_size=10
        )
        
        # Register vector type
        async with self.pool.acquire() as conn:
            await register_vector(conn)
            
            # Load AGE extension
            await conn.execute("LOAD 'age';")
            await conn.execute(
                "SET search_path = ag_catalog, \"$user\", public;"
            )
    
    async def close(self):
        """Close connection pool."""
        if self.pool:
            await self.pool.close()
    
    # =========================================================
    # Node Operations
    # =========================================================
    
    async def create_node(
        self,
        user_id: str,
        node_type: str,
        content: str,
        properties: Dict[str, Any],
        embedding: Optional[List[float]] = None,
        keywords: Optional[List[str]] = None
    ) -> int:
        """Create a node in the graph with metadata."""
        async with self.pool.acquire() as conn:
            # Create node in AGE graph
            cypher_query = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    CREATE (n:{node_type} $props)
                    RETURN id(n)
                $$, $1) AS (node_id agtype)
            """
            
            result = await conn.fetchrow(
                cypher_query,
                json.dumps(properties)
            )
            graph_node_id = int(result['node_id'].strip('"'))
            
            # Create metadata entry with embedding
            await conn.execute("""
                INSERT INTO node_metadata 
                (graph_node_id, user_id, node_type, content, embedding, keywords)
                VALUES ($1, $2, $3, $4, $5, $6)
            """, graph_node_id, user_id, node_type, content, embedding, keywords)
            
            return graph_node_id
    
    async def create_edge(
        self,
        source_id: int,
        target_id: int,
        edge_type: str,
        properties: Optional[Dict[str, Any]] = None,
        weight: float = 1.0
    ) -> None:
        """Create an edge between two nodes."""
        async with self.pool.acquire() as conn:
            props = properties or {}
            props['weight'] = weight
            
            cypher_query = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    MATCH (a), (b)
                    WHERE id(a) = {source_id} AND id(b) = {target_id}
                    CREATE (a)-[r:{edge_type} $props]->(b)
                    RETURN r
                $$, $1) AS (edge agtype)
            """
            
            await conn.execute(cypher_query, json.dumps(props))
    
    # =========================================================
    # Search Operations
    # =========================================================
    
    async def vector_search(
        self,
        query_embedding: List[float],
        user_id: str,
        limit: int = 10,
        node_types: Optional[List[str]] = None
    ) -> List[GraphNode]:
        """Search nodes by vector similarity."""
        async with self.pool.acquire() as conn:
            type_filter = ""
            if node_types:
                type_filter = f"AND node_type = ANY($4)"
            
            query = f"""
                SELECT 
                    graph_node_id,
                    node_type,
                    content,
                    metadata,
                    embedding <=> $1 as distance
                FROM node_metadata
                WHERE user_id = $2
                  AND embedding IS NOT NULL
                  {type_filter}
                ORDER BY embedding <=> $1
                LIMIT $3
            """
            
            params = [query_embedding, user_id, limit]
            if node_types:
                params.append(node_types)
            
            rows = await conn.fetch(query, *params)
            
            return [
                GraphNode(
                    id=row['graph_node_id'],
                    node_type=row['node_type'],
                    content=row['content'],
                    properties=json.loads(row['metadata']) if row['metadata'] else {},
                    activation=1.0 - row['distance']  # Convert distance to similarity
                )
                for row in rows
            ]
    
    async def fulltext_search(
        self,
        query: str,
        user_id: str,
        limit: int = 10
    ) -> List[GraphNode]:
        """Search nodes by full-text matching."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT 
                    graph_node_id,
                    node_type,
                    content,
                    metadata,
                    ts_rank(content_tsv, plainto_tsquery('english', $1)) as rank
                FROM node_metadata
                WHERE user_id = $2
                  AND content_tsv @@ plainto_tsquery('english', $1)
                ORDER BY rank DESC
                LIMIT $3
            """, query, user_id, limit)
            
            return [
                GraphNode(
                    id=row['graph_node_id'],
                    node_type=row['node_type'],
                    content=row['content'],
                    properties=json.loads(row['metadata']) if row['metadata'] else {},
                    activation=row['rank']
                )
                for row in rows
            ]
    
    async def find_entity(
        self,
        name: str,
        user_id: str
    ) -> Optional[GraphNode]:
        """Find an entity by name."""
        async with self.pool.acquire() as conn:
            result = await conn.fetchrow(f"""
                SELECT nm.*, props.name
                FROM cypher('{self.graph_name}', $$
                    MATCH (n:Entity)
                    WHERE n.name = $name
                    RETURN id(n) as node_id, n.name as name
                $$, $1) AS (node_id agtype, name agtype)
                JOIN node_metadata nm ON nm.graph_node_id = node_id::bigint
                WHERE nm.user_id = $2
                LIMIT 1
            """, json.dumps({'name': name}), user_id)
            
            if result:
                return GraphNode(
                    id=result['graph_node_id'],
                    node_type=result['node_type'],
                    content=result['content'],
                    properties=json.loads(result['metadata']) if result['metadata'] else {}
                )
            return None
    
    # =========================================================
    # Graph Traversal
    # =========================================================
    
    async def get_neighbors(
        self,
        node_id: int,
        edge_types: Optional[List[str]] = None,
        direction: str = "both"  # "outgoing", "incoming", "both"
    ) -> List[Tuple[GraphNode, str, float]]:
        """Get neighboring nodes with edge info."""
        async with self.pool.acquire() as conn:
            # Build direction pattern
            if direction == "outgoing":
                pattern = f"(n)-[r]->(neighbor)"
            elif direction == "incoming":
                pattern = f"(n)<-[r]-(neighbor)"
            else:
                pattern = f"(n)-[r]-(neighbor)"
            
            cypher_query = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    MATCH {pattern}
                    WHERE id(n) = {node_id}
                    RETURN id(neighbor) as neighbor_id, 
                           type(r) as edge_type,
                           COALESCE(r.weight, 1.0) as weight
                $$) AS (neighbor_id agtype, edge_type agtype, weight agtype)
            """
            
            rows = await conn.fetch(cypher_query)
            
            result = []
            for row in rows:
                neighbor_id = int(str(row['neighbor_id']).strip('"'))
                edge_type = str(row['edge_type']).strip('"')
                weight = float(str(row['weight']))
                
                # Filter by edge type if specified
                if edge_types and edge_type not in edge_types:
                    continue
                
                # Get node metadata
                metadata = await conn.fetchrow("""
                    SELECT * FROM node_metadata WHERE graph_node_id = $1
                """, neighbor_id)
                
                if metadata:
                    node = GraphNode(
                        id=neighbor_id,
                        node_type=metadata['node_type'],
                        content=metadata['content'],
                        properties=json.loads(metadata['metadata']) if metadata['metadata'] else {}
                    )
                    result.append((node, edge_type, weight))
            
            return result
    
    async def find_shortest_path(
        self,
        source_id: int,
        target_id: int,
        max_length: int = 4
    ) -> Optional[List[Tuple[int, str]]]:
        """Find shortest path between two nodes."""
        async with self.pool.acquire() as conn:
            cypher_query = f"""
                SELECT * FROM cypher('{self.graph_name}', $$
                    MATCH path = shortestPath(
                        (a)-[*..{max_length}]-(b)
                    )
                    WHERE id(a) = {source_id} AND id(b) = {target_id}
                    RETURN [n IN nodes(path) | id(n)] as node_ids,
                           [r IN relationships(path) | type(r)] as edge_types
                $$) AS (node_ids agtype, edge_types agtype)
            """
            
            result = await conn.fetchrow(cypher_query)
            
            if result:
                node_ids = json.loads(str(result['node_ids']))
                edge_types = json.loads(str(result['edge_types']))
                
                path = []
                for i, node_id in enumerate(node_ids[1:], 1):
                    edge_type = edge_types[i-1] if i-1 < len(edge_types) else "unknown"
                    path.append((int(node_id), edge_type))
                
                return path
            
            return None
    
    # =========================================================
    # Spreading Activation
    # =========================================================
    
    async def spreading_activation(
        self,
        anchor_node_ids: List[int],
        user_id: str,
        decay_factor: float = 0.7,
        threshold: float = 0.1,
        max_hops: int = 3
    ) -> Dict[int, float]:
        """
        Perform spreading activation from anchor nodes.
        
        Uses recursive CTE for efficient graph traversal.
        """
        async with self.pool.acquire() as conn:
            # Convert anchor IDs to SQL array
            anchor_array = anchor_node_ids
            
            query = """
                WITH RECURSIVE activation AS (
                    -- Base case: anchor nodes with activation = 1.0
                    SELECT 
                        graph_node_id,
                        1.0::float as activation,
                        0 as depth,
                        ARRAY[graph_node_id] as path
                    FROM node_metadata
                    WHERE graph_node_id = ANY($1)
                      AND user_id = $2
                    
                    UNION ALL
                    
                    -- Recursive case: get neighbors and decay activation
                    SELECT DISTINCT ON (neighbor_data.neighbor_id)
                        neighbor_data.neighbor_id,
                        (a.activation * $3 * COALESCE(neighbor_data.weight, 0.8))::float,
                        a.depth + 1,
                        a.path || neighbor_data.neighbor_id
                    FROM activation a
                    CROSS JOIN LATERAL (
                        SELECT 
                            nm.graph_node_id as neighbor_id,
                            0.8::float as weight
                        FROM node_metadata nm
                        WHERE nm.user_id = $2
                          AND nm.graph_node_id != ALL(a.path)
                          AND EXISTS (
                              SELECT 1 FROM cypher('memory_graph', $$
                                  MATCH (n)-[r]-(neighbor)
                                  WHERE id(n) = $node_id AND id(neighbor) = $neighbor_id
                                  RETURN 1
                              $$, jsonb_build_object(
                                  'node_id', a.graph_node_id,
                                  'neighbor_id', nm.graph_node_id
                              )) AS (exists int)
                          )
                    ) neighbor_data
                    WHERE a.depth < $4
                      AND a.activation * $3 > $5
                )
                SELECT 
                    graph_node_id,
                    MAX(activation) as max_activation
                FROM activation
                GROUP BY graph_node_id
                ORDER BY max_activation DESC
            """
            
            rows = await conn.fetch(
                query,
                anchor_array,
                user_id,
                decay_factor,
                max_hops,
                threshold
            )
            
            return {row['graph_node_id']: row['max_activation'] for row in rows}
    
    # =========================================================
    # Hybrid Retrieval
    # =========================================================
    
    async def hybrid_retrieve(
        self,
        query: str,
        query_embedding: List[float],
        user_id: str,
        vector_weight: float = 0.4,
        text_weight: float = 0.3,
        graph_weight: float = 0.3,
        limit: int = 20
    ) -> List[GraphNode]:
        """
        Hybrid retrieval combining vector, text, and graph search.
        
        1. Vector search for semantic similarity
        2. Full-text search for keyword matches
        3. Entity matching for known entities
        4. Spreading activation for graph context
        5. RRF fusion for final ranking
        """
        
        # 1. Vector search
        vector_results = await self.vector_search(
            query_embedding, user_id, limit=limit
        )
        
        # 2. Full-text search
        text_results = await self.fulltext_search(query, user_id, limit=limit)
        
        # 3. Extract entities and find matches
        entities = self._extract_entities(query)
        entity_nodes = []
        for entity in entities:
            node = await self.find_entity(entity, user_id)
            if node:
                node.activation = 1.0
                entity_nodes.append(node)
        
        # 4. Spreading activation from all found nodes
        anchor_ids = (
            [n.id for n in vector_results[:3]] +
            [n.id for n in text_results[:3]] +
            [n.id for n in entity_nodes]
        )
        
        if anchor_ids:
            activations = await self.spreading_activation(
                list(set(anchor_ids)), user_id
            )
        else:
            activations = {}
        
        # 5. RRF fusion
        all_nodes = {}
        
        for rank, node in enumerate(vector_results, 1):
            if node.id not in all_nodes:
                all_nodes[node.id] = {'node': node, 'scores': {}}
            all_nodes[node.id]['scores']['vector'] = 1 / (60 + rank)
        
        for rank, node in enumerate(text_results, 1):
            if node.id not in all_nodes:
                all_nodes[node.id] = {'node': node, 'scores': {}}
            all_nodes[node.id]['scores']['text'] = 1 / (60 + rank)
        
        for node in entity_nodes:
            if node.id not in all_nodes:
                all_nodes[node.id] = {'node': node, 'scores': {}}
            all_nodes[node.id]['scores']['entity'] = 1.0
        
        for node_id, activation in activations.items():
            if node_id in all_nodes:
                all_nodes[node_id]['scores']['graph'] = activation
        
        # Calculate final scores
        results = []
        for node_id, data in all_nodes.items():
            scores = data['scores']
            final_score = (
                scores.get('vector', 0) * vector_weight +
                scores.get('text', 0) * text_weight +
                scores.get('graph', 0) * graph_weight +
                scores.get('entity', 0) * 0.2  # Bonus for entity match
            )
            data['node'].activation = final_score
            results.append(data['node'])
        
        # Sort by final score
        results.sort(key=lambda n: n.activation, reverse=True)
        
        return results[:limit]
    
    def _extract_entities(self, query: str) -> List[str]:
        """Simple entity extraction (override with NER in production)."""
        # Very basic - in production use spaCy or LLM
        words = query.split()
        # Look for capitalized words
        return [w for w in words if w[0].isupper() and len(w) > 1]
```

---

## 🚀 Deployment Options

### Option 1: Azure Database for PostgreSQL Flexible Server

```bash
# Create with AGE and pgvector extensions
az postgres flexible-server create \
  --name memory-graph-server \
  --resource-group my-rg \
  --location eastus \
  --sku-name Standard_D4s_v3 \
  --version 15

# Enable extensions
az postgres flexible-server parameter set \
  --server-name memory-graph-server \
  --resource-group my-rg \
  --name azure.extensions \
  --value "age,vector"
```

### Option 2: Self-hosted with Docker

```dockerfile
FROM postgres:15

# Install build dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    git \
    postgresql-server-dev-15

# Install Apache AGE
RUN git clone https://github.com/apache/age.git /age && \
    cd /age && \
    make install

# Install pgvector
RUN git clone https://github.com/pgvector/pgvector.git /pgvector && \
    cd /pgvector && \
    make && make install

# Configure PostgreSQL
RUN echo "shared_preload_libraries = 'age'" >> /usr/share/postgresql/postgresql.conf.sample
```

---

## 📊 Performance Considerations

| Operation | Complexity | Optimization |
|-----------|------------|--------------|
| Vector search | O(log n) | HNSW index with `ef_search` tuning |
| Full-text search | O(log n) | GIN index on tsvector |
| Graph traversal | O(V + E) | Edge label indexes, limit depth |
| Spreading activation | O(k^d) | Threshold pruning, max hops |
| Hybrid retrieval | O(log n) | Parallel queries, connection pooling |

### Index Recommendations

```sql
-- Optimize vector search
CREATE INDEX CONCURRENTLY idx_embedding_hnsw 
ON node_metadata USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Optimize full-text
CREATE INDEX CONCURRENTLY idx_content_gin 
ON node_metadata USING GIN (content_tsv);

-- Optimize graph queries (AGE automatically indexes vertex/edge labels)
-- But you can add property indexes:
SELECT create_property_index('memory_graph', 'Entity', 'name');
```
