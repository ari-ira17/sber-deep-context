"""
LanceDB Client export for app/db layer.
Re-exports storage and search modules from rag package.
"""

from rag.storage import LanceDBStorage, format_document_record, get_lance_schema
from rag.metadata_filter import MetadataFilter
from rag.dense_search import DenseSearch

__all__ = [
    "LanceDBStorage",
    "format_document_record",
    "get_lance_schema",
    "MetadataFilter",
    "DenseSearch",
]
