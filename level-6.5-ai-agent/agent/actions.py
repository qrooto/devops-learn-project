"""
Безопасные исполняемые действия агента.

Принцип минимальных привилегий:
  - Агент перезапускает контейнеры через Docker socket API
  - Агент НЕ имеет SSH-доступа к серверам
  - Агент НЕ может удалять данные или останавливать БД/мониторинг
  - Каждое действие логируется с указанием кто его инициировал

Список допустимых действий намеренно минимален.
Добавляй новые только после тщательного обдумывания последствий.
"""
import logging
from typing import Any

import docker
import docker.errors

log = logging.getLogger(__name__)

# Хранилище ожидающих подтверждения действий: session_id → {action, params, alert}
# В production заменить на Redis чтобы не терять при рестарте агента
pending_actions: dict[str, dict[str, Any]] = {}

# Контейнеры которые агент НИКОГДА не должен трогать
PROTECTED_CONTAINERS = frozenset({
    "prometheus", "grafana", "loki", "alertmanager",
    "promtail", "cadvisor", "ai-agent",
})


async def execute_action(action: str, params: dict[str, Any]) -> dict[str, Any]:
    """Выполняет одобренное оператором действие. Возвращает {success, message}."""
    log.info(f"Executing action={action!r} params={params}")
    handlers = {
        "restart":    _restart_container,
        "scale_up":   _scale_replicas,
        "scale_down": _scale_replicas,
        "none":       _noop,
    }
    handler = handlers.get(action, _noop)
    try:
        return await handler(params)
    except Exception as e:
        log.error(f"Action {action!r} raised exception: {e}")
        return {"success": False, "message": f"Ошибка выполнения: {e}"}


async def _restart_container(params: dict[str, Any]) -> dict[str, Any]:
    service = params.get("service", "").strip()
    if not service:
        return {"success": False, "message": "Не указан сервис для перезапуска"}

    if _is_protected(service):
        return {
            "success": False,
            "message": f"Контейнер {service!r} в списке защищённых — агент не трогает его",
        }

    try:
        client = docker.from_env()
        containers = client.containers.list(filters={"name": service})
        if not containers:
            return {"success": False, "message": f"Контейнер {service!r} не найден среди запущенных"}

        container = containers[0]
        log.info(f"Restarting container: {container.name}")
        container.restart(timeout=10)
        return {"success": True, "message": f"Контейнер {container.name!r} перезапущен успешно"}

    except docker.errors.APIError as e:
        return {"success": False, "message": f"Docker API error: {e.explanation}"}


async def _scale_replicas(params: dict[str, Any]) -> dict[str, Any]:
    """
    Масштабирование Docker Compose сервиса.
    В K8s-окружении это был бы `kubectl scale deployment/<name> --replicas=N`.
    Здесь возвращаем готовую команду — пользователь видит что именно будет выполнено.
    """
    service = params.get("service", "").strip()
    replicas = params.get("replicas", 1)

    if not service:
        return {"success": False, "message": "Не указан сервис для масштабирования"}
    if _is_protected(service):
        return {"success": False, "message": f"Сервис {service!r} защищён"}

    cmd = f"docker compose scale {service}={replicas}"
    log.info(f"Scale action (informational): {cmd}")
    return {
        "success": True,
        "message": (
            f"Рекомендуемая команда:\n`{cmd}`\n\n"
            f"Выполни в папке level-6-monitoring/ или автоматизируй через compose API."
        ),
    }


async def _noop(_params: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, "message": "Действие не требуется. Мониторинг продолжается."}


def _is_protected(name: str) -> bool:
    return any(p in name for p in PROTECTED_CONTAINERS)
