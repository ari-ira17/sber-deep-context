"""Evidence Service for Meridian Knowledge Base.

Provides deep auditability, ground-truth inspection, and rich formatting
for documents and attachments (CSV, ASM, PNG/OCR, PDF, DOCX, etc.).
"""

import os
import re
import json
import html
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
import markdown

logger = logging.getLogger(__name__)

PRODUCT_COLOR_PALETTE: Dict[str, str] = {
    "P701": "#FF6B6B",  # Искра (red-orange)
    "P702": "#4D96FF",  # Росинка (blue)
    "P703": "#FFD93D",  # Янтарь (amber)
    "P704": "#6BCB77",  # Мостик (green)
    "P705": "#9B51E0",  # Тихая Гавань (purple)
    "P706": "#FF9F45",  # Лавка (orange)
    "P707": "#F24A72",  # Комета (crimson)
    "P708": "#00C897",  # Призма (teal)
    "P709": "#2F80ED",  # Орбитариум (sapphire)
    "P710": "#56CCF2",  # Парус (cyan)
    "P711": "#EB5757",  # Бастион (ruby)
    "P712": "#F2994A",  # Ритм (coral)
    "P713": "#BB6BD9",  # Зонтик (lilac)
    "P714": "#828282",  # Созвездие (slate)
    "P715": "#27AE60",  # Мозаика (emerald)
    "P716": "#E2B93B",  # Маховик (gold)
    "P717": "#795548",  # Пергамент (bronze)
    "P718": "#607D8B",  # Облачный Сад (blue-grey)
}
DEFAULT_PRODUCT_COLOR = "#10B981"


def parse_table_data(text: str) -> Optional[Dict[str, Any]]:
    """Parse markdown table or CSV text into headers and rows for interactive rendering."""
    if not text or not text.strip():
        return None
    
    clean_text = text.strip()
    lines = [l.strip() for l in clean_text.splitlines() if l.strip()]
    if not lines:
        return None

    # Check for Markdown table format (| col1 | col2 |)
    if lines[0].startswith("|") and "|" in lines[0][1:]:
        header_parts = [c.strip() for c in lines[0].strip("|").split("|")]
        rows = []
        data_lines = lines[1:]
        # Skip divider line if present (|---|---|)
        if data_lines and "---" in data_lines[0]:
            data_lines = data_lines[1:]
        
        for dl in data_lines:
            if dl.startswith("|"):
                cells = [c.strip() for c in dl.strip("|").split("|")]
                # Pad cells if needed
                while len(cells) < len(header_parts):
                    cells.append("")
                rows.append(cells[:len(header_parts)])
        
        return {
            "type": "table",
            "headers": header_parts,
            "rows": rows,
            "total_rows": len(rows),
        }

    # Check for CSV delimiter (comma or semicolon) anywhere in the text
    table_lines = []
    delimiter = None
    
    for line in lines:
        if delimiter:
            if delimiter in line:
                table_lines.append(line)
            else:
                # Table ended
                break
        else:
            if ";" in line and line.count(";") > 1:
                delimiter = ";"
                table_lines.append(line)
            elif "," in line and line.count(",") > 1:
                delimiter = ","
                table_lines.append(line)

    if delimiter and len(table_lines) > 1:
        try:
            import csv
            import io
            reader = csv.reader(io.StringIO("\n".join(table_lines)), delimiter=delimiter)
            rows = list(reader)
            if rows and len(rows) > 1:
                return {
                    "type": "table",
                    "headers": [h.strip() for h in rows[0]],
                    "rows": [[c.strip() for c in r] for r in rows[1:]],
                    "total_rows": len(rows) - 1,
                }
        except Exception as e:
            logger.debug(f"Failed CSV parse: {e}")

    return None


def convert_csv_tables_to_markdown(text: str) -> str:
    """Finds semicolon-delimited CSV tables in text and converts them to Markdown tables."""
    import csv
    import io

    lines = text.splitlines()
    out_lines = []
    table_buffer = []

    def flush_table_buffer():
        if not table_buffer:
            return
        reader = csv.reader(io.StringIO("\n".join(table_buffer)), delimiter=";")
        try:
            rows = list(reader)
        except Exception:
            out_lines.extend(table_buffer)
            table_buffer.clear()
            return

        # Strip trailing empty cell if line ended with semicolon
        cleaned_rows = []
        for r in rows:
            if r and r[-1] == "":
                r = r[:-1]
            cleaned_rows.append(r)

        if len(cleaned_rows) > 1 and len(cleaned_rows[0]) > 1:
            for i, row in enumerate(cleaned_rows):
                md_line = "| " + " | ".join(cell.replace("\n", " ").strip() for cell in row) + " |"
                out_lines.append(md_line)
                if i == 0:
                    sep_line = "| " + " | ".join(["---"] * len(row)) + " |"
                    out_lines.append(sep_line)
        else:
            out_lines.extend(table_buffer)
        table_buffer.clear()

    for line in lines:
        stripped = line.strip()
        is_pipe_table = stripped.startswith("|") or line.count("|") >= 2
        is_csv_candidate = (";" in line) and (line.count(";") >= 1) and not is_pipe_table

        if is_csv_candidate:
            table_buffer.append(line)
        else:
            flush_table_buffer()
            out_lines.append(line)

    flush_table_buffer()
    return "\n".join(out_lines)


def format_code_with_lines(code_text: str, lang: str = "text") -> str:
    """Escape and format code with line numbers for syntax inspection."""
    lines = code_text.splitlines()
    html_lines = []
    for idx, line in enumerate(lines, 1):
        safe_line = html.escape(line)
        html_lines.append(
            f'<div class="code-line">'
            f'<span class="line-num">{idx}</span>'
            f'<span class="line-content">{safe_line or "&nbsp;"}</span>'
            f'</div>'
        )
    return "\n".join(html_lines)


class EvidenceService:
    """Manages the full corpus of documents and attachments for the Evidence Inspector."""

    def __init__(self, data_path: Optional[str] = None):
        self.root_dir = Path(__file__).resolve().parent.parent
        self.dataset_path = Path(data_path) if data_path else self.root_dir / "data" / "final_merged_dataset.json"
        self.attachments_path = self.root_dir / "data" / "attachments" / "attachments.json"
        self.raw_attachments_dir = self.root_dir / "meridian_hackathon_knowledge_base" / "knowledge_attachments"

        self.by_slug: Dict[str, Dict[str, Any]] = {}
        self.by_doc_id: Dict[str, Dict[str, Any]] = {}
        self.by_product: Dict[str, List[Dict[str, Any]]] = {}
        self.all_slugs: Set[str] = set()

        self._load_corpus()

    def _load_corpus(self) -> None:
        """Load and index all documents from dataset."""
        if not self.dataset_path.exists():
            logger.warning(f"Corpus dataset not found at {self.dataset_path}")
            return

        try:
            with open(self.dataset_path, "r", encoding="utf-8") as f:
                records = json.load(f)

            for rec in records:
                meta = rec.get("metadata", {})
                slug = meta.get("slug")
                if not slug:
                    continue

                doc_id = meta.get("doc_id", f"doc-{slug}")
                item = {
                    "raw": rec,
                    "metadata": meta,
                    "slug": slug,
                    "doc_id": doc_id,
                    "product_code": meta.get("product_code") or "P701",
                    "product_name": meta.get("product_name") or "Не указан",
                    "section": meta.get("section") or "Общие сведения",
                    "owner": meta.get("owner") or "Команда разработки",
                    "methodology_version": meta.get("methodology_version", 2),
                    "lifecycle": meta.get("lifecycle", "active"),
                    "quality_tags": meta.get("quality_tags") or [],
                    "updated_at": meta.get("updated_at", "2026-09-01"),
                    "valid_from": meta.get("valid_from", "2026-04-01"),
                    "attachment_path": meta.get("attachment_path"),
                    "attachment_format": meta.get("attachment_format"),
                }

                self.by_slug[slug] = item
                self.by_doc_id[doc_id] = item
                self.all_slugs.add(slug)

                p_code = item["product_code"]
                if p_code not in self.by_product:
                    self.by_product[p_code] = []
                self.by_product[p_code].append(item)

            logger.info(f"EvidenceService loaded {len(self.by_slug)} documents across {len(self.by_product)} products.")

        except Exception as e:
            logger.exception(f"Failed to load corpus dataset: {e}")

    def get_document_raw(self, slug: str) -> Optional[Dict[str, Any]]:
        """Find raw document entry by slug or doc_id."""
        if slug in self.by_slug:
            return self.by_slug[slug]
        if slug in self.by_doc_id:
            return self.by_doc_id[slug]
        
        # Case-insensitive or normalized fallback
        slug_lower = slug.lower().strip()
        for k, v in self.by_slug.items():
            if k.lower() == slug_lower:
                return v
        return None

    def _get_sandbox_evidence(self, slug: str, highlight_term: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Build evidence inspector payload for user uploaded sandbox document."""
        from app.db import chat_history
        source_id = slug.replace("sandbox-", "")
        src = chat_history.get_chat_source(source_id)
        if not src:
            return None

        filename = src["filename"]
        ftype = src["file_type"].lower()
        content = src["text_content"] or ""
        meta = src.get("parsed_meta", {})

        rendered_html = markdown.markdown(
            content,
            extensions=["extra", "tables", "fenced_code", "nl2br"]
        )

        table_data = None
        code_html = None
        if ftype in ["csv", "tsv"] or meta.get("type") == "table":
            if meta.get("headers") and meta.get("rows"):
                table_data = {
                    "type": "table",
                    "headers": meta["headers"],
                    "rows": meta["rows"],
                    "total_rows": meta.get("total_rows", len(meta["rows"])),
                }
            else:
                table_data = parse_table_data(content)
        elif ftype in ["py", "js", "ts", "json", "yaml", "yml", "sql", "html", "css", "xml", "asm", "sh", "bat"] or meta.get("type") == "code":
            code_html = format_code_with_lines(content, lang=ftype)

        attachment_info = {
            "path": src["file_path"],
            "filename": filename,
            "format": ftype.upper(),
            "raw_text": content,
            "table_data": table_data,
            "code_html": code_html,
            "image_url": None,
            "file_exists": True,
        }

        sibling_docs = []
        for s in chat_history.list_chat_sources():
            if s["id"] != src["id"]:
                sibling_docs.append({
                    "slug": f"sandbox-{s['id']}",
                    "section": "Пользовательские файлы",
                    "topic": s["file_type"].upper(),
                    "title": f"📎 {s['filename']}",
                })

        return {
            "slug": slug,
            "title": f"📎 {filename}",
            "product_code": "ФАЙЛ",
            "product_name": "Пользовательский файл",
            "product_color": "#8B5CF6",
            "section": "Пользовательские документы",
            "owner": "Пользователь",
            "lifecycle": "active",
            "quality_tags": ["пользовательский_файл", ftype.upper()],
            "updated_at": src["created_at"][:10],
            "valid_from": src["created_at"][:10],
            "doc_html": rendered_html,
            "doc_raw_markdown": content,
            "attachment": attachment_info,
            "has_attachment": bool(table_data or code_html or ftype in ["pdf", "docx", "csv", "tsv"]),
            "related_documents": sibling_docs,
            "highlight_term": highlight_term or "",
        }

    def _get_code_evidence(self, code_rec: Any, highlight_term: Optional[str] = None) -> Dict[str, Any]:
        """Generate evidence dossier for a code asset (Python, C#, ASM, SQL, etc.)."""
        content = code_rec.content or ""
        ext = code_rec.extension.lower()
        code_html = format_code_with_lines(content, lang=ext)

        md_desc = (
            f"# {code_rec.filename}\n\n"
            f"**Язык программирования**: `{ext.upper()}`  \n"
            f"**Продукт**: {code_rec.product_name} ({code_rec.product_code or 'Общая база'})  \n"
            f"**Категория**: `{code_rec.category}`  \n"
            f"**Путь к файлу**: `{code_rec.rel_path}`  \n\n"
            f"### Назначение\n{code_rec.summary}\n\n"
        )
        if code_rec.symbols:
            md_desc += "### Объявленные функции и структуры данных\n"
            for s in code_rec.symbols:
                md_desc += f"- `{s}`\n"

        rendered_doc = markdown.markdown(md_desc, extensions=["extra", "tables", "fenced_code"])

        sibling_docs = []
        if code_rec.product_code:
            try:
                from app.code_registry import code_registry
                for sib in code_registry.filter_by_product(code_rec.product_code):
                    if sib.filename != code_rec.filename:
                        sibling_docs.append({
                            "slug": sib.filename,
                            "section": f"{sib.extension.upper()} скрипт",
                            "topic": sib.product_name,
                            "title": f"💻 {sib.filename}",
                        })
            except Exception:
                pass

        attachment_info = {
            "path": code_rec.rel_path,
            "filename": code_rec.filename,
            "format": ext.upper(),
            "raw_text": content,
            "table_data": None,
            "code_html": code_html,
            "image_url": None,
            "file_exists": True,
        }

        badge_color = PRODUCT_COLOR_PALETTE.get(code_rec.product_code or "", "#10B981")

        return {
            "slug": code_rec.filename,
            "title": f"💻 {code_rec.filename}",
            "product_code": code_rec.product_code or "CODE",
            "product_name": code_rec.product_name or "Исходный код",
            "product_color": badge_color,
            "section": f"Исходный код ({ext.upper()})",
            "owner": "Инженерная разработка",
            "lifecycle": "active",
            "quality_tags": ["исходный_код", ext.upper(), code_rec.category],
            "updated_at": "2026-09-01",
            "valid_from": "2026-04-01",
            "doc_html": rendered_doc,
            "doc_raw_markdown": md_desc,
            "attachment": attachment_info,
            "has_attachment": True,
            "related_documents": sibling_docs[:8],
            "highlight_term": highlight_term or "",
        }

    def get_evidence(self, slug: str, highlight_term: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve full audit-grade evidence details for a given slug."""
        if slug.startswith("sandbox-"):
            return self._get_sandbox_evidence(slug, highlight_term=highlight_term)

        if slug.startswith("code-catalog-"):
            ext = slug.split("-")[-1]
            if ext == "all":
                ext = None
            try:
                from app.code_registry import code_registry
                matched = code_registry.filter_by_extension(ext) if ext else code_registry.list_all()
                title_ext = ext.upper() if ext else "Кода"
                catalog_md = code_registry.format_catalog_markdown(matched, title=f"Сводный каталог файлов {title_ext}")
                rendered_html = markdown.markdown(catalog_md, extensions=["extra", "tables", "fenced_code"])
                return {
                    "slug": slug,
                    "title": f"📚 Каталог файлов {title_ext}",
                    "product_code": "CATALOG",
                    "product_name": "Каталог Кода",
                    "product_color": "#4B5563",
                    "section": "Сводный реестр",
                    "owner": "Система",
                    "lifecycle": "active",
                    "quality_tags": ["каталог", "автогенерация"],
                    "updated_at": "2026-09-01",
                    "valid_from": "2026-04-01",
                    "doc_html": rendered_html,
                    "doc_raw_markdown": catalog_md,
                    "attachment": None,
                    "has_attachment": False,
                    "related_documents": [],
                    "highlight_term": highlight_term or "",
                }
            except Exception as e:
                logger.error(f"Failed to generate catalog evidence: {e}")
                return None

        try:
            from app.code_registry import code_registry
            code_file = code_registry.get_file(slug)
            if code_file:
                return self._get_code_evidence(code_file, highlight_term=highlight_term)
        except Exception as e:
            logger.debug(f"Code registry lookup failed for {slug}: {e}")

        item = self.get_document_raw(slug)
        if not item:
            return None

        rec = item["raw"]
        meta = item["metadata"]
        page_content = rec.get("page_content", "")

        # Split document text and attachment text
        doc_markdown = page_content
        attachment_text = ""
        if "--- Текст вложения ---" in page_content:
            parts = page_content.split("--- Текст вложения ---", 1)
            doc_markdown = parts[0].strip()
            attachment_text = parts[1].strip()

        # Smart title extraction
        title = ""
        for line in doc_markdown.splitlines():
            line_str = line.strip()
            if line_str.startswith("# "):
                title = line_str[2:].strip()
                break

        if not title and attachment_text and "document_title" in attachment_text:
            try:
                import json
                att_data = json.loads(attachment_text)
                if isinstance(att_data, dict) and att_data.get("document_title"):
                    title = att_data["document_title"]
            except Exception:
                pass

        p_name = item.get("product_name") or ""
        if not title and attachment_text and p_name:
            for line in attachment_text.splitlines()[:25]:
                line_clean = line.strip()
                if line_clean.startswith(f"{p_name}:") or line_clean.startswith(f"{p_name} :"):
                    title = line_clean
                    break

        slug = item.get("slug", "")
        suffix = slug.split("-")[-1]
        topic_map = {
            "access": "Получение доступа",
            "corrections": "Ручные корректировки",
            "events": "Событийная модель и состояния",
            "income": "Учёт и признание выручки",
            "sources": "Источники данных и витрины",
            "freshness": "Свежесть данных и SLA",
            "reconciliation": "Сверка и балансировка",
            "segmentation": "Сегментация и тарифы",
            "tariff": "Тарифная сетка",
            "cancellation": "Отмены и сторнирование",
            "dedup": "Дедупликация и идемпотентность",
            "release": "Релизы и версионирование",
            "archive": "Архивация и хранение данных",
            "reporting": "Отчётность и агрегаты",
            "acceptance": "Приёмка и верификация",
            "examples": "Примеры расчётов",
            "changelog": "Журнал изменений",
            "security": "Безопасность и доступы",
        }
        topic_name = topic_map.get(suffix)

        if not title:
            if topic_name:
                title = f"{p_name}: {topic_name}" if p_name else topic_name
            else:
                for line in doc_markdown.splitlines():
                    line_str = line.strip()
                    if line_str.startswith("## "):
                        title = f"{p_name}: {line_str[3:].strip()}" if p_name else line_str[3:].strip()
                        break

        if not title:
            title = f"{p_name}: {slug}" if p_name else slug

        # Render document markdown to rich HTML
        doc_markdown = convert_csv_tables_to_markdown(doc_markdown)
        rendered_doc_html = markdown.markdown(
            doc_markdown,
            extensions=["extra", "tables", "fenced_code", "nl2br"]
        )
        rendered_doc_html = self.transform_wiki_links(rendered_doc_html)

        # Process attachment
        attachment_info = None
        att_path = meta.get("attachment_path")
        att_format = (meta.get("attachment_format") or "").lower().lstrip(".")

        if att_path or attachment_text:
            rel_file_path = att_path.replace("knowledge_attachments/", "") if att_path else ""
            
            # Check if physical file exists for direct viewing
            file_exists_on_disk = False
            image_url = None
            if rel_file_path:
                disk_path = self.raw_attachments_dir / rel_file_path
                if disk_path.exists():
                    file_exists_on_disk = True
                    if att_format in ["png", "jpg", "jpeg", "webp", "gif"]:
                        norm_rel = rel_file_path.replace('\\', '/')
                        image_url = f"/attachments/{norm_rel}"

            # Check for tabular data (CSV / TSV)
            table_data = None
            if att_format in ["csv", "tsv"] or "|" in attachment_text or ";" in attachment_text:
                table_data = parse_table_data(attachment_text)

            # Check for code (ASM, Python, C#, JSON)
            code_html = None
            if att_format in ["asm", "py", "cs", "json", "c", "cpp"]:
                code_html = format_code_with_lines(attachment_text, lang=att_format)

            attachment_info = {
                "path": att_path or f"attachment.{att_format}",
                "filename": Path(att_path).name if att_path else f"attachment.{att_format}",
                "format": att_format.upper() if att_format else "FILE",
                "raw_text": attachment_text,
                "table_data": table_data,
                "code_html": code_html,
                "image_url": image_url,
                "file_exists": file_exists_on_disk,
            }

        # Related documents in the same product with topic metadata
        p_code = item["product_code"]
        sibling_docs = []
        for d in self.by_product.get(p_code, []):
            if d["slug"] != item["slug"]:
                sib_suffix = d["slug"].split("-")[-1]
                sib_topic = topic_map.get(sib_suffix, "")
                sibling_docs.append({
                    "slug": d["slug"],
                    "section": d["section"],
                    "topic": sib_topic,
                    "title": f"{p_name}: {sib_topic}" if sib_topic else d["slug"]
                })
        sibling_docs = sibling_docs[:7]

        product_color = PRODUCT_COLOR_PALETTE.get(p_code, DEFAULT_PRODUCT_COLOR)

        return {
            "slug": item["slug"],
            "doc_id": item["doc_id"],
            "title": title,
            "topic": topic_name or suffix,
            "product_code": p_code,
            "product_name": item["product_name"],
            "product_color": product_color,
            "section": item["section"],
            "owner": item["owner"],
            "methodology_version": item["methodology_version"],
            "lifecycle": item["lifecycle"],
            "quality_tags": item["quality_tags"],
            "updated_at": item["updated_at"],
            "valid_from": item["valid_from"],
            "doc_html": rendered_doc_html,
            "doc_raw_markdown": doc_markdown,
            "attachment": attachment_info,
            "has_attachment": attachment_info is not None and bool(attachment_text or (attachment_info and attachment_info.get("image_url"))),
            "related_documents": sibling_docs,
            "highlight_term": highlight_term or "",
        }

    def transform_wiki_links(self, html_content: str) -> str:
        """
        Convert synthetic corporate wiki URLs (https://kb.arcadia.example/pages/<slug>)
        into interactive in-drawer cross-references or graceful informational indicators.
        Also secures any other external links so they don't break application context.
        """
        if not html_content:
            return ""

        def _replace_kb_link(match: re.Match) -> str:
            slug = match.group(1).strip()
            link_text = match.group(2).strip()

            target = self.get_document_raw(slug)
            if target:
                p_name = target["metadata"].get("product_name") or target.get("product_name", "")
                title_tip = f"Открыть регламент: {p_name} ({slug})"
                return (
                    f'<a href="javascript:void(0)" onclick="openEvidenceInspector(\'{slug}\')" '
                    f'title="{title_tip}">{link_text}</a>'
                )
            else:
                return (
                    f'<a href="javascript:void(0)" onclick="handleMissingEvidenceLink(\'{slug}\')" '
                    f'title="Внутренний регламент (отдельный файл отсутствует в выгрузке)">{link_text}</a>'
                )

        # 1. Intercept any links pointing to kb.arcadia.example/pages/<slug>
        pattern = re.compile(
            r'<a\s+[^>]*href="https?://kb\.arcadia\.example/pages/([a-zA-Z0-9_\-]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE
        )
        transformed = pattern.sub(_replace_kb_link, html_content)

        # 2. Also safeguard any remaining external links: ensure target="_blank" and rel
        def _safe_external_link(match: re.Match) -> str:
            full_tag = match.group(0)
            if 'target=' not in full_tag and 'javascript:void' not in full_tag:
                return full_tag[:-1] + ' target="_blank" rel="noopener noreferrer">'
            return full_tag

        transformed = re.sub(r'<a\s+href="https?://[^"]+"[^>]*>', _safe_external_link, transformed)
        return transformed

    def enhance_citations(self, html_content: str, active_citations: Optional[List[str]] = None) -> str:
        """
        Enhance [slug] citations in generated answers into interactive Evidence Inspector chips.
        Also turns internal KB links into inspector triggers.
        """
        if not html_content:
            return ""

        active_set = set(active_citations or [])

        # 1. Replace [slug] with interactive evidence badges
        def replace_slug_cite(match: re.Match) -> str:
            raw_slug = match.group(1).strip()
            if raw_slug.startswith("sandbox-"):
                sid = raw_slug.replace("sandbox-", "")
                from app.db import chat_history
                src = chat_history.get_chat_source(sid)
                label = src["filename"] if src else raw_slug
                safe_label = html.escape(label)
                safe_slug = html.escape(raw_slug)
                return (
                    f'<button type="button" class="evidence-pill" '
                    f'onclick="openEvidenceInspector(\'{safe_slug}\')" '
                    f'data-slug="{safe_slug}" '
                    f'title="Открыть документ [{safe_label}] в Evidence Inspector">'
                    f'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
                    f'<path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48"></path>'
                    f'</svg>'
                    f'<span class="pill-slug">📎 {safe_label}</span>'
                    f'<span class="pill-dot" style="background-color: #8B5CF6;"></span>'
                    f'</button>'
                )

            # Check code registry for Python, C#, ASM, SQL scripts
            try:
                from app.code_registry import code_registry
                code_file = code_registry.get_file(raw_slug)
                if code_file:
                    safe_slug = html.escape(code_file.filename)
                    safe_label = html.escape(code_file.filename)
                    badge_color = PRODUCT_COLOR_PALETTE.get(code_file.product_code or "", "#10B981")
                    return (
                        f'<button type="button" class="evidence-pill code-pill" '
                        f'onclick="openEvidenceInspector(\'{safe_slug}\')" '
                        f'data-slug="{safe_slug}" '
                        f'title="Открыть исходный код [{safe_label}] в Evidence Inspector">'
                        f'<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">'
                        f'<polyline points="16 18 22 12 16 6"></polyline>'
                        f'<polyline points="8 6 2 12 8 18"></polyline>'
                        f'</svg>'
                        f'<span class="pill-slug">💻 {safe_label}</span>'
                        f'<span class="pill-dot" style="background-color: {badge_color};"></span>'
                        f'</button>'
                    )
            except Exception:
                pass

            # Verify if this is a known slug in our corpus or active citations
            is_valid = raw_slug in self.all_slugs or raw_slug in active_set
            if not is_valid:
                # Check fuzzy matching
                if not any(prefix in raw_slug for prefix in ["iskra", "rosinka", "yantar", "mostik", "tihaya", "lavka", "kometa", "prizma", "orbitarium", "parus", "bastion", "ritm", "zontik", "sozvezdie", "mozaika", "mahovik", "pergament", "oblachny", "p70", "p71", "passport", "guide", "spec", "events"]):
                    return match.group(0)

            index = -1
            if active_citations and raw_slug in active_citations:
                index = active_citations.index(raw_slug) + 1
            else:
                return match.group(0)

            safe_slug = html.escape(raw_slug)
            
            return (
                f'<a href="#source-{index}" class="citation-link" '
                f'onclick="openEvidenceInspector(\'{safe_slug}\')" '
                f'title="Источник: {safe_slug}" style="text-decoration: none; color: #3b82f6; font-weight: 500;">[{index}]</a>'
            )

        # Regex for [slug] patterns
        enhanced = re.sub(r"\[([a-zA-Z0-9_\-\.]+)\]", replace_slug_cite, html_content)

        # 2. Intercept wiki links and safeguard external URLs
        enhanced = self.transform_wiki_links(enhanced)

        # 3. Collapse adjacent citation links like [1][2][3][4][5] into concise ranges like [1–5] or [1, 2]
        def collapse_adjacent_citations(m: re.Match) -> str:
            raw_group = m.group(0)
            # Find all (index, slug) pairs
            items = re.findall(r'href="#source-(\d+)"[^>]*onclick="openEvidenceInspector\(\'([^\']+)\'\)"[^>]*>\[\d+\]</a>', raw_group)
            if not items:
                return raw_group
            
            unique_items = []
            seen = set()
            for idx_str, slug in items:
                idx = int(idx_str)
                if idx not in seen:
                    seen.add(idx)
                    unique_items.append((idx, slug))
            
            if len(unique_items) == 1:
                idx, slug = unique_items[0]
                return (
                    f'<a href="#source-{idx}" class="citation-link" '
                    f'onclick="openEvidenceInspector(\'{slug}\')" '
                    f'title="Источник: {slug}" style="text-decoration: none; color: #3b82f6; font-weight: 500;">[{idx}]</a>'
                )
            
            sorted_indices = sorted([u[0] for u in unique_items])
            min_idx, max_idx = sorted_indices[0], sorted_indices[-1]
            first_slug = unique_items[0][1]
            all_slugs_str = ", ".join([u[1] for u in unique_items])
            
            if len(sorted_indices) >= 3 and sorted_indices == list(range(min_idx, max_idx + 1)):
                label = f"[{min_idx}–{max_idx}]"
            else:
                label = f"[{', '.join(str(i) for i in sorted_indices)}]"
            
            return (
                f'<a href="#source-{min_idx}" class="citation-link" '
                f'onclick="openEvidenceInspector(\'{first_slug}\')" '
                f'title="Источники: {all_slugs_str}" style="text-decoration: none; color: #3b82f6; font-weight: 500;">{label}</a>'
            )

        # Match 2 or more adjacent citation links (allowing whitespace/newlines/commas between them)
        cite_link_pattern = r'(?:<a href="#source-\d+" class="citation-link"[^>]*>\[\d+\]</a>[\s,]*){2,}'
        enhanced = re.sub(cite_link_pattern, collapse_adjacent_citations, enhanced)

        return enhanced


# Global singleton instance
evidence_service = EvidenceService()
