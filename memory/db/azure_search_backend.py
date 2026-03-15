"""
Azure AI Search backend for Agent Memory Service.

This backend stores each memory container in a dedicated Azure AI Search index
and uses native vector + hybrid retrieval instead of a standalone reranker.
"""

import json
import os
from typing import Any, Dict, Iterable, List, Optional

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents.aio import SearchClient
from azure.search.documents.indexes.aio import SearchIndexClient
from azure.search.documents.indexes.models import (
    HnswAlgorithmConfiguration,
    SearchField,
    SearchFieldDataType,
    SearchIndex,
    SearchableField,
    SimpleField,
    VectorSearch,
    VectorSearchProfile,
)
from azure.search.documents.models import VectorizedQuery

from memory.db.base import (
    ContainerType,
    DatabaseCapabilities,
    EmbeddingProvider,
    MemoryDatabase,
    SearchResult,
)


VECTOR_PROFILE_NAME = "default-vector-profile"
VECTOR_ALGORITHM_NAME = "default-hnsw"

INDEX_SUFFIXES = {
    ContainerType.INTERACTIONS: "interactions",
    ContainerType.INSIGHTS: "insights",
    ContainerType.SESSION_SUMMARIES: "session-summaries",
}

SEARCHABLE_TEXT_FIELDS = {
    ContainerType.INTERACTIONS: ["content", "summary", "metadata_json"],
    ContainerType.INSIGHTS: ["insight_text", "category", "importance", "mutation_history_json"],
    ContainerType.SESSION_SUMMARIES: ["summary", "cumulative_summary", "key_topics_text"],
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

SERIALIZED_JSON_FIELDS = {
    ContainerType.INTERACTIONS: {"metadata"},
    ContainerType.INSIGHTS: {"mutation_history"},
    ContainerType.SESSION_SUMMARIES: set(),
}

COLLECTION_FIELDS = {
    ContainerType.INTERACTIONS: set(),
    ContainerType.INSIGHTS: {"session_ids", "source_insight_ids", "source_session_ids"},
    ContainerType.SESSION_SUMMARIES: {"key_topics", "extracted_insights"},
}

VECTOR_FIELDS = {
    ContainerType.INTERACTIONS: {"content_vector", "summary_vector"},
    ContainerType.INSIGHTS: {"insight_vector"},
    ContainerType.SESSION_SUMMARIES: {"summary_vector"},
}


class AzureAISearchDatabase(MemoryDatabase):
    """Azure AI Search implementation of the memory database interface."""

    def __init__(
        self,
        endpoint: Optional[str] = None,
        credential: Optional[Any] = None,
        api_key: Optional[str] = None,
        index_prefix: str = "agent-memory",
        embedding_provider: Optional[EmbeddingProvider] = None,
        vector_dimensions: int = 1536,
        index_client: Optional[SearchIndexClient] = None,
        search_clients: Optional[Dict[ContainerType, SearchClient]] = None,
    ):
        super().__init__(embedding_provider)

        self.endpoint = endpoint or os.getenv("AZURE_AI_SEARCH_ENDPOINT") or os.getenv("AZURE_SEARCH_ENDPOINT")
        self.index_prefix = (index_prefix or os.getenv("AZURE_AI_SEARCH_INDEX_PREFIX") or "agent-memory").lower()
        self.vector_dimensions = vector_dimensions

        resolved_credential = credential
        resolved_api_key = api_key or os.getenv("AZURE_AI_SEARCH_API_KEY") or os.getenv("AZURE_SEARCH_API_KEY")
        if resolved_credential is None and resolved_api_key:
            resolved_credential = AzureKeyCredential(resolved_api_key)
        elif resolved_credential is None and self.endpoint:
            from azure.identity import DefaultAzureCredential

            resolved_credential = DefaultAzureCredential()

        if (index_client is None or search_clients is None) and (not self.endpoint or resolved_credential is None):
            raise ValueError(
                "Azure AI Search requires endpoint plus credential/api_key, "
                "or pre-created search clients."
            )

        self._credential = resolved_credential
        self._index_client = index_client
        self._search_clients = search_clients or {}
        self._owns_index_client = index_client is None
        self._owns_search_clients = search_clients is None
        self._initialized = False

    async def initialize(self) -> None:
        """Create indexes if needed and initialize per-container clients."""
        if self._initialized:
            return

        if self._index_client is None:
            self._index_client = SearchIndexClient(
                endpoint=self.endpoint,
                credential=self._credential,
            )

        for container in ContainerType:
            index = self._build_index(container)
            await self._index_client.create_or_update_index(index=index)

            if container not in self._search_clients:
                self._search_clients[container] = SearchClient(
                    endpoint=self.endpoint,
                    index_name=index.name,
                    credential=self._credential,
                )

        self._initialized = True

    async def close(self) -> None:
        """Close owned search clients."""
        if self._owns_search_clients:
            for client in self._search_clients.values():
                await client.close()
        self._search_clients.clear()

        if self._owns_index_client and self._index_client is not None:
            await self._index_client.close()
        self._index_client = None
        self._initialized = False

    def get_capabilities(self) -> DatabaseCapabilities:
        """Describe backend capabilities."""
        return DatabaseCapabilities(
            supports_vector_search=True,
            supports_hybrid_search=True,
            supports_full_text_search=True,
            supports_transactions=False,
            vector_dimensions=self.vector_dimensions,
            max_batch_size=1000,
            backend_name="azure_ai_search",
            backend_version="vector-hybrid",
        )

    async def upsert(
        self,
        container: ContainerType,
        document: Dict[str, Any],
        partition_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Insert or replace a document."""
        container = self._normalize_container(container)
        if "id" not in document:
            raise ValueError("Document must have an 'id' field")

        client = self._get_search_client(container)
        indexed_doc = self._prepare_document(container, document)
        await client.merge_or_upload_documents(documents=[indexed_doc])
        return document

    async def batch_upsert(
        self,
        container: ContainerType,
        documents: List[Dict[str, Any]],
        partition_key: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Insert or replace multiple documents."""
        container = self._normalize_container(container)
        for document in documents:
            if "id" not in document:
                raise ValueError("Document must have an 'id' field")

        client = self._get_search_client(container)
        await client.merge_or_upload_documents(
            documents=[self._prepare_document(container, document) for document in documents]
        )
        return documents

    async def get_by_id(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Retrieve a document by its ID."""
        container = self._normalize_container(container)
        client = self._get_search_client(container)
        try:
            document = await client.get_document(
                key=document_id,
                selected_fields=self._selected_fields(container),
            )
        except ResourceNotFoundError:
            return None

        return self._decode_document(container, document)

    async def delete(
        self,
        container: ContainerType,
        document_id: str,
        partition_key: Optional[str] = None,
    ) -> bool:
        """Delete a document by ID."""
        container = self._normalize_container(container)
        client = self._get_search_client(container)
        results = await client.delete_documents(documents=[{"id": document_id}])
        return any(getattr(result, "succeeded", True) for result in results)

    async def query(
        self,
        container: ContainerType,
        filters: Dict[str, Any],
        order_by: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Query documents with equality filters and optional ordering."""
        container = self._normalize_container(container)
        self._validate_filter_keys(container, filters)
        order_clauses = None
        if order_by:
            field_name, direction = self._parse_order_by(order_by)
            order_clauses = [f"{field_name} {direction}"]

        results = await self._run_search(
            container=container,
            search_text="*",
            filter_expression=self._build_filter_expression(filters),
            order_by=order_clauses,
            top=limit or 100,
        )
        return [self._decode_document(container, result) for result in results]

    async def vector_search(
        self,
        container: ContainerType,
        query_embedding: List[float],
        vector_field: str = "content_vector",
        top_k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Perform pure vector similarity search."""
        container = self._normalize_container(container)
        self._validate_filter_keys(container, filters)
        results = await self._run_search(
            container=container,
            search_text=None,
            filter_expression=self._build_filter_expression(filters),
            top=top_k,
            vector_queries=[
                VectorizedQuery(
                    vector=query_embedding,
                    k=top_k,
                    fields=vector_field,
                )
            ],
        )
        return self._to_search_results(container, results, score_type="similarity")

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
        """Perform native Azure AI Search hybrid search."""
        container = self._normalize_container(container)
        self._validate_filter_keys(container, filters)
        results = await self._run_search(
            container=container,
            search_text=query_text or "*",
            filter_expression=self._build_filter_expression(filters),
            top=top_k,
            search_fields=text_fields or SEARCHABLE_TEXT_FIELDS[container],
            vector_queries=[
                VectorizedQuery(
                    vector=query_embedding,
                    k=top_k,
                    fields=vector_field,
                )
            ],
        )
        return self._to_search_results(container, results, score_type="hybrid")

    def _get_search_client(self, container: ContainerType) -> SearchClient:
        """Return the client for a container."""
        container = self._normalize_container(container)
        try:
            return self._search_clients[container]
        except KeyError as exc:
            raise ValueError(f"Container {container.value} is not initialized") from exc

    def _index_name(self, container: ContainerType) -> str:
        """Build a valid Azure AI Search index name."""
        container = self._normalize_container(container)
        suffix = INDEX_SUFFIXES[container]
        return f"{self.index_prefix}-{suffix}".replace("_", "-").lower()

    def _normalize_container(self, container: ContainerType | str) -> ContainerType:
        """Normalize enum instances that may come from reloaded modules."""
        if isinstance(container, ContainerType):
            return container
        return ContainerType(getattr(container, "value", container))

    def _selected_fields(self, container: ContainerType) -> List[str]:
        """Return all non-vector fields for a container."""
        fields = []
        for field in self._build_index_fields(container):
            if field.name not in VECTOR_FIELDS[container]:
                fields.append(field.name)
        return fields

    def _build_index(self, container: ContainerType) -> SearchIndex:
        """Build the Azure AI Search index definition for a container."""
        return SearchIndex(
            name=self._index_name(container),
            fields=self._build_index_fields(container),
            vector_search=VectorSearch(
                profiles=[VectorSearchProfile(name=VECTOR_PROFILE_NAME, algorithm_configuration_name=VECTOR_ALGORITHM_NAME)],
                algorithms=[HnswAlgorithmConfiguration(name=VECTOR_ALGORITHM_NAME)],
            ),
        )

    def _build_index_fields(self, container: ContainerType) -> List[SearchField]:
        """Define index fields for a given container."""
        if container == ContainerType.INTERACTIONS:
            return [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
                SimpleField(name="user_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="agent_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="session_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="timestamp", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchableField(name="content"),
                SearchableField(name="summary"),
                SearchableField(name="metadata_json"),
                SimpleField(name="created_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="updated_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchField(
                    name="content_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self.vector_dimensions,
                    vector_search_profile_name=VECTOR_PROFILE_NAME,
                ),
                SearchField(
                    name="summary_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self.vector_dimensions,
                    vector_search_profile_name=VECTOR_PROFILE_NAME,
                ),
            ]

        if container == ContainerType.INSIGHTS:
            return [
                SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
                SimpleField(name="user_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="agent_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchField(name="session_ids", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
                SimpleField(name="insight_type", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchableField(name="insight_text"),
                SearchableField(name="category", filterable=True, sortable=True),
                SimpleField(name="confidence", type=SearchFieldDataType.Double, filterable=True, sortable=True),
                SearchableField(name="importance", filterable=True, sortable=True),
                SimpleField(name="processed", type=SearchFieldDataType.Boolean, filterable=True, sortable=True),
                SearchField(name="source_insight_ids", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
                SearchField(name="source_session_ids", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
                SimpleField(name="date_added", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="last_accessed", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="access_count", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
                SimpleField(name="is_deleted", type=SearchFieldDataType.Boolean, filterable=True, sortable=True),
                SimpleField(name="deleted_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchableField(name="mutation_history_json"),
                SimpleField(name="created_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SimpleField(name="updated_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
                SearchField(
                    name="insight_vector",
                    type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                    searchable=True,
                    vector_search_dimensions=self.vector_dimensions,
                    vector_search_profile_name=VECTOR_PROFILE_NAME,
                ),
            ]

        return [
            SimpleField(name="id", type=SearchFieldDataType.String, key=True, filterable=True, sortable=True),
            SimpleField(name="user_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SimpleField(name="agent_id", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SimpleField(name="start_time", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SimpleField(name="end_time", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SearchableField(name="summary"),
            SearchField(name="key_topics", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
            SearchableField(name="key_topics_text"),
            SearchField(name="extracted_insights", type=SearchFieldDataType.Collection(SearchFieldDataType.String), filterable=True),
            SimpleField(name="status", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SimpleField(name="reflection_status", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SearchableField(name="cumulative_summary"),
            SimpleField(name="turn_count", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
            SimpleField(name="created_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SimpleField(name="updated_at", type=SearchFieldDataType.String, filterable=True, sortable=True),
            SearchField(
                name="summary_vector",
                type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
                searchable=True,
                vector_search_dimensions=self.vector_dimensions,
                vector_search_profile_name=VECTOR_PROFILE_NAME,
            ),
        ]

    def _prepare_document(self, container: ContainerType, document: Dict[str, Any]) -> Dict[str, Any]:
        """Convert an app document to an index document."""
        prepared = dict(document)

        for field in SERIALIZED_JSON_FIELDS[container]:
            value = prepared.pop(field, None)
            if value is None:
                value = {} if field == "metadata" else []
            prepared[f"{field}_json"] = json.dumps(value)

        for field in COLLECTION_FIELDS[container]:
            value = prepared.get(field)
            prepared[field] = [str(item) for item in value] if value is not None else []

        if container == ContainerType.SESSION_SUMMARIES:
            prepared["key_topics_text"] = " ".join(prepared.get("key_topics", []))

        return prepared

    def _decode_document(self, container: ContainerType, document: Dict[str, Any]) -> Dict[str, Any]:
        """Convert an index document back to the repo's document shape."""
        decoded = {k: v for k, v in document.items() if not k.startswith("@search.")}

        for field in SERIALIZED_JSON_FIELDS[container]:
            json_field = f"{field}_json"
            value = decoded.pop(json_field, None)
            if value is None:
                continue
            decoded[field] = json.loads(value)

        if container == ContainerType.SESSION_SUMMARIES:
            decoded.pop("key_topics_text", None)

        return decoded

    def _validate_filter_keys(self, container: ContainerType, filters: Optional[Dict[str, Any]]) -> None:
        """Reject unsupported filter keys early."""
        if not filters:
            return

        unknown = sorted(set(filters) - FILTERABLE_FIELDS[container])
        if unknown:
            raise ValueError(
                f"Unsupported filter keys for {container.value}: {', '.join(unknown)}"
            )

    def _parse_order_by(self, order_by: str) -> tuple[str, str]:
        """Convert repo order syntax into Azure AI Search order syntax."""
        descending = order_by.startswith("-")
        field_name = order_by[1:] if descending else order_by
        direction = "desc" if descending else "asc"
        return field_name, direction

    def _build_filter_expression(self, filters: Optional[Dict[str, Any]]) -> Optional[str]:
        """Convert equality filters into OData syntax."""
        if not filters:
            return None
        return " and ".join(self._format_filter_clause(key, value) for key, value in filters.items())

    def _format_filter_clause(self, key: str, value: Any) -> str:
        """Format one OData equality clause."""
        if value is None:
            return f"{key} eq null"
        if isinstance(value, bool):
            return f"{key} eq {'true' if value else 'false'}"
        if isinstance(value, (int, float)):
            return f"{key} eq {value}"
        if isinstance(value, str):
            escaped = value.replace("'", "''")
            return f"{key} eq '{escaped}'"
        raise ValueError(f"Unsupported filter value type for {key}: {type(value).__name__}")

    async def _run_search(
        self,
        container: ContainerType,
        *,
        search_text: Optional[str],
        filter_expression: Optional[str],
        top: int,
        vector_queries: Optional[List[VectorizedQuery]] = None,
        search_fields: Optional[List[str]] = None,
        order_by: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a search request and collect the results."""
        client = self._get_search_client(container)
        pager = await client.search(
            search_text=search_text,
            filter=filter_expression,
            top=top,
            select=self._selected_fields(container),
            vector_queries=vector_queries,
            search_fields=search_fields,
            order_by=order_by,
        )
        return [document async for document in pager]

    def _to_search_results(
        self,
        container: ContainerType,
        raw_results: Iterable[Dict[str, Any]],
        *,
        score_type: str,
    ) -> List[SearchResult]:
        """Normalize raw Azure AI Search hits into SearchResult objects."""
        results: List[SearchResult] = []
        for hit in raw_results:
            document = self._decode_document(container, hit)
            results.append(
                SearchResult(
                    id=document["id"],
                    document=document,
                    score=float(hit.get("@search.score", 0.0) or 0.0),
                    score_type=score_type,
                )
            )
        return results
