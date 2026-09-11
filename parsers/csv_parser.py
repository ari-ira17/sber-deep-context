from pathlib import Path
import pandas as pd


def _escape(value: str) -> str:
    return str(value).replace("\n", " ").replace("|", r"\|").strip()


def _to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return ""
    df = df.copy().fillna("")
    df.columns = [str(c) for c in df.columns]
    try:
        return df.to_markdown(index=False)
    except (ImportError, ValueError):
        headers = [_escape(c) for c in df.columns]
        out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
        for row in df.astype(str).itertuples(index=False, name=None):
            out.append("| " + " | ".join(_escape(v) for v in row) + " |")
        return "\n".join(out)


def parse_csv(path: str | Path) -> str:
    path = Path(path)
    last_error = None
    for kwargs in ({"sep": None, "engine": "python"}, {"sep": ";", "engine": "python"}):
        try:
            df = pd.read_csv(path, encoding="utf-8-sig", on_bad_lines="warn", **kwargs)
            return _to_markdown(df)
        except Exception as exc:
            last_error = exc
    raise RuntimeError(f"CSV parsing failed: {last_error}")
