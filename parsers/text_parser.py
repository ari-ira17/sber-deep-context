from pathlib import Path

SUPPORTED_TEXT_EXTENSIONS = {".md", ".txt", ".py", ".asm", ".cs"}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [line.rstrip() for line in text.split("\n")]
    result, empty = [], 0
    for line in lines:
        if not line.strip():
            empty += 1
            if empty <= 2:
                result.append("")
        else:
            empty = 0
            result.append(line)
    return "\n".join(result).strip()


def parse_text(path: str | Path) -> str:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    return normalize_text(text)
