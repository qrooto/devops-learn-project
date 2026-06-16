"""
Сборщик контекста из Prometheus и Loki.

Агент читает данные ТОЛЬКО через HTTP API — никаких прямых коннектов к БД,
никакого SSH. Это принцип read-only наблюдаемости: видеть всё, трогать минимум.

Архитектура сбора данных:
  Prometheus → instant query (текущие значения метрик)
  Loki       → range query (последние N строк логов за 5 минут)
"""
import logging
import os
from typing import Any

import httpx

log = logging.getLogger(__name__)

PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")

# Таймаут запросов к внешним API — не блокируем обработку алертов
HTTP_TIMEOUT = 10.0


async def collect_context(alert: dict[str, Any]) -> dict[str, Any]:
    """
    Собирает метрики и логи релевантные для конкретного алерта.
    Извлекает имя сервиса из labels алерта.
    """
    labels = alert.get("labels", {})
    # Пробуем разные label-ы в порядке приоритета
    container = (
        labels.get("container") or
        labels.get("job") or
        labels.get("instance", "").split(":")[0] or
        "backend"
    )

    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        metrics, logs = await _gather_all(client, container)

    return {
        "container": container,
        "metrics": metrics,
        "logs": logs,
    }


async def _gather_all(
    client: httpx.AsyncClient,
    container: str,
) -> tuple[dict[str, Any], list[str]]:
    """Запрашивает метрики и логи параллельно через один httpx-клиент."""
    import asyncio
    metrics_task = asyncio.create_task(_fetch_metrics(client, container))
    logs_task = asyncio.create_task(_fetch_logs(client, container))
    metrics = await metrics_task
    logs = await logs_task
    return metrics, logs


async def _fetch_metrics(client: httpx.AsyncClient, container: str) -> dict[str, Any]:
    """
    Мгновенные значения ключевых метрик.
    rate([5m]) — среднее за последние 5 минут, не чувствительно к пикам.
    """
    queries = {
        "rps": (
            f'sum(rate(http_requests_total{{job=~".*{container}.*"}}[5m]))'
        ),
        "error_rate_pct": (
            f'sum(rate(http_requests_total{{job=~".*{container}.*",status_code=~"5.."}}[5m]))'
            f' / sum(rate(http_requests_total{{job=~".*{container}.*"}}[5m])) * 100'
        ),
        "latency_p95_ms": (
            f'histogram_quantile(0.95,'
            f'  sum(rate(http_request_duration_seconds_bucket{{job=~".*{container}.*"}}[5m])) by (le)'
            f') * 1000'
        ),
        "cpu_percent": (
            f'rate(container_cpu_usage_seconds_total{{name=~".*{container}.*"}}[5m]) * 100'
        ),
        "memory_mb": (
            f'container_memory_usage_bytes{{name=~".*{container}.*"}} / 1024 / 1024'
        ),
    }

    results: dict[str, Any] = {}
    for name, query in queries.items():
        try:
            resp = await client.get(
                f"{PROMETHEUS_URL}/api/v1/query",
                params={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()
            result = data.get("data", {}).get("result", [])
            if result:
                raw_value = result[0]["value"][1]
                results[name] = round(float(raw_value), 2)
            else:
                results[name] = None  # Метрика есть, но нет данных для этого сервиса
        except Exception as e:
            log.warning(f"Prometheus query failed [{name}]: {e}")
            results[name] = None

    return results


async def _fetch_logs(
    client: httpx.AsyncClient,
    container: str,
    limit: int = 50,
) -> list[str]:
    """
    Последние N строк логов из Loki.
    direction=backward + limit → самые свежие строки.
    """
    query = f'{{container=~".*{container}.*"}}'
    try:
        resp = await client.get(
            f"{LOKI_URL}/loki/api/v1/query_range",
            params={
                "query": query,
                "limit": limit,
                "direction": "backward",
            },
        )
        resp.raise_for_status()
        data = resp.json()

        lines: list[str] = []
        for stream in data.get("data", {}).get("result", []):
            for _ts, line in stream.get("values", []):
                lines.append(line)

        # Возвращаем в хронологическом порядке (backward → reverse)
        return list(reversed(lines))[:limit]

    except Exception as e:
        log.warning(f"Loki query failed for {container!r}: {e}")
        return []
