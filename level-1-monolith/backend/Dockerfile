FROM python:3.12-slim

# Запуск не от root — базовая практика безопасности контейнеров.
# Если злоумышленник получит RCE, он окажется внутри контейнера
# без прав root, что значительно ограничивает его возможности.
RUN useradd --create-home appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app
USER appuser

# entrypoint.sh: сначала миграции, потом сервер.
# Так мы гарантируем что схема БД всегда актуальна при старте.
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
