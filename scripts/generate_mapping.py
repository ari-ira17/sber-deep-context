import os
import json
from parse_sql import parse_sql_dump
from extract_metadata import flatten_metadata

def generate_attachment_mapping(documents: list, output_path: str) -> dict:
    """
    Проходит по документам и собирает словарь связей между путями файлов и doc_id.
    """
    mapping = {}
    for doc in documents:
        
        att_path = doc.get("attachment_path")
        if att_path:
            mapping[att_path] = {
                "doc_id": doc.get("doc_id"),
                
                "attachment_label": doc.get("attachment_label", doc.get("title")),
                "product_code": doc.get("product_code"),
                "product_name": doc.get("product_name"),
                "product_name": doc.get("product_name")
            }
    
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(mapping, f, ensure_ascii=False, indent=2)
        
    return mapping

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    
    sql_file = os.path.normpath(
        os.path.join(script_dir, "..", "meridian_hackathon_knowledge_base", "meridian_hackathon_knowledge_base", "ai_copilot_documents.sql")
    )
    
    
    output_file = os.path.normpath(
        os.path.join(script_dir, "..", "data", "attachments", "attachment_mapping.json")
    )
    
    print("1. Читаем SQL-дамп...")
    raw_docs = list(parse_sql_dump(sql_file))
    
    print("2. Распаковываем метаданные...")
    flat_docs = flatten_metadata(raw_docs)
    
    print("3. Генерируем маппинг вложений...")
    mapping = generate_attachment_mapping(flat_docs, output_file)
    
    print(f"Готово! Найдено {len(mapping)} документов с вложениями.")
    print(f"Файл сохранен по пути: {output_file}")