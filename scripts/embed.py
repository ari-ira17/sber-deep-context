import os
import json
from sentence_transformers import SentenceTransformer

def generate_embeddings():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Путь к твоему текущему файлу с данными (можешь поправить имя на свое)
    input_path = os.path.normpath(
        os.path.join(script_dir, "..", "data", "final_merged_dataset.json")
    )
    # Путь для сохранения результата с векторами
    output_path = os.path.normpath(
        os.path.join(script_dir, "..", "data", "dataset_with_vectors.json")
    )

    if not os.path.exists(input_path):
        print(f"Файл {input_path} не найден. Проверь путь.")
        return

    print("Загрузка датасета...")
    with open(input_path, 'r', encoding='utf-8') as f:
        docs = json.load(f)

    print("Загрузка локальной модели эмбеддингов intfloat/multilingual-e5-base...")
    # Модель автоматически скачается при первом запуске (нужен интернет) или возьмется из кэша
    model = SentenceTransformer('intfloat/multilingual-e5-base')

    # Для семейства моделей e5 рекомендуется добавлять префикс "passage: " текстам документов
    texts = [f"passage: {doc.get('page_content', '')}" for doc in docs]

    print(f"Генерация эмбеддингов для {len(texts)} документов (это может занять пару минут)...")
    vectors = model.encode(texts, show_progress_bar=True, batch_size=32)

    # Добавляем вектор в каждый документ на верхний уровень
    for doc, vec in zip(docs, vectors):
        doc['vector'] = vec.tolist()

    print(f"Сохранение результатов в {output_path}...")
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(docs, f, ensure_ascii=False, indent=2)

    print("Генерация эмбеддингов успешно завершена!")

if __name__ == "__main__":
    generate_embeddings()