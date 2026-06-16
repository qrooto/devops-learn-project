FROM python:3.12-slim

# Non-root user — агент не должен работать от root даже внутри контейнера.
# Docker socket монтируется read-write (нужен для restart), поэтому особенно важно.
RUN useradd --create-home appuser

# Добавляем appuser в группу docker чтобы мог работать с сокетом
RUN groupadd -g 999 docker-host && usermod -aG docker-host appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R appuser:appuser /app
USER appuser

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
