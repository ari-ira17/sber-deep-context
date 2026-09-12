"""
Metadata Filtering module for Meridian Knowledge Base (Task 3.1).
Provides fast metadata filtering, SQL filter construction, fast-path lookup,
and broadening fallback logic for ambiguous/over-constrained queries.
"""

from typing import List, Dict, Any, Optional
import json
from rag.storage import LanceDBStorage, TABLE_NAME


def sanitize_sql_value(val: Any) -> str:
    """Escape single quotes for SQL string literals."""
    if isinstance(val, str):
        escaped = val.replace("'", "''")
        return f"'{escaped}'"
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, bool):
        return "true" if val else "false"
    return f"'{str(val)}'"


class MetadataFilter:
    """
    Metadata filter engine for LanceDB table.
    Implements Task 3.1 metadata filtering and Fast-Path lookups.
    """

    def __init__(self, storage: Optional[LanceDBStorage] = None):
        self.storage = storage or LanceDBStorage()

    def build_sql_filter(
        self,
        product_code: Optional[str] = None,
        product_name: Optional[str] = None,
        section: Optional[str] = None,
        owner: Optional[str] = None,
        slug: Optional[str] = None,
        methodology_version: Optional[int] = None,
        lifecycle: Optional[str] = None,
        quality_tag: Optional[str] = None,
        dataset_version: Optional[str] = None,
        extra_filters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Build SQL WHERE clause for LanceDB scalar filtering.
        """
        clauses = []

        if product_code:
            clauses.append(f"product_code = {sanitize_sql_value(product_code)}")
        if product_name:
            clauses.append(f"product_name = {sanitize_sql_value(product_name)}")
        if section:
            clauses.append(f"section = {sanitize_sql_value(section)}")
        if owner:
            clauses.append(f"owner = {sanitize_sql_value(owner)}")
        if slug:
            clauses.append(f"slug = {sanitize_sql_value(slug)}")
        if methodology_version is not None:
            clauses.append(f"methodology_version = {int(methodology_version)}")
        if lifecycle:
            clauses.append(f"lifecycle = {sanitize_sql_value(lifecycle)}")
        if quality_tag:
            tag_escaped = quality_tag.replace("'", "''")
            clauses.append(f"quality_tags_str LIKE '%{tag_escaped}%'")
        if dataset_version:
            clauses.append(f"dataset_version = {sanitize_sql_value(dataset_version)}")

        if extra_filters:
            for key, val in extra_filters.items():
                if val is not None:
                    clauses.append(f"{key} = {sanitize_sql_value(val)}")

        return " AND ".join(clauses) if clauses else ""

    def filter_documents(
        self,
        where_clause: str,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Execute SQL filter query on LanceDB table.
        """
        tbl = self.storage.get_table()
        if tbl is None:
            return []

        try:
            query_builder = tbl.search()
            if where_clause:
                query_builder = query_builder.where(where_clause)
            
            results = query_builder.limit(limit).to_list()
            return [self._format_record(r) for r in results]
        except Exception as e:
            # Fallback handling if filter execution fails
            print(f"[MetadataFilter Error] Failed to execute filter '{where_clause}': {e}")
            return []

    def metadata_lookup(
        self,
        product_code: Optional[str] = None,
        product_name: Optional[str] = None,
        section: Optional[str] = None,
        owner: Optional[str] = None,
        slug: Optional[str] = None,
        methodology_version: Optional[int] = None,
        lifecycle: Optional[str] = None,
        quality_tag: Optional[str] = None,
        limit: int = 10,
        enable_broadening: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Fast-Path direct metadata lookup for LanceDB storage.
        If enable_broadening is True and 0 results found, automatically broadens search.
        """
        sql_filter = self.build_sql_filter(
            product_code=product_code,
            product_name=product_name,
            section=section,
            owner=owner,
            slug=slug,
            methodology_version=methodology_version,
            lifecycle=lifecycle,
            quality_tag=quality_tag,
        )

        results = self.filter_documents(sql_filter, limit=limit)
        if results or not enable_broadening:
            return results

        # --- Broadening Fallback Strategy ---
        # Level 1: Drop slug & quality_tag & methodology_version
        if slug or quality_tag or methodology_version is not None:
            sql_fallback_1 = self.build_sql_filter(
                product_code=product_code,
                product_name=product_name,
                section=section,
                owner=owner,
                lifecycle=lifecycle,
            )
            results = self.filter_documents(sql_fallback_1, limit=limit)
            if results:
                return results

        # Level 2: Keep only product_code or product_name
        if product_code or product_name:
            sql_fallback_2 = self.build_sql_filter(
                product_code=product_code,
                product_name=product_name,
            )
            results = self.filter_documents(sql_fallback_2, limit=limit)
            if results:
                return results

        # Level 3: Keep section or owner
        if section or owner:
            sql_fallback_3 = self.build_sql_filter(
                section=section,
                owner=owner,
            )
            results = self.filter_documents(sql_fallback_3, limit=limit)
            if results:
                return results

        return []

    def _format_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a LanceDB record back to standard JSON document structure."""
        quality_tags_json = record.get("quality_tags_json")
        quality_tags = []
        if quality_tags_json:
            try:
                quality_tags = json.loads(quality_tags_json)
            except Exception:
                quality_tags = [t.strip() for t in record.get("quality_tags_str", "").split(",") if t.strip()]
        elif record.get("quality_tags_str"):
            quality_tags = [t.strip() for t in record.get("quality_tags_str", "").split(",") if t.strip()]

        return {
            "page_content": record.get("page_content", ""),
            "metadata": {
                "doc_id": record.get("doc_id", ""),
                "product_code": record.get("product_code", ""),
                "product_name": record.get("product_name", ""),
                "section": record.get("section", ""),
                "owner": record.get("owner", ""),
                "methodology_version": record.get("methodology_version", 0),
                "lifecycle": record.get("lifecycle", ""),
                "quality_tags": quality_tags,
                "slug": record.get("slug", ""),
                "attachment_path": record.get("attachment_path", ""),
                "attachment_format": record.get("attachment_format", ""),
                "attachment_text": record.get("attachment_text", ""),
                "updated_at": record.get("updated_at", ""),
                "valid_from": record.get("valid_from", ""),
                "synthetic": record.get("synthetic", False),
                "dataset_version": record.get("dataset_version", "v1.0"),
            }
        }
