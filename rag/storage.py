"""
LanceDB Storage module for Meridian Knowledge Base.
Handles database initialization, schema definition, scalar indexing, and document insertion.
"""

import os
from typing import List, Dict, Any, Optional, Union
import lancedb
import pyarrow as pa

VECTOR_DIM = 768
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "lancedb")
TABLE_NAME = "meridian_documents"


def get_lance_schema() -> pa.Schema:
    """Return the PyArrow schema for Meridian Knowledge Base documents."""
    return pa.schema([
        pa.field("doc_id", pa.string()),
        pa.field("vector", pa.list_(pa.float32(), VECTOR_DIM)),
        pa.field("page_content", pa.string()),
        pa.field("product_code", pa.string()),
        pa.field("product_name", pa.string()),
        pa.field("section", pa.string()),
        pa.field("owner", pa.string()),
        pa.field("methodology_version", pa.int64()),
        pa.field("lifecycle", pa.string()),
        pa.field("quality_tags_str", pa.string()),  # Comma-separated tags for SQL LIKE / FTS
        pa.field("quality_tags_json", pa.string()), # Original JSON string
        pa.field("slug", pa.string()),
        pa.field("attachment_path", pa.string()),
        pa.field("attachment_format", pa.string()),
        pa.field("attachment_text", pa.string()),
        pa.field("updated_at", pa.string()),
        pa.field("valid_from", pa.string()),
        pa.field("synthetic", pa.bool_()),
        pa.field("dataset_version", pa.string()),
    ])


def format_document_record(doc: Dict[str, Any], vector: Optional[List[float]] = None) -> Dict[str, Any]:
    """
    Format a document dictionary into a row compliant with LanceDB schema.
    Safely handles nested {'metadata': {...}} structure or flat record dicts.
    """
    if isinstance(doc.get("metadata"), dict):
        metadata = doc["metadata"]
    else:
        metadata = doc
    
    # Extract vector
    vec = vector or doc.get("vector") or metadata.get("vector")
    if vec is None:
        # Default zero vector if not provided
        vec = [0.0] * VECTOR_DIM
    elif len(vec) != VECTOR_DIM:
        raise ValueError(f"Vector dimension mismatch: expected {VECTOR_DIM}, got {len(vec)}")

    # Format quality tags
    raw_tags = metadata.get("quality_tags") or doc.get("quality_tags") or metadata.get("quality_tags_json") or doc.get("quality_tags_json") or []
    if isinstance(raw_tags, str):
        try:
            import json
            parsed = json.loads(raw_tags)
            if isinstance(parsed, list):
                raw_tags = parsed
            else:
                raw_tags = [raw_tags]
        except Exception:
            raw_tags = [t.strip() for t in raw_tags.split(",") if t.strip()]

    if isinstance(raw_tags, list):
        quality_tags_str = ",".join(str(t) for t in raw_tags)
        import json
        quality_tags_json = json.dumps(raw_tags, ensure_ascii=False)
    else:
        quality_tags_str = str(raw_tags)
        import json
        quality_tags_json = json.dumps([str(raw_tags)], ensure_ascii=False)

    doc_id = str(metadata.get("doc_id") or doc.get("doc_id") or doc.get("id") or "")
    methodology_version = metadata.get("methodology_version") if metadata.get("methodology_version") is not None else doc.get("methodology_version")
    try:
        methodology_version = int(methodology_version) if methodology_version is not None else 0
    except (ValueError, TypeError):
        methodology_version = 0

    return {
        "doc_id": doc_id,
        "vector": vec,
        "page_content": str(doc.get("page_content") or doc.get("content") or metadata.get("page_content") or ""),
        "product_code": str(metadata.get("product_code") or doc.get("product_code") or ""),
        "product_name": str(metadata.get("product_name") or doc.get("product_name") or ""),
        "section": str(metadata.get("section") or doc.get("section") or ""),
        "owner": str(metadata.get("owner") or doc.get("owner") or ""),
        "methodology_version": methodology_version,
        "lifecycle": str(metadata.get("lifecycle") or doc.get("lifecycle") or ""),
        "quality_tags_str": quality_tags_str,
        "quality_tags_json": quality_tags_json,
        "slug": str(metadata.get("slug") or doc.get("slug") or ""),
        "attachment_path": str(metadata.get("attachment_path") or doc.get("attachment_path") or ""),
        "attachment_format": str(metadata.get("attachment_format") or doc.get("attachment_format") or ""),
        "attachment_text": str(metadata.get("attachment_text") or doc.get("attachment_text") or ""),
        "updated_at": str(metadata.get("updated_at") or doc.get("updated_at") or ""),
        "valid_from": str(metadata.get("valid_from") or doc.get("valid_from") or ""),
        "synthetic": bool(metadata.get("synthetic") if metadata.get("synthetic") is not None else doc.get("synthetic", False)),
        "dataset_version": str(metadata.get("dataset_version") or doc.get("dataset_version") or "v1.0"),
    }


class LanceDBStorage:
    """Manager class for LanceDB dataset interaction."""
    
    def __init__(self, db_path: str = DEFAULT_DB_PATH, table_name: str = TABLE_NAME):
        self.db_path = db_path
        self.table_name = table_name
        os.makedirs(self.db_path, exist_ok=True)
        self.db = lancedb.connect(self.db_path)
        self._table = None

    def get_table_names(self) -> List[str]:
        """Get list of table names in DB safely across LanceDB versions."""
        try:
            res = self.db.list_tables()
            if isinstance(res, list):
                return res
            if hasattr(res, "tables"):
                return res.tables
        except Exception:
            pass
        try:
            return list(self.db.table_names())
        except Exception:
            return []

    def get_table(self):
        """Get or open LanceDB table."""
        if self._table is not None:
            return self._table
        if self.table_name in self.get_table_names():
            self._table = self.db.open_table(self.table_name)
            return self._table
        return None

    def create_table(self, records: Optional[List[Dict[str, Any]]] = None, mode: str = "overwrite"):
        """Create table with PyArrow schema and initial records."""
        schema = get_lance_schema()
        if records:
            formatted_records = [format_document_record(r) for r in records]
            table = self.db.create_table(self.table_name, data=formatted_records, schema=schema, mode=mode)
        else:
            table = self.db.create_table(self.table_name, schema=schema, mode=mode)
        
        self.create_scalar_indices(table)
        self._table = table
        return table

    def create_scalar_indices(self, table=None):
        """Create scalar indices for fast metadata filtering on key fields."""
        tbl = table or self.get_table()
        if tbl is None:
            return
        
        # LanceDB scalar indexing for fast metadata filtering
        for col in ["product_code", "slug", "owner", "section"]:
            try:
                tbl.create_scalar_index(col, replace=True)
            except Exception as e:
                # Log or ignore if scalar index creation is not supported for specific version
                pass

    def add_documents(self, documents: List[Dict[str, Any]], vectors: Optional[List[List[float]]] = None):
        """Add batch of documents with optional separate vectors list."""
        tbl = self.get_table()
        if tbl is None:
            # Create table if it doesn't exist
            records = []
            for i, doc in enumerate(documents):
                vec = vectors[i] if vectors and i < len(vectors) else None
                records.append(format_document_record(doc, vector=vec))
            return self.create_table(records=records)

        formatted_records = []
        for i, doc in enumerate(documents):
            vec = vectors[i] if vectors and i < len(vectors) else None
            formatted_records.append(format_document_record(doc, vector=vec))
        
        tbl.add(formatted_records)
        return tbl

    def count(self) -> int:
        """Return total document count in table."""
        tbl = self.get_table()
        if tbl is None:
            return 0
        return len(tbl)
