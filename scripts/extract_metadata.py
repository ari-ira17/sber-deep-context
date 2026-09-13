import json
import logging
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def flatten_metadata(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Распаковывает целевые поля из JSON-строки или словаря metadata 
    в корень каждого документа и удаляет исходное поле metadata[cite: 1].
    """
    target_fields = [
        'product_code', 'product_name', 'section', 'owner', 
        'methodology_version', 'lifecycle', 'quality_tags', 'slug', 
        'updated_at', 'valid_from', 'synthetic', 'attachment_path', 
        'attachment_format', 'child_slugs'
    ]

    for doc in documents:
        metadata_raw = doc.get('metadata')
        metadata_obj = {}

        
        if isinstance(metadata_raw, str):
            try:
                metadata_obj = json.loads(metadata_raw)
            except json.JSONDecodeError as e:
                logging.warning(f"Ошибка парсинга JSON в документе {doc.get('doc_id', 'unknown')}: {e}")
        elif isinstance(metadata_raw, dict):
            metadata_obj = metadata_raw

        
        for field in target_fields:
            doc[field] = metadata_obj.get(field)

        
        if 'metadata' in doc:
            del doc['metadata']

    return documents

if __name__ == "__main__":
    
    test_docs = [
        {
            "doc_id": "test-json-string",
            "content": "Текст документа 1",
            "metadata": '{"product_code": "P701", "product_name": "Искра", "synthetic": true, "quality_tags": ["wide_table"]}'
        },
        {
            "doc_id": "test-dict",
            "content": "Текст документа 2",
            "metadata": {
                "product_code": "P702", 
                "product_name": "Росинка", 
                "attachment_path": "knowledge_attachments/p702/file.pdf", 
                "attachment_format": "pdf"
            }
        },
        {
            "doc_id": "test-broken-json",
            "content": "Текст документа 3",
            "metadata": '{"product_code": "P703", broken_json...}'
        }
    ]

    print("--- ДО РАСПАКОВКИ (Документ 1) ---")
    print(json.dumps(test_docs[0], ensure_ascii=False, indent=2))
    print("\n" + "="*50 + "\n")

    flattened_docs = flatten_metadata(test_docs)

    print("--- ПОСЛЕ РАСПАКОВКИ (Документ 1: Успешный JSON) ---")
    print(json.dumps(flattened_docs[0], ensure_ascii=False, indent=2))
    print("\n--- ПОСЛЕ РАСПАКОВКИ (Документ 2: Готовый dict) ---")
    print(json.dumps(flattened_docs[1], ensure_ascii=False, indent=2))
    print("\n--- ПОСЛЕ РАСПАКОВКИ (Документ 3: Битый JSON -> поля None) ---")
    print(json.dumps(flattened_docs[2], ensure_ascii=False, indent=2))