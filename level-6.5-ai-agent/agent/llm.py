"""
Интеграция с Claude API для диагностики инфраструктурных алертов.

Почему LLM для диагностики?
  Классические алерты говорят ЧТО сломалось: "error_rate > 5%".
  Claude объясняет ПОЧЕМУ, глядя на логи и метрики одновременно,
  и предлагает конкретное следующее действие — как опытный DevOps-инженер.

Промпт спроектирован так чтобы ответ был структурированным (парсится кодом),
но понятным человеку даже без парсинга.
"""
import logging
import os
from dataclasses import dataclass, field
from typing import Any

import anthropic

log = logging.getLogger(__name__)

CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")
MAX_LOG_LINES = 30   # Не заваливаем Claude километрами логов
MAX_TOKENS = 1024


@dataclass
class Diagnosis:
    summary: str              # 1-2 предложения — что случилось
    root_cause: str           # Вероятная причина
    action: str               # "restart" | "scale_up" | "scale_down" | "none"
    action_params: dict       # {"service": "backend_1"} или {"service": "...", "replicas": 5}
    confidence: str           # "high" | "medium" | "low"
    details: str              # Подробности от Claude (показываем оператору)
    raw_text: str = field(repr=False)  # Полный сырой ответ для отладки


def make_client() -> anthropic.Anthropic:
    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("CLAUDE_API_KEY не задан в переменных окружения")
    return anthropic.Anthropic(api_key=api_key)


async def diagnose(alert: dict[str, Any], context: dict[str, Any]) -> Diagnosis:
    """
    Основная функция: строит промпт, вызывает Claude, парсит ответ.
    При любой ошибке API возвращает Diagnosis с action='none' — не блокируем процесс.
    """
    prompt = _build_prompt(alert, context)
    log.debug(f"Sending prompt to Claude ({len(prompt)} chars)")

    try:
        client = make_client()
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = message.content[0].text
        log.info(f"Claude responded ({len(raw)} chars)")
        return _parse_response(raw, context)

    except anthropic.AuthenticationError:
        log.error("Claude API: неверный CLAUDE_API_KEY")
        return _error_diagnosis("Неверный API ключ Claude. Проверь CLAUDE_API_KEY в .env")
    except anthropic.RateLimitError:
        log.warning("Claude API: rate limit exceeded")
        return _error_diagnosis("Claude API rate limit. Повтори через минуту.")
    except anthropic.APIError as e:
        log.error(f"Claude API error: {e}")
        return _error_diagnosis(f"Claude API недоступен: {e}")


def _build_prompt(alert: dict[str, Any], context: dict[str, Any]) -> str:
    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})
    metrics = context.get("metrics", {})
    logs = context.get("logs", [])
    container = context.get("container", "неизвестен")

    alert_name = labels.get("alertname", "Unknown")
    severity = labels.get("severity", "unknown")
    description = (
        annotations.get("description") or
        annotations.get("summary") or
        "Описание не предоставлено"
    )

    # Форматируем метрики — пропускаем None (недоступные)
    metrics_lines = [
        f"  {k}: {v}" for k, v in metrics.items() if v is not None
    ]
    metrics_str = "\n".join(metrics_lines) if metrics_lines else "  Метрики недоступны"

    # Берём последние MAX_LOG_LINES строк — самые свежие и релевантные
    recent_logs = logs[-MAX_LOG_LINES:]
    logs_str = "\n".join(recent_logs) if recent_logs else "Логи недоступны"

    return f"""Ты — опытный DevOps-инженер. Проанализируй алерт и предложи решение.

## Алерт
- Имя: {alert_name}
- Severity: {severity}
- Сервис: {container}
- Описание: {description}

## Текущие метрики (последние 5 минут)
{metrics_str}

## Последние логи (хронологически)
```
{logs_str}
```

## Задача
Дай структурированный ответ строго в следующем формате (каждое поле с новой строки):

SUMMARY: [1-2 предложения — что происходит прямо сейчас]
ROOT_CAUSE: [вероятная причина проблемы]
ACTION: [одно из: restart / scale_up / scale_down / none]
SERVICE: [имя сервиса для действия, например backend_1 или backend]
REPLICAS: [число, только для scale_up/scale_down]
CONFIDENCE: [one of: high / medium / low]
DETAILS: [подробное объяснение для оператора, можно несколько предложений]

Правила выбора ACTION:
- restart: если сервис завис, crashloopbackoff, OOM-killed
- scale_up: если перегружен (высокий CPU/latency при нормальных логах)
- scale_down: если избыточно много реплик, нагрузка упала
- none: если причина неясна, действие небезопасно, или нужен человек

Помни: ACTION=none лучше чем неправильный restart в продакшне."""


def _parse_response(text: str, context: dict[str, Any]) -> Diagnosis:
    """
    Парсит структурированный ответ Claude.
    Нечувствителен к регистру и лишним пробелам.
    """
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().upper()
        if key in ("SUMMARY", "ROOT_CAUSE", "ACTION", "SERVICE", "REPLICAS", "CONFIDENCE", "DETAILS"):
            parsed[key] = value.strip()

    action = parsed.get("ACTION", "none").lower()
    if action not in ("restart", "scale_up", "scale_down", "none"):
        action = "none"

    service = parsed.get("SERVICE", context.get("container", "")).strip()

    action_params: dict[str, Any] = {}
    if action == "restart":
        action_params = {"service": service}
    elif action in ("scale_up", "scale_down"):
        try:
            replicas = int(parsed.get("REPLICAS", "3"))
        except ValueError:
            replicas = 3
        action_params = {"service": service, "replicas": replicas}

    return Diagnosis(
        summary=parsed.get("SUMMARY", "Не удалось получить описание"),
        root_cause=parsed.get("ROOT_CAUSE", "Неизвестно"),
        action=action,
        action_params=action_params,
        confidence=parsed.get("CONFIDENCE", "low"),
        details=parsed.get("DETAILS", ""),
        raw_text=text,
    )


def _error_diagnosis(message: str) -> Diagnosis:
    return Diagnosis(
        summary=f"Ошибка диагностики: {message}",
        root_cause="Недоступен Claude API",
        action="none",
        action_params={},
        confidence="low",
        details=message,
        raw_text="",
    )
