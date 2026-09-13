FROM python:3.9-slim

# Установка системных зависимостей, необходимых для сборки пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости (в том числе принудительно PyMuPDF для PDF)
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir PyMuPDF python-docx

# Копируем код проекта
COPY . .

# Открываем порт для uvicorn
EXPOSE 8009

# Запускаем сервер
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8009"]
