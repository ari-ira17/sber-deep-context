from __future__ import annotations
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parsers.text_parser import parse_text
from parsers.csv_parser import parse_csv
from parsers.json_parser import parse_json
from parsers.docx_parser import parse_docx
from parsers.pdf_parser import parse_pdf
from parsers.png_parser import parse_png

PARSER_VERSION = "1.0.0"
PARSERS = {
    ".md": ("text", parse_text), ".txt": ("text", parse_text),
    ".py": ("text", parse_text), ".asm": ("text", parse_text),
    ".cs": ("text", parse_text), ".csv": ("csv", parse_csv),
    ".json": ("json", parse_json), ".docx": ("docx", parse_docx),
    ".pdf": ("pdf", parse_pdf), ".png": ("png_ocr", parse_png),
}
IGNORED_FILENAMES = {"README.md"}


def norm(path: str | Path) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def load_mapping(path: Path | None) -> dict:
    if path is None:
        return {}
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, dict) and "attachments" in data:
        return {norm(x["attachment_path"]): x for x in data["attachments"] if x.get("attachment_path")}
    if not isinstance(data, dict):
        raise ValueError("Mapping JSON must be an object")
    return {norm(k): ({"doc_id": v} if isinstance(v, str) else v) for k, v in data.items()}


def discover(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file() and p.name not in IGNORED_FILENAMES)


def parse_one(path: Path, root: Path, mapping: dict) -> dict:
    rel = norm(path.relative_to(root))
    attachment_path = norm(Path(root.name) / path.relative_to(root))
    meta = mapping.get(attachment_path) or mapping.get(rel) or {}
    suffix = path.suffix.lower()
    record = {
        "doc_id": meta.get("doc_id"),
        "attachment_path": attachment_path,
        "attachment_format": suffix.lstrip("."),
        "attachment_label": meta.get("attachment_label"),
        "product_code": meta.get("product_code"),
        "product_name": meta.get("product_name"),
        "parser": None,
        "parser_version": PARSER_VERSION,
        "status": None,
        "confidence": None,
        "ocr_used": False,
        "text_length": 0,
        "text": "",
        "error": None,
    }
    if suffix not in PARSERS:
        record.update(status="unsupported", error=f"Unsupported extension: {suffix}")
        return record
    parser_name, parser = PARSERS[suffix]
    record["parser"] = parser_name
    try:
        result = parser(path)
        if isinstance(result, dict):
            text = str(result.get("text", "") or "").strip()
            record["ocr_used"] = bool(result.get("ocr_used", False))
            record["confidence"] = result.get("confidence")
        else:
            text = str(result or "").strip()
        record["text"] = text
        record["text_length"] = len(text)
        record["status"] = "success"
        if record["confidence"] is None:
            record["confidence"] = "normal" if len(text) >= 50 else "LOW_CONFIDENCE"
    except Exception as exc:
        record.update(status="error", confidence="LOW_CONFIDENCE", error=f"{type(exc).__name__}: {exc}")
    return record


def main() -> int:
    ap = argparse.ArgumentParser(description="Parse all Meridian knowledge-base attachments")
    ap.add_argument("--input", type=Path, default=ROOT / "knowledge_attachments")
    ap.add_argument("--output", type=Path, default=ROOT / "data/attachments/attachments.json")
    ap.add_argument("--mapping", type=Path, default=None)
    args = ap.parse_args()
    if not args.input.exists():
        print(f"ERROR: input directory does not exist: {args.input}")
        return 1
    mapping = load_mapping(args.mapping)
    files = discover(args.input)
    print(f"Parsing {len(files)} files from {args.input}")
    started = time.time()
    results = []
    statuses, formats, confidences = Counter(), Counter(), Counter()
    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {norm(path.relative_to(args.input))}")
        result = parse_one(path, args.input, mapping)
        results.append(result)
        statuses[result["status"]] += 1
        formats[result["attachment_format"]] += 1
        if result["confidence"]:
            confidences[result["confidence"]] += 1
        if result["status"] == "error":
            print(f"  ERROR: {result['error']}")
    elapsed = time.time() - started
    payload = {
        "schema_version": "1.0",
        "parser_version": PARSER_VERSION,
        "source": {"directory": norm(args.input), "ignored_filenames": sorted(IGNORED_FILENAMES)},
        "statistics": {
            "files_processed": len(results), "success": statuses["success"],
            "errors": statuses["error"], "unsupported": statuses["unsupported"],
            "low_confidence": confidences["LOW_CONFIDENCE"], "elapsed_seconds": round(elapsed, 3),
            "formats": dict(sorted(formats.items())),
        },
        "attachments": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n=== COMPLETED ===")
    print(f"Processed: {len(results)} | success: {statuses['success']} | errors: {statuses['error']} | unsupported: {statuses['unsupported']}")
    print(f"LOW_CONFIDENCE: {confidences['LOW_CONFIDENCE']} | time: {elapsed:.2f}s")
    print(f"Output: {args.output}")
    return 0 if statuses["error"] == 0 and statuses["unsupported"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
