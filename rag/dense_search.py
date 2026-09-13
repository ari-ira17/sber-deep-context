"""
Dense Vector Search module for Meridian Knowledge Base (Task 3.2).
Provides vector similarity search using LanceDB, supporting metadata pre-filtering,
similarity score normalization, and fallback broadenings.
"""

from typing import List, Dict, Any, Optional, Union
import json
from rag.storage import LanceDBStorage
from rag.metadata_filter import MetadataFilter


class DenseSearch:
    """
    Dense Vector Search engine using LanceDB vector similarity.
    Implements Task 3.2 requirements for vector retrieval and hybrid pre-filtering.
    """

    def __init__(
        self,
        storage: Optional[LanceDBStorage] = None,
        metadata_filter: Optional[MetadataFilter] = None,
    ):
        self.storage = storage or LanceDBStorage()
        self.metadata_filter = metadata_filter or MetadataFilter(storage=self.storage)

    def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        where_clause: Optional[str] = None,
        product_code: Optional[str] = None,
        product_name: Optional[str] = None,
        section: Optional[str] = None,
        owner: Optional[str] = None,
        slug: Optional[str] = None,
        methodology_version: Optional[int] = None,
        lifecycle: Optional[str] = None,
        quality_tag: Optional[str] = None,
        metric: str = "cosine",
        enable_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Execute dense vector search on LanceDB.
        
        Args:
            query_vector: 768-dim float vector.
            top_k: Number of nearest documents to return.
            where_clause: Direct SQL WHERE clause (if provided).
            product_code, section, owner, slug, etc.: Metadata fields to construct filter.
            metric: Distance metric ("cosine", "L2", "dot").
            enable_fallback: If True, falls back to unconstrained search if 0 results found.
            
        Returns:
            List of result dicts containing score, page_content, and metadata.
        """
        tbl = self.storage.get_table()
        if tbl is None:
            return []

        
        sql_filter = where_clause or self.metadata_filter.build_sql_filter(
            product_code=product_code,
            product_name=product_name,
            section=section,
            owner=owner,
            slug=slug,
            methodology_version=methodology_version,
            lifecycle=lifecycle,
            quality_tag=quality_tag,
        )

        results = self._execute_vector_search(tbl, query_vector, top_k=top_k, where_clause=sql_filter, metric=metric)

        
        if not results and sql_filter and enable_fallback:
            
            fallback_filter = self.metadata_filter.build_sql_filter(
                product_code=product_code,
                product_name=product_name,
                section=section,
                owner=owner,
            )
            if fallback_filter and fallback_filter != sql_filter:
                results = self._execute_vector_search(tbl, query_vector, top_k=top_k, where_clause=fallback_filter, metric=metric)

            
            if not results and (product_code or product_name):
                product_filter = self.metadata_filter.build_sql_filter(
                    product_code=product_code,
                    product_name=product_name,
                )
                if product_filter and product_filter != fallback_filter:
                    results = self._execute_vector_search(tbl, query_vector, top_k=top_k, where_clause=product_filter, metric=metric)

            
            if not results:
                results = self._execute_vector_search(tbl, query_vector, top_k=top_k, where_clause="", metric=metric)

        return results

    def _execute_vector_search(
        self,
        tbl,
        query_vector: List[float],
        top_k: int,
        where_clause: str,
        metric: str,
    ) -> List[Dict[str, Any]]:
        """Helper to run vector query against LanceDB table."""
        try:
            query = tbl.search(query_vector).metric(metric).limit(top_k)
            if where_clause:
                query = query.where(where_clause)
            
            raw_results = query.to_list()
            return [self._format_search_result(r, metric=metric) for r in raw_results]
        except Exception as e:
            print(f"[DenseSearch Error] Vector search failed (where='{where_clause}'): {e}")
            return []

    def _format_search_result(self, record: Dict[str, Any], metric: str) -> Dict[str, Any]:
        """Format raw LanceDB search record into structured result."""
        dist = record.get("_distance", 0.0)
        
        
        if metric == "cosine":
            
            score = max(0.0, min(1.0, 1.0 - dist))
        elif metric == "L2":
            score = max(0.0, 1.0 / (1.0 + dist))
        else: 
            score = float(dist)

        formatted_doc = self.metadata_filter._format_record(record)
        formatted_doc["score"] = round(score, 4)
        formatted_doc["distance"] = round(float(dist), 4)
        return formatted_doc
