import os
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
try:
    from mcp.server.fastmcp import FastMCP as Server
    mcp = Server("File Exporter Server")
except ImportError:
    # Dummy mock if mcp is not installed
    class DummyServer:
        def tool(self):
            def decorator(func):
                return func
            return decorator
        def run(self):
            print("MCP is not installed. Run with Python >=3.10 and 'pip install mcp'")
    mcp = DummyServer()

BASE_EXPORT_DIR = Path.cwd() / "exported_docs"

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r'\s+', "_", cleaned).strip()
    return cleaned or "document"

def clean_xml_chars(text: str) -> str:
    """Удаляет невидимые управляющие символы, ломающие структуру .docx"""
    if not text:
        return text
    # Оставляем только валидные для XML символы (разрешаем \n, \r, \t)
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', text)

@mcp.tool()
def export_to_file(
    title: str,
    content: str,
    format_type: str = "md",
    subfolder: str = ""
) -> str:
    try:
        # Очищаем входные данные от символов, ломающих Word
        content = clean_xml_chars(content)
        title = clean_xml_chars(title)
        
        target_dir = BASE_EXPORT_DIR
        if subfolder:
            safe_subfolder = sanitize_filename(subfolder)
            target_dir = target_dir / safe_subfolder
        
        target_dir.mkdir(parents=True, exist_ok=True)
        
        safe_title = sanitize_filename(title)
        ext = format_type.lower().strip(".")
        if ext not in ["md", "docx"]:
            ext = "md"
            
        file_path = target_dir / f"{safe_title}.{ext}"
        
        if ext == "md":
            file_content = content
            file_path.write_text(file_content, encoding="utf-8")
            
        elif ext == "docx":
            doc = Document()
            
            # Глобальный стиль Normal настраивать безопасно (делается один раз)
            style_normal = doc.styles['Normal']
            style_normal.font.name = 'Times New Roman'
            style_normal.font.size = Pt(14)
            
            lines = content.split("\n")
            table_rows = []
            
            def flush_table():
                if not table_rows:
                    return
                filtered_rows = [r for r in table_rows if not all(c.strip("-") == "" for c in r)]
                if filtered_rows:
                    cols_count = len(filtered_rows[0])
                    # Защита от пустых таблиц
                    if cols_count > 0:
                        table = doc.add_table(rows=len(filtered_rows), cols=cols_count)
                        table.style = 'Table Grid'
                        for r_idx, row_data in enumerate(filtered_rows):
                            for c_idx, cell_value in enumerate(row_data):
                                if c_idx < cols_count:
                                    cell = table.cell(r_idx, c_idx)
                                    cell.text = cell_value.strip()
                                    for p in cell.paragraphs:
                                        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                                        for r in p.runs:
                                            r.font.name = 'Times New Roman'
                                            r.font.size = Pt(12)
                table_rows.clear()
                doc.add_paragraph()

            for line in lines:
                stripped = line.strip()
                
                if stripped.startswith("|") and stripped.endswith("|"):
                    cells = [c.strip() for c in stripped.strip("|").split("|")]
                    table_rows.append(cells)
                    continue
                else:
                    flush_table()
                
                # Безопасное добавление заголовков через run
                if stripped.startswith("## "):
                    h = doc.add_heading(level=2)
                    run = h.add_run(stripped[3:])
                    run.font.name = 'Times New Roman'
                elif stripped.startswith("### "):
                    h = doc.add_heading(level=3)
                    run = h.add_run(stripped[4:])
                    run.font.name = 'Times New Roman'
                elif stripped.startswith("- ") or stripped.startswith("* "):
                    p = doc.add_paragraph(stripped[2:], style='List Bullet')
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                elif stripped:
                    p = doc.add_paragraph(stripped)
                    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                else:
                    doc.add_paragraph()
            
            flush_table()
            doc.save(str(file_path))
            
        return f"Файл успешно создан.\nАбсолютный путь: {file_path.resolve()}"
        
    except Exception as e:
        return f"Произошла ошибка при создании файла: {str(e)}"

if __name__ == "__main__":
    mcp.run()