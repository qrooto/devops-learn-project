"""
AI Diagnostic Agent — точка входа.

Поток данных:
  Alertmanager POST /webhook
      → parse alert
      → collect_context()   [Prometheus + Loki]
      → diagnose()          [Claude API]
      → send_diagnosis()    [Telegram с кнопками Approve/Reject]
      → оператор нажимает кнопку
      → execute_action()    [Docker API]
      → отчёт в Telegram

Все шаги — async, обработка алертов не блокирует приём новых вебхуков.
"""
import asyncio
import logging
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, Request, Response

load_dotenv()

# Инициализируем логгер ДО импорта модулей чтобы видеть их ошибки инициализации
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
)
log = logging.getLogger("agent")

# Импортируем после load_dotenv — модули читают env в момент импорта
from actions import pending_actions  # noqa: E402
from diagnostics import collect_context  # noqa: E402
from llm import diagnose  # noqa: E402
from telegram_bot import run_polling, send_diagnosis  # noqa: E402


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    Запускаем Telegram-polling как фоновую задачу FastAPI.
    При остановке приложения задача отменяется корректно.
    """
    polling_task = asyncio.create_task(run_polling())
    log.info("Agent started. Waiting for Alertmanager webhooks on POST /webhook")
    try:
        yield
    finally:
        polling_task.cancel()
        try:
            await polling_task
        except asyncio.CancelledError:
            pass
        log.info("Agent stopped")


app = FastAPI(title="AI Diagnostic Agent", version="1.0.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "pending_sessions": str(len(pending_actions))}


@app.post("/webhook")
async def alertmanager_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Получает payload от Alertmanager.
    Каждый firing-алерт обрабатывается в фоне — не блокируем ответ.

    Alertmanager ожидает 200 OK быстро, иначе будет retry.
    """
    try:
        payload = await request.json()
    except Exception:
        return Response(status_code=400)

    alerts = payload.get("alerts", [])
    firing = [a for a in alerts if a.get("status") == "firing"]

    for alert in firing:
        background_tasks.add_task(_process_alert, alert)

    log.info(f"Webhook received: {len(alerts)} alerts, {len(firing)} firing")
    return {"received": len(alerts), "processing": len(firing)}


async def _process_alert(alert: dict[str, Any]) -> None:
    """Полный цикл обработки одного алерта."""
    alert_name = alert.get("labels", {}).get("alertname", "Unknown")
    log.info(f"Processing alert: {alert_name}")

    try:
        # Шаг 1: собрать контекст из Prometheus и Loki
        context = await collect_context(alert)
        log.info(
            f"Context collected for {alert_name}: "
            f"metrics={list(context['metrics'].keys())}, "
            f"log_lines={len(context['logs'])}"
        )

        # Шаг 2: получить диагноз от Claude
        diagnosis = await diagnose(alert, context)
        log.info(
            f"Diagnosis: action={diagnosis.action!r}, "
            f"confidence={diagnosis.confidence}, "
            f"service={diagnosis.action_params.get('service')}"
        )

        # Шаг 3: сохранить ожидающее действие
        session_id = str(uuid.uuid4())[:8]
        if diagnosis.action != "none":
            pending_actions[session_id] = {
                "alert": alert,
                "action": diagnosis.action,
                "action_params": diagnosis.action_params,
            }

        # Шаг 4: отправить в Telegram
        await send_diagnosis(diagnosis, session_id)

    except Exception as e:
        log.error(f"Failed to process alert {alert_name!r}: {e}", exc_info=True)
