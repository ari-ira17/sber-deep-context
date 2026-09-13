"""
BM25 Full-Text Search (FTS) module for Meridian Knowledge Base (Task 3.3).
Provides keyword/FTS search using LanceDB FTS capabilities with a fallback BM25 engine.
"""

import math
import re
from collections import Counter
from typing import List, Dict, Any, Optional
from rag.storage import LanceDBStorage
from rag.metadata_filter import MetadataFilter


import pymorphy3

_MORPH_ANALYZER = None


def _get_morph():
    global _MORPH_ANALYZER
    if _MORPH_ANALYZER is None:
        try:
            _MORPH_ANALYZER = pymorphy3.MorphAnalyzer()
        except Exception as e:
            print(f"[pymorphy3 Warning] Failed to initialize MorphAnalyzer: {e}")
            _MORPH_ANALYZER = False
    return _MORPH_ANALYZER if _MORPH_ANALYZER is not False else None


def tokenize(text: str, lemmatize: bool = True) -> List[str]:
    """Tokenize Russian/English text into lowercase words with optional pymorphy3 lemmatization."""
    if not text:
        return []
    raw_tokens = re.findall(r'[a-zA-Zа-яА-ЯёЁ0-9_]+', text.lower())
    if not lemmatize:
        return raw_tokens

    morph = _get_morph()
    if morph is None:
        return raw_tokens

    lemmas = []
    for token in raw_tokens:
        if token.isdigit() or "_" in token or len(token) <= 2:
            lemmas.append(token)
        else:
            try:
                lemma = morph.parse(token)[0].normal_form
                lemmas.append(lemma)
            except Exception:
                lemmas.append(token)
    return lemmas



class SimpleBM25:
    """Lightweight in-memory BM25 scorer for fallback retrieval."""

    def __init__(self, corpus: List[str], k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.corpus_size = len(corpus)
        self.doc_tokens = [tokenize(doc) for doc in corpus]
        self.doc_lens = [len(tokens) for tokens in self.doc_tokens]
        self.avgdl = sum(self.doc_lens) / max(1, self.corpus_size)

        
        self.df = Counter()
        for tokens in self.doc_tokens:
            self.df.update(set(tokens))

        
        self.idf = {}
        for word, freq in self.df.items():
            self.idf[word] = math.log((self.corpus_size - freq + 0.5) / (freq + 0.5) + 1.0)

    def get_scores(self, query: str) -> List[float]:
        """Compute BM25 scores for all corpus documents against query."""
        query_tokens = tokenize(query)
        scores = [0.0] * self.corpus_size
        if not query_tokens or self.corpus_size == 0:
            return scores

        for q_token in query_tokens:
            if q_token not in self.idf:
                continue
            idf_val = self.idf[q_token]
            for doc_idx, tokens in enumerate(self.doc_tokens):
                tf = tokens.count(q_token)
                if tf == 0:
                    continue
                doc_len = self.doc_lens[doc_idx]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * (doc_len / max(1, self.avgdl)))
                scores[doc_idx] += idf_val * (numerator / denominator)

        return scores


class BM25Search:
    """
    BM25 Search engine for LanceDB table.
    Implements Task 3.3 requirements for full-text search.
    """

    def __init__(
        self,
        storage: Optional[LanceDBStorage] = None,
        metadata_filter: Optional[MetadataFilter] = None,
    ):
        self.storage = storage or LanceDBStorage()
        self.metadata_filter = metadata_filter or MetadataFilter(storage=self.storage)

    def create_fts_index(self, field_name: str = "page_content", replace: bool = True) -> bool:
        """Create LanceDB Full-Text Search (FTS) index on specified field."""
        tbl = self.storage.get_table()
        if tbl is None:
            return False
        try:
            tbl.create_fts_index(field_name, replace=replace)
            return True
        except Exception as e:
            print(f"[BM25Search Warning] Could not create LanceDB FTS index: {e}")
            return False

    def search(
        self,
        query_text: str,
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
        enable_fallback: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Execute BM25 keyword/FTS search on LanceDB.
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

        
        results = self._execute_native_fts(tbl, query_text, top_k=top_k, where_clause=sql_filter)
        if results:
            return results

        
        results = self._execute_fallback_bm25(tbl, query_text, top_k=top_k, where_clause=sql_filter)

        
        if not results and sql_filter and enable_fallback:
            fallback_filter = self.metadata_filter.build_sql_filter(
                product_code=product_code,
                product_name=product_name,
                section=section,
                owner=owner,
            )
            if fallback_filter and fallback_filter != sql_filter:
                results = self._execute_fallback_bm25(tbl, query_text, top_k=top_k, where_clause=fallback_filter)

            if not results:
                results = self._execute_fallback_bm25(tbl, query_text, top_k=top_k, where_clause="")

        return results

    def _execute_native_fts(
        self,
        tbl,
        query_text: str,
        top_k: int,
        where_clause: str,
    ) -> List[Dict[str, Any]]:
        """Attempt native LanceDB FTS query."""
        try:
            query = tbl.search(query_text, query_type="fts").limit(top_k)
            if where_clause:
                query = query.where(where_clause)
            raw_results = query.to_list()
            if not raw_results:
                return []
            
            formatted = []
            for r in raw_results:
                doc = self.metadata_filter._format_record(r)
                score = r.get("_score", r.get("score", 1.0))
                doc["score"] = round(float(score), 4)
                formatted.append(doc)
            return formatted
        except Exception:
            return []

    def _execute_fallback_bm25(
        self,
        tbl,
        query_text: str,
        top_k: int,
        where_clause: str,
    ) -> List[Dict[str, Any]]:
        """Fallback Python BM25 execution over filtered documents."""
        try:
            query = tbl.search()
            if where_clause:
                query = query.where(where_clause)
            records = query.to_list()
            if not records:
                return []

            corpus = [r.get("page_content", "") + " " + r.get("attachment_text", "") for r in records]
            bm25 = SimpleBM25(corpus)
            scores = bm25.get_scores(query_text)

            indexed_scores = [(idx, score) for idx, score in enumerate(scores) if score > 0.0]
            indexed_scores.sort(key=lambda x: x[1], reverse=True)

            results = []
            max_score = indexed_scores[0][1] if indexed_scores else 1.0
            for idx, score in indexed_scores[:top_k]:
                record = records[idx]
                doc = self.metadata_filter._format_record(record)
                norm_score = score / max_score if max_score > 0 else 0.0
                doc["score"] = round(float(norm_score), 4)
                results.append(doc)

            return results
        except Exception as e:
            print(f"[BM25Search Fallback Error]: {e}")
            return []
