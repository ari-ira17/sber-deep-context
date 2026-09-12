from pathlib import Path
import json


def parse_json(path: str | Path) -> str:
    path = Path(path)
    try:
        with path.open("r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON: {exc}") from exc
    return json.dumps(data, ensure_ascii=False, indent=2).strip()
