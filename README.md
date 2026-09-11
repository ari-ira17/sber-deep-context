# sber-deep-context
```text
app/
├── __init__.py
├── agents/        # Код для Router Agent и Answer Agent (Deep Agents)
│   └── __init__.py
├── api/           # FastAPI роуты (чат-интерфейс)
│   ├── __init__.py
│   └── routes/
│       └── __init__.py
├── core/          # Настройки (config, prompts)
│   └── __init__.py
├── db/            # Работа с LanceDB (поиск, фильтрация)
│   └── __init__.py
├── ingestion/     # Скрипты загрузки данных (парсинг SQL, OCR Tesseract)
│   └── __init__.py
├── llm/           # Обертка GigaChat + Tool Calling (langchain-gigachat)
│   └── __init__.py
├── static/        # Статические файлы для UI (JS/CSS)
│   └── .gitkeep
└── templates/     # HTMX шаблоны для UI
    └── .gitkeep
data/              # Сюда можно положить исходный SQL дамп и картинки (в .gitignore стоит исключить сами файлы, но оставить папку)
└── .gitkeep
scripts/           # Служебные скрипты (например, создание LanceDB индексов)
└── .gitkeep
tests/             # Тесты и прогон 100 калибровочных вопросов
└── __init__.py
```
