"""
Reciprocal Rank Fusion (RRF) module for Meridian Knowledge Base (Task 3.4).
Combines rankings from Dense Vector Search and BM25 Search into a single score.
"""

from typing import List, Dict, Any, Optional


class RRFFusion:
    """
    Reciprocal Rank Fusion engine for hybrid retrieval.
    Merges dense and sparse (BM25) search results.
    """

    def __init__(self, k: int = 60):
        """
        Args:
            k: Smoothing constant for RRF formula (default 60).
        """
        self.k = k

    def fuse(
        self,
        dense_results: List[Dict[str, Any]],
        bm25_results: List[Dict[str, Any]],
        top_k: int = 10,
        dense_weight: float = 1.0,
        bm25_weight: float = 1.0,
    ) -> List[Dict[str, Any]]:
        """
        Fuse dense and BM25 ranked document lists.
        
        Args:
            dense_results: Ranked list of documents from Dense Search.
            bm25_results: Ranked list of documents from BM25 Search.
            top_k: Number of combined top documents to return.
            dense_weight: Weight multiplier for dense ranks.
            bm25_weight: Weight multiplier for BM25 ranks.
            
        Returns:
            List of combined documents sorted by RRF score descending.
        """
        rrf_scores: Dict[str, float] = {}
        docs_map: Dict[str, Dict[str, Any]] = {}
        rank_info: Dict[str, Dict[str, Any]] = {}

        
        for rank, doc in enumerate(dense_results, start=1):
            doc_id = self._get_doc_key(doc)
            if not doc_id:
                continue

            score = dense_weight * (1.0 / (self.k + rank))
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + score
            docs_map[doc_id] = doc

            if doc_id not in rank_info:
                rank_info[doc_id] = {}
            rank_info[doc_id]["dense_rank"] = rank
            rank_info[doc_id]["dense_score"] = doc.get("score", 0.0)

        
        for rank, doc in enumerate(bm25_results, start=1):
            doc_id = self._get_doc_key(doc)
            if not doc_id:
                continue

            score = bm25_weight * (1.0 / (self.k + rank))
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0.0) + score

            if doc_id not in docs_map:
                docs_map[doc_id] = doc

            if doc_id not in rank_info:
                rank_info[doc_id] = {}
            rank_info[doc_id]["bm25_rank"] = rank
            rank_info[doc_id]["bm25_score"] = doc.get("score", 0.0)

        
        sorted_doc_ids = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)

        
        fused_documents = []
        for doc_id in sorted_doc_ids[:top_k]:
            doc_copy = dict(docs_map[doc_id])
            doc_copy["rrf_score"] = round(rrf_scores[doc_id], 6)
            doc_copy["score"] = doc_copy["rrf_score"]
            doc_copy["retrieval_meta"] = {
                "dense_rank": rank_info[doc_id].get("dense_rank"),
                "dense_score": rank_info[doc_id].get("dense_score"),
                "bm25_rank": rank_info[doc_id].get("bm25_rank"),
                "bm25_score": rank_info[doc_id].get("bm25_score"),
            }
            fused_documents.append(doc_copy)

        return fused_documents

    def _get_doc_key(self, doc: Dict[str, Any]) -> str:
        """Extract unique document identifier key."""
        meta = doc.get("metadata", {})
        doc_id = meta.get("doc_id") or doc.get("doc_id") or meta.get("slug") or doc.get("slug")
        return str(doc_id) if doc_id else ""
