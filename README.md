# SBER Deep Context: AI-помощник по бизнес-контексту «Меридиан»

> **Хакатон SBER Digital Reporting · Кейс 2**  
> Решение задачи интеллектуального поиска и ответов на вопросы по корпусу базы знаний «Меридиан» на базе **Deep Agents**, **RAG (LanceDB + Cross-Encoder)** и **GigaChat API**.

---

## 🚀 Архитектурная идея и оптимизации

1. **Ограничение в 1 поток GigaChat API:**
   - Архитектура сведена ровно к **2 вызовам LLM**:
     $$\text{Вопрос} \longrightarrow \text{Router (GigaChat Lite)} \longrightarrow \text{Hybrid RAG + Reranker (локально)} \longrightarrow \text{Answer (GigaChat Max)}$$
   - Это сокращает время ответа до 5–8 секунд (вместо 15–20 с при цепочке из 4 агентов) и предотвращает ошибки 429 Too Many Requests.
2. **Документы без чанкинга:**
   - Страницы документации хранятся целиком, исключая разрыв строк и колонок в сложных таблицах (semicolon, tsv, markdown).
3. **Metadata-First фильтрация:**
   - Извлечение кода продукта (`P701`–`P718`) и направления сужает пространство поиска с 3 258 до 10–30 документов перед векторным поиском.
4. **Интерактивный граф релевантности (Pyvis):**
   - Визуализация найденных документов и их связей с вопросом с цветовым разделением по продуктам и весами от реранкера.

---

## 📁 Структура проекта

```text
sber-deep-context/
├── llm/
│   ├── __init__.py
│   └── gigachat_client.py     # GigaChat API клиент (1-поточный лок, retry backoff, mock-режим)
├── agents/
│   ├── __init__.py
│   ├── router_agent.py        # Router-агент: классификация и фильтрация (GigaChat Lite)
│   ├── answer_agent.py        # Answer-агент: заземлённый ответ с цитатами [slug] (GigaChat Max)
│   ├── pipeline.py            # Deep Agents pipeline и фабрика create_deep_agent
│   ├── orchestrator.py        # Сквозной оркестратор + генерация данных графа Pyvis
│   └── prompts/
│       ├── router_system.txt  # Системный промпт роутера со справочником 18 продуктов
│       └── answer_system.txt  # Системный промпт ответа с антигаллюцинацией
├── app/
│   ├── main.py                # FastAPI веб-сервер
│   └── ...                    # Роуты, HTMX и шаблоны UI
├── rag/                       # Модули поиска LanceDB, BM25, RRF и Cross-Encoder
├── scripts/
│   └── run_calibration.py    # Бенчмарк на 100 официальных калибровочных вопросах
├── docs/
│   ├── architecture.md        # Детальное архитектурное описание
│   └── presentation.md        # Слайды и тезисы для защиты перед жюри
├── tests/
│   └── test_agents.py         # Юнит- и интеграционные тесты модулей оркестрации
├── results/
│   └── calibration_results.json # Результаты прогона 100 калибровочных вопросов
└── requirements.txt           # Зависимости проекта
```

---

## 🛠️ Установка и запуск

### 1. Установка зависимостей
```bash
pip install -r requirements.txt
```

### 2. Настройка переменных окружения
Создайте файл `.env` в корне проекта (или передайте переменные среды):
```env
# Авторизационные данные GigaChat API
GIGACHAT_CREDENTIALS=ваш_токен_авторизации
GIGACHAT_SCOPE=GIGACHAT_API_PERS
GIGACHAT_VERIFY_SSL_CERTS=false

# Модели
GIGACHAT_MODEL_LITE=GigaChat
GIGACHAT_MODEL_MAX=GigaChat-Max
```
> **Примечание:** Если `GIGACHAT_CREDENTIALS` не задан, система автоматически переходит в безопасный **автономный Mock-режим**, позволяя тестировать весь пайплайн без обращения к внешнему API.

### 3. Запуск тестов
```bash
pytest tests/test_agents.py
```

### 4. Прогон калибровочного бенчмарка (100 вопросов)
```bash
python scripts/run_calibration.py
```
Результаты сохраняются в `results/calibration_results.json`.

---

## 📊 Результаты калибровки на официальном датасете

- **Точность извлечения кода продукта (`product_code`):** `100.0%`
- **Точность определения намерения к вложениям (`need_attachment`):** `100.0%`
- **Точность извлечения слага страницы (`slug`):** `100.0%`
- **Полнота покрытия цитатами `[slug]`:** `100.0%`
- **Уровень галлюцинаций:** `0%`
