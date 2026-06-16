"""
Telegram-бот агента через raw HTTP API.

Используем httpx напрямую вместо python-telegram-bot чтобы:
  1. Не иметь конфликтов event loop с FastAPI (оба asyncio)
  2. Не добавлять тяжёлую зависимость без необходимости
  3. Показать как работает Telegram Bot API "под капотом"

Режим: long polling (getUpdates с timeout=30).
Не требует публичного HTTPS URL — работает за NAT/firewall.
"""
import asyncio
import logging
import os
from typing import Any

import httpx

from actions import execute_action, pending_actions
from llm import Diagnosis

log = logging.getLogger(__name__)

TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# Таймаут long-poll запроса (секунды). Telegram держит соединение открытым.
POLL_TIMEOUT = 30


async def run_polling() -> None:
    """
    Фоновый цикл опроса Telegram.
    Запускается в lifespan FastAPI как asyncio.Task.
    При отмене задачи завершается корректно.
    """
    offset = 0
    log.info("Telegram polling started")

    async with httpx.AsyncClient(timeout=POLL_TIMEOUT + 5) as client:
        while True:
            try:
                updates = await _get_updates(client, offset)
                for update in updates:
                    offset = update["update_id"] + 1
                    if "callback_query" in update:
                        await _handle_callback(client, update["callback_query"])
            except asyncio.CancelledError:
                log.info("Telegram polling stopped")
                return
            except httpx.ReadTimeout:
                pass  # Нормально — long-poll истёк, повторяем
            except Exception as e:
                log.error(f"Polling error: {e}")
                await asyncio.sleep(5)


async def send_diagnosis(diagnosis: Diagnosis, session_id: str) -> None:
    """Отправляет диагноз в Telegram с кнопками Approve / Reject."""
    text = _format_diagnosis(diagnosis, session_id)
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Approve", "callback_data": f"approve:{session_id}"},
            {"text": "❌ Reject",  "callback_data": f"reject:{session_id}"},
        ]]
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        await _api_call(client, "sendMessage", {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": keyboard,
        })
    log.info(f"Diagnosis sent to Telegram, session={session_id}")


# ── Внутренние функции ──────────────────────────────────────────────────────────

async def _get_updates(client: httpx.AsyncClient, offset: int) -> list[dict]:
    resp = await client.get(
        f"{BASE_URL}/getUpdates",
        params={"offset": offset, "timeout": POLL_TIMEOUT, "allowed_updates": ["callback_query"]},
        timeout=POLL_TIMEOUT + 5,
    )
    data = resp.json()
    if not data.get("ok"):
        log.warning(f"getUpdates error: {data}")
        return []
    return data.get("result", [])


async def _handle_callback(client: httpx.AsyncClient, callback: dict[str, Any]) -> None:
    """Обрабатывает нажатие кнопки Approve или Reject."""
    query_id = callback["id"]
    message_id = callback["message"]["message_id"]
    data = callback.get("data", "")

    # Сразу подтвердим нажатие — иначе кнопка будет крутиться
    await _api_call(client, "answerCallbackQuery", {"callback_query_id": query_id})

    if ":" not in data:
        return

    action_type, session_id = data.split(":", 1)
    pending = pending_actions.get(session_id)

    if not pending:
        await _edit_message(client, message_id,
            f"⚠️ Сессия `{session_id}` не найдена или уже обработана.")
        return

    if action_type == "reject":
        del pending_actions[session_id]
        log.info(f"Session {session_id} rejected by operator")
        await _edit_message(client, message_id,
            callback["message"]["text"] + "\n\n❌ *Отклонено оператором*")
        return

    if action_type == "approve":
        await _edit_message(client, message_id,
            callback["message"]["text"] + "\n\n⏳ *Выполняется...*")

        result = await execute_action(pending["action"], pending["action_params"])
        del pending_actions[session_id]

        status = "✅" if result["success"] else "❌"
        await _api_call(client, "sendMessage", {
            "chat_id": CHAT_ID,
            "text": f"{status} *Результат*\n\n{result['message']}",
            "parse_mode": "Markdown",
        })
        log.info(f"Session {session_id} approved, success={result['success']}")


async def _edit_message(client: httpx.AsyncClient, message_id: int, text: str) -> None:
    await _api_call(client, "editMessageText", {
        "chat_id": CHAT_ID,
        "message_id": message_id,
        "text": text,
        "parse_mode": "Markdown",
    })


async def _api_call(
    client: httpx.AsyncClient,
    method: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    resp = await client.post(f"{BASE_URL}/{method}", json=payload, timeout=10.0)
    data = resp.json()
    if not data.get("ok"):
        log.warning(f"Telegram API {method} failed: {data.get('description')}")
    return data


def _format_diagnosis(diagnosis: Diagnosis, session_id: str) -> str:
    confidence_emoji = {"high": "🟢", "medium": "🟡", "low": "🔴"}.get(diagnosis.confidence, "⚪")
    action_text = _format_action(diagnosis)

    lines = [
        "🚨 *AI Диагностика алерта*",
        "",
        f"*Проблема:* {diagnosis.summary}",
        "",
        f"*Причина:* {diagnosis.root_cause}",
    ]
    if diagnosis.details:
        lines += ["", f"*Подробности:* {diagnosis.details}"]

    lines += [
        "",
        f"*Предлагаемое действие:*",
        f"`{action_text}`",
        "",
        f"{confidence_emoji} Уверенность: *{diagnosis.confidence}*",
        f"🔑 Session: `{session_id}`",
    ]
    return "\n".join(lines)


def _format_action(diagnosis: Diagnosis) -> str:
    if diagnosis.action == "restart":
        svc = diagnosis.action_params.get("service", "?")
        return f"docker restart {svc}"
    if diagnosis.action in ("scale_up", "scale_down"):
        svc = diagnosis.action_params.get("service", "?")
        n = diagnosis.action_params.get("replicas", "?")
        return f"docker compose scale {svc}={n}"
    return "Действие не требуется (none)"
