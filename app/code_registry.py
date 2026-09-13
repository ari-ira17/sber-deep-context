"""Code Registry for Meridian Knowledge Base.

Provides structured indexing, metadata extraction, and multi-faceted search
(by extension, product, symbol, or text) for code files:
- Python (.py)
- C# (.cs)
- Assembler (.asm)
- SQL / Shell scripts (.sql, .sh)
"""

import os
import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

PRODUCT_NAMES_MAP = {
    "P701": "Искра",
    "P702": "Росинка",
    "P703": "Янтарь",
    "P704": "Мостик",
    "P705": "Тихая Гавань",
    "P706": "Лавка",
    "P707": "Комета",
    "P708": "Призма",
    "P709": "Орбитариум",
    "P710": "Парус",
    "P711": "Бастион",
    "P712": "Ритм",
    "P713": "Зонтик",
    "P714": "Созвездие",
    "P715": "Мозаика",
    "P716": "Маховик",
    "P717": "Пергамент",
    "P718": "Облачный Сад",
    "GENERAL": "Общая база",
}

SUPPORTED_CODE_EXTENSIONS = {"py", "cs", "asm", "sql", "sh"}


@dataclass
class CodeFileRecord:
    filename: str
    slug: str
    extension: str
    product_code: Optional[str]
    product_name: Optional[str]
    category: str
    rel_path: str
    abs_path: Optional[str]
    summary: str
    symbols: List[str] = field(default_factory=list)
    content: str = ""
    line_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "filename": self.filename,
            "slug": self.slug,
            "extension": self.extension,
            "product_code": self.product_code,
            "product_name": self.product_name,
            "category": self.category,
            "rel_path": self.rel_path,
            "summary": self.summary,
            "symbols": self.symbols,
            "line_count": self.line_count,
        }


class CodeRegistry:
    """Singleton registry indexing all code assets across the Meridian knowledge base."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent.parent
        self.files: Dict[str, CodeFileRecord] = {}
        self._by_extension: Dict[str, List[str]] = {}
        self._by_product: Dict[str, List[str]] = {}
        self._load_registry()

    def _load_registry(self):
        """Load code records from filesystem and parsed attachments."""
        
        att_file = self.base_dir / "data" / "attachments" / "attachments.json"
        parsed_texts: Dict[str, str] = {}
        if att_file.exists():
            try:
                with open(att_file, "r", encoding="utf-8") as f:
                    att_data = json.load(f)
                for item in att_data.get("attachments", []):
                    path_str = item.get("attachment_path")
                    text_str = item.get("text", "")
                    if path_str and text_str:
                        norm_p = path_str.replace("\\", "/").strip("/")
                        parsed_texts[norm_p] = text_str
            except Exception as e:
                logger.warning(f"Error loading attachments.json: {e}")

        
        mapping_file = self.base_dir / "data" / "attachments" / "attachment_mapping.json"
        doc_mappings: Dict[str, Dict[str, Any]] = {}
        if mapping_file.exists():
            try:
                with open(mapping_file, "r", encoding="utf-8") as f:
                    doc_mappings = json.load(f)
            except Exception as e:
                logger.warning(f"Error loading attachment_mapping.json: {e}")

        
        
        search_roots = [
            self.base_dir / "meridian_hackathon_knowledge_base" / "knowledge_attachments",
            self.base_dir / "knowledge_attachments",
        ]

        found_disk_paths: Set[str] = set()
        for root in search_roots:
            if not root.exists():
                continue
            for p in root.rglob("*"):
                if p.is_file() and p.suffix:
                    ext = p.suffix.lstrip(".").lower()
                    if ext in SUPPORTED_CODE_EXTENSIONS:
                        rel = str(p.relative_to(root)).replace("\\", "/")
                        full_rel = f"knowledge_attachments/{rel}"
                        found_disk_paths.add(full_rel)
                        try:
                            content = p.read_text(encoding="utf-8", errors="replace")
                        except Exception:
                            content = parsed_texts.get(full_rel, "")
                        self._register_file(
                            filename=p.name,
                            rel_path=full_rel,
                            extension=ext,
                            content=content,
                            abs_path=str(p),
                            mapping_meta=doc_mappings.get(full_rel),
                        )

        
        for full_rel, content in parsed_texts.items():
            if full_rel in found_disk_paths:
                continue
            fname = Path(full_rel).name
            ext = Path(full_rel).suffix.lstrip(".").lower()
            if ext in SUPPORTED_CODE_EXTENSIONS:
                self._register_file(
                    filename=fname,
                    rel_path=full_rel,
                    extension=ext,
                    content=content,
                    abs_path=None,
                    mapping_meta=doc_mappings.get(full_rel),
                )

        logger.info(f"CodeRegistry loaded {len(self.files)} code files (Python, C#, ASM, SQL).")

    def _extract_summary(self, content: str, ext: str) -> str:
        """Extract leading docstring or comment block explaining file purpose."""
        if not content:
            return "Файл исходного кода."

        lines = content.strip().splitlines()
        comments: List[str] = []

        if ext == "py":
            doc_match = re.search(r'^[ \t]*(?:"""|\'\'\')(.*?)(?:"""|\'\'\')', content, re.DOTALL)
            if doc_match:
                doc = doc_match.group(1).strip()
                return doc.replace("\n", " ")[:250]
            for l in lines[:10]:
                l_str = l.strip()
                if l_str.startswith("#"):
                    comments.append(l_str.lstrip("#").strip())
                elif comments:
                    break

        elif ext in ("cs", "c", "cpp"):
            in_block = False
            for l in lines[:15]:
                l_str = l.strip()
                if l_str.startswith("/*"):
                    in_block = True
                    cleaned = l_str.lstrip("/*").strip()
                    if cleaned:
                        comments.append(cleaned)
                elif in_block:
                    if "*/" in l_str:
                        cleaned = l_str.split("*/")[0].strip().lstrip("*").strip()
                        if cleaned:
                            comments.append(cleaned)
                        break
                    comments.append(l_str.lstrip("*").strip())
                elif l_str.startswith("//"):
                    comments.append(l_str.lstrip("/").strip())
                elif comments:
                    break

        elif ext == "asm":
            for l in lines[:15]:
                l_str = l.strip()
                if l_str.startswith(";"):
                    comments.append(l_str.lstrip(";").strip())
                elif comments:
                    break

        elif ext == "sql":
            for l in lines[:15]:
                l_str = l.strip()
                if l_str.startswith("--"):
                    comments.append(l_str.lstrip("-").strip())
                elif comments:
                    break

        if comments:
            return " ".join(c for c in comments if c)[:250]

        for l in lines[:5]:
            if l.strip():
                return l.strip()[:150]

        return f"Исходный код на языке {ext.upper()}."

    def _extract_symbols(self, content: str, ext: str) -> List[str]:
        """Extract declared functions, classes, and exported routines."""
        symbols: Set[str] = set()
        if not content:
            return []

        if ext == "py":
            for m in re.finditer(r"^[ \t]*(?:def|class)\s+([a-zA-Z0-9_]+)", content, re.MULTILINE):
                symbols.add(m.group(1))

        elif ext == "cs":
            for m in re.finditer(r"\b(?:class|struct|interface|enum)\s+([a-zA-Z0-9_]+)", content):
                symbols.add(m.group(1))
            for m in re.finditer(r"\b(?:public|private|protected|internal|static|async)\s+[a-zA-Z0-9_<>\[\]]+\s+([a-zA-Z0-9_]+)\s*\(", content):
                name = m.group(1)
                if name not in ("if", "while", "for", "switch", "using"):
                    symbols.add(name)

        elif ext == "asm":
            for m in re.finditer(r"global\s+([a-zA-Z0-9_]+)", content):
                symbols.add(m.group(1))
            for m in re.finditer(r"^[ \t]*([a-zA-Z0-9_]+):", content, re.MULTILINE):
                symbols.add(m.group(1))

        elif ext == "sql":
            for m in re.finditer(r"(?:CREATE\s+TABLE|CREATE\s+VIEW)\s+([a-zA-Z0-9_]+)", content, re.IGNORECASE):
                symbols.add(m.group(1))

        return sorted(list(symbols))[:15]

    def _register_file(
        self,
        filename: str,
        rel_path: str,
        extension: str,
        content: str,
        abs_path: Optional[str] = None,
        mapping_meta: Optional[Dict[str, Any]] = None,
    ):
        """Process and register a code file record."""
        product_code = None
        product_name = None
        category = "technical"

        if mapping_meta:
            product_code = mapping_meta.get("product_code")
            product_name = mapping_meta.get("product_name")

        parts = rel_path.split("/")
        for p in parts:
            p_upper = p.upper()
            if p_upper.startswith("P7") and len(p_upper) == 4 and p_upper in PRODUCT_NAMES_MAP:
                product_code = p_upper
                product_name = PRODUCT_NAMES_MAP.get(p_upper)
            if p.lower() in ("technical", "business", "visuals", "general"):
                category = p.lower()

        slug = Path(filename).stem
        summary = self._extract_summary(content, extension)
        symbols = self._extract_symbols(content, extension)
        lines = content.splitlines()

        rec = CodeFileRecord(
            filename=filename,
            slug=slug,
            extension=extension,
            product_code=product_code,
            product_name=product_name or (PRODUCT_NAMES_MAP.get(product_code) if product_code else "Общая база"),
            category=category,
            rel_path=rel_path,
            abs_path=abs_path,
            summary=summary,
            symbols=symbols,
            content=content,
            line_count=len(lines),
        )

        key = filename.lower()
        self.files[key] = rec
        self.files[slug.lower()] = rec

        self._by_extension.setdefault(extension.lower(), []).append(key)
        if product_code:
            self._by_product.setdefault(product_code.upper(), []).append(key)

    def list_all(self) -> List[CodeFileRecord]:
        """Return unique list of all indexed code files."""
        unique_recs = {r.filename: r for r in self.files.values()}
        return sorted(list(unique_recs.values()), key=lambda r: (r.product_code or "", r.filename))

    def filter_by_extension(self, ext: str, product_code: Optional[str] = None) -> List[CodeFileRecord]:
        """Filter files by extension (e.g. 'py', 'cs', 'asm') and optional product code."""
        clean_ext = ext.lower().lstrip(".")
        keys = self._by_extension.get(clean_ext, [])
        recs = [self.files[k] for k in set(keys)]
        if product_code:
            target_p = product_code.upper()
            recs = [r for r in recs if r.product_code and r.product_code.upper() == target_p]
        return sorted(recs, key=lambda r: (r.product_code or "", r.filename))

    def filter_by_product(self, product_code: str) -> List[CodeFileRecord]:
        """Filter files by product code (e.g. 'P701')."""
        target_p = product_code.upper()
        keys = self._by_product.get(target_p, [])
        recs = [self.files[k] for k in set(keys)]
        return sorted(recs, key=lambda r: (r.extension, r.filename))

    def get_file(self, identifier: str) -> Optional[CodeFileRecord]:
        """Lookup by filename, slug, or relative path."""
        if not identifier:
            return None
        clean_id = identifier.lower().strip()
        if clean_id in self.files:
            return self.files[clean_id]
        clean_stem = Path(clean_id).stem
        if clean_stem in self.files:
            return self.files[clean_stem]
        fname = Path(clean_id).name
        if fname in self.files:
            return self.files[fname]
        return None

    def search(
        self,
        query: str,
        product_code: Optional[str] = None,
        extension: Optional[str] = None,
        top_k: int = 5,
    ) -> List[CodeFileRecord]:
        """Semantic/lexical search matching symbols, filename, and code content."""
        clean_q = query.lower().strip()
        candidates = self.list_all()

        if product_code:
            candidates = [c for c in candidates if c.product_code and c.product_code.upper() == product_code.upper()]
        if extension:
            candidates = [c for c in candidates if c.extension == extension.lower()]

        scored: List[tuple[float, CodeFileRecord]] = []
        tokens = [t for t in re.findall(r"[a-zA-Z0-9_\-]+", clean_q) if len(t) >= 2]

        for rec in candidates:
            score = 0.0
            if clean_q in rec.filename.lower() or clean_q in rec.slug.lower():
                score += 20.0
            for t in tokens:
                if t in rec.filename.lower():
                    score += 8.0

            for sym in rec.symbols:
                sym_lower = sym.lower()
                if clean_q == sym_lower:
                    score += 25.0
                elif clean_q in sym_lower:
                    score += 12.0
                for t in tokens:
                    if t == sym_lower:
                        score += 10.0
                    elif t in sym_lower:
                        score += 4.0

            for t in tokens:
                if t in rec.summary.lower():
                    score += 3.0

            content_lower = rec.content.lower()
            for t in tokens:
                if t in content_lower:
                    score += 1.0

            if score > 0:
                scored.append((score, rec))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def format_catalog_markdown(self, records: List[CodeFileRecord], title: Optional[str] = None) -> str:
        """Format a clean markdown table of files with purposes and symbols."""
        if not records:
            return "Файлы кода по заданным критериям не найдены."

        header = title or f"Каталог исходного кода ({len(records)} файлов)"
        lines = [
            f"# {header}",
            "",
            "| Файл | Язык | Продукт | Назначение / Ключевые функции |",
            "|:---|:---:|:---:|:---|",
        ]

        for r in records:
            p_label = f"{r.product_name} ({r.product_code})" if r.product_code else "Общая база"
            ext_label = r.extension.upper()
            syms_str = f" `[{', '.join(r.symbols[:3])}]`" if r.symbols else ""
            desc = r.summary.replace("\n", " ").strip()
            if len(desc) > 130:
                desc = desc[:127] + "..."
            lines.append(f"| `[{r.filename}]` | **{ext_label}** | {p_label} | {desc}{syms_str} |")

        lines.append("")
        lines.append("> *Примечание: Нажмите на название любого файла в ответе, чтобы открыть его исходный код с номерами строк в Evidence Inspector.*")
        return "\n".join(lines)



code_registry = CodeRegistry()
