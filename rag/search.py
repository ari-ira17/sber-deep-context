"""
Hybrid Search Orchestration module for Meridian Knowledge Base (Task 3.6).
Combines Metadata Filtering, Dense Vector Search, BM25 Search, RRF Fusion, and Cross-Encoder Reranking
into a unified high-level search engine.

Interface for Participant 4 (Agent Engineer):
    Input:  query_text (str) + parsed metadata filters (product_code, slug, etc.)
    Output: List[Dict] of top-k documents, each with page_content, metadata, score
"""

from typing import List, Dict, Any, Optional
import os
import yaml

from rag.storage import LanceDBStorage, VECTOR_DIM
from rag.metadata_filter import MetadataFilter
from rag.dense_search import DenseSearch
from rag.bm25_search import BM25Search
from rag.rrf import RRFFusion
from rag.reranker import Reranker
from rag.embedder import get_embedder


class HybridSearchEngine:
    """
    Unified Orchestrator for Hybrid RAG Search (Metadata + Dense + BM25 + RRF + Reranker).
    """

    def __init__(
        self,
        storage: Optional[LanceDBStorage] = None,
        config_path: Optional[str] = None,
    ):
        self.config = self._load_config(config_path)
        
        # Load from config or use fallbacks
        k_rrf = self.config.get("search", {}).get("k_rrf", 60)
        reranker_model = self.config.get("models", {}).get("reranker", "BAAI/bge-reranker-base")
        embedder_model = self.config.get("models", {}).get("embedder", "intfloat/multilingual-e5-base")
        
        self.storage = storage or LanceDBStorage()
        self.metadata_filter = MetadataFilter(storage=self.storage)
        self.dense_search = DenseSearch(storage=self.storage, metadata_filter=self.metadata_filter)
        self.bm25_search = BM25Search(storage=self.storage, metadata_filter=self.metadata_filter)
        self.rrf_fusion = RRFFusion(k=k_rrf)
        self.reranker = Reranker(model_name=reranker_model)
        self.embedder = get_embedder()

    def _load_config(self, config_path: Optional[str]) -> Dict[str, Any]:
        if not config_path:
            # Default to configs/search_config.yaml in the project root
            root_dir = os.path.dirname(os.path.dirname(__file__))
            config_path = os.path.join(root_dir, "configs", "search_config.yaml")
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                print(f"[Config Warning] Failed to load {config_path}: {e}")
        return {}

    def search(
        self,
        query_text: str,
        query_vector: Optional[List[float]] = None,
        top_k: Optional[int] = None,
        candidate_k: Optional[int] = None,
        product_code: Optional[str] = None,
        product_name: Optional[str] = None,
        section: Optional[str] = None,
        owner: Optional[str] = None,
        slug: Optional[str] = None,
        methodology_version: Optional[int] = None,
        lifecycle: Optional[str] = None,
        quality_tag: Optional[str] = None,
        where_clause: Optional[str] = None,
        enable_reranker: Optional[bool] = None,
        enable_fast_path: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """
        Execute full RAG search pipeline.
        
        Steps:
            1. Fast-Path direct metadata lookup (if exact slug/code requested).
            2. Dense Vector Search.
            3. BM25 Keyword Search.
            4. RRF Fusion of Dense + BM25 results.
            5. Cross-Encoder Reranking of fused top candidates.
        """
        # Apply config defaults if parameters are not provided
        search_cfg = self.config.get("search", {})
        top_k = top_k if top_k is not None else search_cfg.get("top_k", 5)
        candidate_k = candidate_k if candidate_k is not None else search_cfg.get("candidate_k", 20)
        enable_reranker = enable_reranker if enable_reranker is not None else search_cfg.get("enable_reranker", True)
        enable_fast_path = enable_fast_path if enable_fast_path is not None else search_cfg.get("enable_fast_path", True)
        min_reranker_score = search_cfg.get("min_reranker_score", 0.0)

        # Step 1: Fast-Path Exact Metadata Match
        if enable_fast_path and slug:
            exact_docs = self.metadata_filter.metadata_lookup(
                slug=slug,
                product_code=product_code,
                product_name=product_name,
                limit=top_k,
                enable_broadening=False,
            )
            if exact_docs:
                for doc in exact_docs:
                    doc["score"] = 1.0
                    doc["search_mode"] = "fast_path_exact_slug"
                return exact_docs[:top_k]

        # Auto-embed query_text if Participant 4 did not supply a vector
        if query_vector and len(query_vector) == VECTOR_DIM:
            vec = query_vector
        else:
            vec = self.embedder.embed(query_text)

        # Step 2: Dense Search
        dense_results = self.dense_search.search(
            query_vector=vec,
            top_k=candidate_k,
            where_clause=where_clause,
            product_code=product_code,
            product_name=product_name,
            section=section,
            owner=owner,
            slug=slug,
            methodology_version=methodology_version,
            lifecycle=lifecycle,
            quality_tag=quality_tag,
        )

        # Step 3: BM25 Search
        bm25_results = self.bm25_search.search(
            query_text=query_text,
            top_k=candidate_k,
            where_clause=where_clause,
            product_code=product_code,
            product_name=product_name,
            section=section,
            owner=owner,
            slug=slug,
            methodology_version=methodology_version,
            lifecycle=lifecycle,
            quality_tag=quality_tag,
        )

        # Step 4: RRF Fusion
        fused_results = self.rrf_fusion.fuse(
            dense_results=dense_results,
            bm25_results=bm25_results,
            top_k=candidate_k,
        )

        if not fused_results:
            return []

        # Step 5: Cross-Encoder Reranking
        if enable_reranker:
            final_results = self.reranker.rerank(
                query=query_text,
                documents=fused_results,
                top_n=top_k,
            )
            # Filter out results below min score threshold
            if min_reranker_score > 0.0:
                final_results = [doc for doc in final_results if doc.get("score", 0) >= min_reranker_score]
        else:
            final_results = fused_results[:top_k]

        return final_results


def search(
    query_text: str,
    query_vector: Optional[List[float]] = None,
    top_k: int = 5,
    storage: Optional[LanceDBStorage] = None,
    **kwargs,
) -> List[Dict[str, Any]]:
    """
    Convenience function for hybrid RAG search.
    """
    engine = HybridSearchEngine(storage=storage)
    return engine.search(
        query_text=query_text,
        query_vector=query_vector,
        top_k=top_k,
        **kwargs,
    )
