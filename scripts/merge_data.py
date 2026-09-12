import os
import json
from parse_sql import parse_sql_dump
from normalize_tables import normalize_documents
from extract_metadata import flatten_metadata

def merge_with_attachments(flat_docs: list, att_json_data: dict) -> list:
    """
    Скрещивает документы Участника 1 с текстами вложений Участника 2.
    Если есть вложение по пути — добавляет его текст к основному контенту, 
    иначе оставляет только контент из SQL.
    """
    # 1. Индексируем вложения из файла Участника 2: путь_к_файлу -> текст
    att_dict = {}
    for item in att_json_data.get("attachments", []):
        path = item.get("attachment_path")
        text = item.get("text", "")
        if path:
            att_dict[path] = text

    final_dataset = []
    
    for doc in flat_docs:
        base_content = doc.get("content", "")
        att_path = doc.get("attachment_path")
        
        # 2. Ищем текст вложения по его пути. Если путь есть и текст найден — добавляем его.
        att_text = att_dict.get(att_path, "") if att_path else ""
        
        if att_text:
            page_content = f"{base_content}\n\n--- Текст вложения ---\n{att_text}"
        else:
            page_content = base_content

        # 3. Формируем словарь metadata
        metadata = {
            "doc_id": doc.get("doc_id"),
            "product_code": doc.get("product_code"),
            "product_name": doc.get("product_name"),
            "section": doc.get("section"),
            "owner": doc.get("owner"),
            "methodology_version": doc.get("methodology_version"),
            "lifecycle": doc.get("lifecycle"),
            "quality_tags": doc.get("quality_tags"),
            "slug": doc.get("slug"),
            "updated_at": doc.get("updated_at"),
            "valid_from": doc.get("valid_from"),
            "synthetic": doc.get("synthetic"),
            "attachment_path": att_path,
            "attachment_format": doc.get("attachment_format"),
            "child_slugs": doc.get("child_slugs")
        }

        # Итоговая структура документа для LanceDB
        final_dataset.append({
            "page_content": page_content,
            "metadata": metadata
        })
        
    return final_dataset

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Пути
    sql_file = os.path.normpath(
        os.path.join(script_dir, "..", "meridian_hackathon_knowledge_base", "meridian_hackathon_knowledge_base", "ai_copilot_documents.sql")
    )
    # Путь к файлу с текстами вложений от Участника 2
    att_output_file = os.path.normpath(
        os.path.join(script_dir, "..", "data", "attachments", "attachments.json")
    )
    
    print("1. Запуск пайплайна Участника 1 (Парсинг -> Нормализация -> Метаданные)...")
    raw_docs = list(parse_sql_dump(sql_file))
    norm_docs = normalize_documents(raw_docs)
    flat_docs = flatten_metadata(norm_docs)
    
    # Загружаем данные Участника 2
    attachments_data = {}
    if os.path.exists(att_output_file):
        with open(att_output_file, 'r', encoding='utf-8') as f:
            attachments_data = json.load(f)
        print(f"2. Загружены тексты вложений из {att_output_file}.")
    else:
        print(f"2. Файл вложений {att_output_file} не найден. Скрипт отработает только с базой из SQL.")

    print("3. Скрещиваем в формат page_content + metadata...")
    dataset = merge_with_attachments(flat_docs, attachments_data)
    
    # Тест: выведем структуру первой записи
    print("\n--- ПРИМЕР ИТОГОВОГО JSON ---")
    print(json.dumps(dataset[0], ensure_ascii=False, indent=2))

    # Сохраняем итоговый датасет на диск
    final_output_path = os.path.normpath(
        os.path.join(script_dir, "..", "data", "final_merged_dataset.json")
    )
    
    os.makedirs(os.path.dirname(final_output_path), exist_ok=True)
    with open(final_output_path, 'w', encoding='utf-8') as f:
        json.dump(dataset, f, ensure_ascii=False, indent=2)
        
    print(f"\n4. Итоговый датасет ({len(dataset)} документов) сохранен в: {final_output_path}")