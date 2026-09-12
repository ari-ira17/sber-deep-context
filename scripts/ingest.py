"""
Ingestion script for Meridian Knowledge Base (Task 3.10).
Imports documents & pre-computed vectors from data/dataset_with_vectors.json into LanceDB,
creates scalar indices, and builds full-text search (FTS) BM25 index.
"""

import os
import sys
import json

# Ensure project root is in python path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from rag.storage import LanceDBStorage
from rag.bm25_search import BM25Search
from rag.search import HybridSearchEngine


def ingest_data():
    project_dir = os.path.dirname(os.path.dirname(__file__))
    input_path = os.path.join(project_dir, "data", "dataset_with_vectors.json")
    
    if not os.path.exists(input_path):
        print(f"❌ Ошибка: файл {input_path} не найден!")
        return False

    print(f"1. Загрузка очищенного датасета из {input_path}...")
    with open(input_path, "r", encoding="utf-8") as f:
        docs = json.load(f)

    print(f"   Загружено документов из JSON: {len(docs)}")

    print("\n2. Инициализация и очистка хранилища LanceDB...")
    storage = LanceDBStorage()
    table = storage.create_table(records=docs, mode="overwrite")
    
    count = storage.count() if hasattr(storage, "count") else len(table.to_pandas())
    print(f"   Успешно записано в таблицу LanceDB: {count} документов.")

    print("\n3. Создание скалярных индексов (product_code, slug, owner, section)...")
    storage.create_scalar_indices(table)
    print("   Скалярные индексы созданы.")

    print("\n4. Создание полнотекстового FTS-индекса (BM25 search)...")
    bm25_search = BM25Search(storage=storage)
    fts_created = bm25_search.create_fts_index(field_name="page_content", replace=True)
    if fts_created:
        print("   FTS-индекс создан успешно.")
    else:
        print("   FTS-индекс будет использоваться через Python BM25 fallback engine.")

    print("\n5. Сквозная проверка гибридного поиска (HybridSearchEngine)...")
    search_engine = HybridSearchEngine(storage=storage)
    test_results = search_engine.search(query_text="ежедневные расчёты", top_k=3)
    print(f"   Тестовый поиск по запросу 'ежедневные расчёты' вернул {len(test_results)} документов.")
    if test_results:
        top_doc = test_results[0]
        meta = top_doc.get("metadata", top_doc)
        print(f"   Топ-1 результат: slug='{meta.get('slug')}', score={top_doc.get('score')}")

    print("\n🎉 Инжест данных в LanceDB успешно завершён!")
    return True


if __name__ == "__main__":
    ingest_data()
