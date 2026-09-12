"""
RAG package for Meridian Knowledge Base.
Provides Metadata Filtering, LanceDB Storage, Dense Vector Search, BM25 Search, RRF Fusion, Reranking, and Hybrid Search Engine.
"""

from rag.storage import LanceDBStorage
from rag.metadata_filter import MetadataFilter
from rag.dense_search import DenseSearch
from rag.bm25_search import BM25Search, SimpleBM25
from rag.rrf import RRFFusion
from rag.reranker import Reranker
from rag.search import HybridSearchEngine, search, to_document_context, to_document_contexts

__all__ = [
    "LanceDBStorage",
    "MetadataFilter",
    "DenseSearch",
    "BM25Search",
    "SimpleBM25",
    "RRFFusion",
    "Reranker",
    "HybridSearchEngine",
    "search",
    "to_document_context",
    "to_document_contexts",
]
