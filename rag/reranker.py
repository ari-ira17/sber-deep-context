"""
Cross-Encoder Reranker module for Meridian Knowledge Base (Task 3.5).
Re-ranks candidate documents using CrossEncoder models (bge-reranker / ms-marco)
with an intelligent fallback engine when neural reranking models are unavailable.
"""

import math
import re
from typing import List, Dict, Any, Optional


class Reranker:
    """
    Reranker engine for fine-grained document relevance scoring.
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        device: Optional[str] = None,
        use_fallback: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.use_fallback = use_fallback
        self._model = None
        self._load_model()

    def _load_model(self):
        """Attempt to load SentenceTransformers CrossEncoder."""
        try:
            from sentence_transformers import CrossEncoder
            kwargs = {}
            if self.device:
                kwargs["device"] = self.device
            self._model = CrossEncoder(self.model_name, **kwargs)
        except ImportError:
            
            self._model = None
        except Exception as e:
            print(f"[Reranker Warning] Could not load model '{self.model_name}': {e}")
            self._model = None

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank list of candidate documents against query.
        
        Args:
            query: User search query text.
            documents: Candidate documents from RRF or search stage.
            top_n: Limit number of reranked documents returned.
            
        Returns:
            Reranked list of documents enriched with rerank_score.
        """
        if not documents:
            return []

        top_n = top_n or len(documents)

        
        if self._model is not None:
            return self._neural_rerank(query, documents, top_n)

        
        return self._fallback_rerank(query, documents, top_n)

    def _neural_rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int,
    ) -> List[Dict[str, Any]]:
        """Neural reranking using CrossEncoder."""
        pairs = []
        for doc in documents:
            content = doc.get("page_content", "")
            pairs.append([query, content])

        try:
            scores = self._model.predict(pairs)
            if hasattr(scores, "tolist"):
                scores = scores.tolist()

            reranked = []
            for i, doc in enumerate(documents):
                doc_copy = dict(doc)
                raw_score = float(scores[i])
                
                norm_score = 1.0 / (1.0 + math.exp(-raw_score)) if abs(raw_score) > 1.0 else max(0.0, min(1.0, raw_score))
                doc_copy["rerank_score"] = round(norm_score, 4)
                doc_copy["score"] = doc_copy["rerank_score"]
                reranked.append(doc_copy)

            reranked.sort(key=lambda d: d["rerank_score"], reverse=True)
            return reranked[:top_n]
        except Exception as e:
            print(f"[Reranker Error] Neural rerank failed: {e}")
            return self._fallback_rerank(query, documents, top_n)

    def _fallback_rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_n: int,
    ) -> List[Dict[str, Any]]:
        """
        Fallback reranker calculating term overlap, exact exact match,
        and title/section relevance boosted by existing RRF score.
        """
        query_words = set(re.findall(r'[a-zA-Zа-яА-Я0-9_]+', query.lower()))
        if not query_words:
            return documents[:top_n]

        reranked = []
        for doc in documents:
            doc_copy = dict(doc)
            content = doc_copy.get("page_content", "").lower()
            meta = doc_copy.get("metadata", {})
            title = str(meta.get("product_name", "") or meta.get("slug", "")).lower()

            content_words = set(re.findall(r'[a-zA-Zа-яА-Я0-9_]+', content))
            
            
            overlap_count = len(query_words.intersection(content_words))
            overlap_ratio = overlap_count / max(1, len(query_words))

            
            title_match = 0.3 if any(w in title for w in query_words) else 0.0

            
            base_score = float(doc_copy.get("rrf_score", doc_copy.get("score", 0.5)))

            
            combined_score = 0.5 * overlap_ratio + 0.2 * title_match + 0.3 * base_score
            doc_copy["rerank_score"] = round(combined_score, 4)
            doc_copy["score"] = doc_copy["rerank_score"]
            reranked.append(doc_copy)

        reranked.sort(key=lambda d: d["rerank_score"], reverse=True)
        return reranked[:top_n]
