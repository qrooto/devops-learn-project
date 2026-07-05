# Уровень 6.5 — AI Diagnostic Agent

## Зачем начинать отсюда?

На уровне 6 ты научился видеть проблему: Grafana показывает красный error rate, Prometheus шлёт алерт. Но дальше — ручная работа:

1. Получил уведомление → открыл Grafana
2. Нашёл нужный дашборд → посмотрел метрики
3. Открыл Loki → нашёл логи нужного сервиса → прочитал
4. Понял что случилось → решил что делать
5. Подключился по SSH или через UI → выполнил действие

В 2:00 ночи. После третьего алерта за смену.

**AI-агент автоматизирует шаги 1-4** и предлагает шаг 5 с кнопкой "Approve". Ты принимаешь решение — агент исполняет.

## Аналогия

Без агента: пожарная сигнализация сработала — ты сам бежишь смотреть что горит, в каком крыле, как тушить.

С агентом: сигнализация → агент сам открывает камеры, проверяет датчики, читает план эвакуации, пишет тебе "Возгорание в серверной, рекомендую активировать систему пожаротушения \[Approve\] \[Reject\]".

## Архитектура

```
Alertmanager
    │
    │ POST /webhook  (при срабатывании алерта)
    ▼
┌─────────────────────────────────────────────────────────────┐
│                    AI Diagnostic Agent                      │
│                                                             │
│  main.py                                                    │
│  ├── parse alert (alertname, labels, severity)              │
│  │                                                          │
│  ├── diagnostics.py ──────────────────────────────────────→ Prometheus API
│  │   collect_context()    ──────────────────────────────→   Loki API
│  │   {metrics, logs}                                        │
│  │                                                          │
│  ├── llm.py                                                 │
│  │   diagnose(alert, context) ──────────────────────────→  Claude API
│  │   → Diagnosis{summary, root_cause, action, confidence}  │
│  │                                                          │
│  └── telegram_bot.py                                        │
│      send_diagnosis() ──────────────────────────────────→  Telegram
│                                                             │
└─────────────────────────────────────────────────────────────┘
                                    │
                         Оператор видит сообщение:
                         "Error rate 12%. Причина: OOM-killed.
                          Действие: restart backend_2
                          [✅ Approve] [❌ Reject]"
                                    │
                         ┌──────────┴──────────┐
                    Approve                  Reject
                         │
                    actions.py
                    docker.restart("backend_2")
                         │
                    Отчёт в Telegram:
                    "✅ backend_2 перезапущен"
```

**Что агент НЕ делает:**
- Не имеет SSH-доступа к серверам
- Не удаляет данные и не останавливает БД/мониторинг
- Не выполняет действия без Approve оператора
- Не хранит логи и метрики — только читает API

---

## Предварительные требования

- Запущен стек из уровня 6 (`level-6-monitoring/`)
- Есть аккаунт в Anthropic Console (claude API)
- Есть Telegram-аккаунт

---

## Шаг 1 — Создать Telegram-бота

```bash
# 1. Открой Telegram → найди @BotFather → напиши /newbot
# 2. Укажи имя бота: "DevOps Alert Bot"
# 3. Укажи username: "my_devops_alert_bot" (должен заканчиваться на _bot)
# 4. BotFather даст токен вида: 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ

# 5. Напиши своему боту любое сообщение (иначе getUpdates вернёт пустой массив)

# 6. Получи свой chat_id:
curl -s "https://api.telegram.org/bot<ВАШ_ТОКЕН>/getUpdates" | python3 -m json.tool
```

В выводе найди:
```json
{
    "result": [{
        "message": {
            "chat": {
                "id": -100123456789   ← это и есть TELEGRAM_CHAT_ID
            }
        }
    }]
}
```

**Для группового чата:** добавь бота в группу, он должен быть администратором (иначе не получит callback-и).

---

## Шаг 2 — Получить Claude API ключ

1. Зайди на `https://console.anthropic.com/`
2. Settings → API Keys → Create Key
3. Скопируй ключ — он показывается один раз

**Стоимость:** примерно $0.003 за один диагностический запрос (входящий + исходящий токены). При 10 алертах в день — менее $1 в месяц.

---

## Шаг 3 — Настроить переменные окружения

```bash
cd level-6.5-ai-agent
cp .env.example .env
nano .env
```

Заполни все поля:
```env
CLAUDE_API_KEY=sk-ant-api03-...
TELEGRAM_BOT_TOKEN=123456789:ABC...
TELEGRAM_CHAT_ID=-100123456789
PROMETHEUS_URL=http://prometheus:9090
LOKI_URL=http://loki:3100
```

**Проверь что level-6 стек запущен:**
```bash
docker compose -f ../level-6-monitoring/docker-compose.yml ps
# prometheus, grafana, loki, backend_1/2/3 должны быть Up
```

---

## Шаг 4 — Подключить агента к сети мониторинга

Агент должен достучаться до Prometheus и Loki. Они в сети `level-6-monitoring_default`.

```bash
# Проверь имя сети:
docker network ls | grep monitoring
# level-6-monitoring_default

# Если имя отличается — обнови в docker-compose.yml:
# networks:
#   monitoring_net:
#     name: <ТВОЁ_ИМЯ_СЕТИ>
```

---

## Шаг 5 — Настроить Alertmanager webhook

Если в level-6 ещё нет Alertmanager, добавь его.

**Добавь в `level-6-monitoring/docker-compose.yml`:**
```yaml
alertmanager:
  image: prom/alertmanager:v0.27.0
  container_name: alertmanager
  volumes:
    - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
  ports:
    - "9093:9093"
```

**Создай `level-6-monitoring/alertmanager/alertmanager.yml`** (скопируй из `alerts/alertmanager-webhook.yml` в этой папке — там полный файл с комментариями).

**Добавь в `level-6-monitoring/prometheus/prometheus.yml`:**
```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```

**Перезапусти level-6 стек:**
```bash
docker compose -f ../level-6-monitoring/docker-compose.yml up -d
```

---

## Шаг 6 — Запустить агента

```bash
cd level-6.5-ai-agent
docker compose up --build -d

# Смотреть логи (здесь будет видно каждый шаг обработки):
docker compose logs -f agent
```

**Что должен увидеть в логах:**
```
2025-01-01 12:00:00 INFO     agent — Agent started. Waiting for Alertmanager webhooks on POST /webhook
2025-01-01 12:00:00 INFO     agent — Telegram polling started
```

**Проверь health:**
```bash
curl http://localhost:8080/health
# {"status": "ok", "pending_sessions": "0"}
```

---

## Шаг 7 — Тест: отправить вебхук вручную

Сначала убедись что всё работает без реального алерта:

```bash
curl -s -X POST http://localhost:8080/webhook \
  -H "Content-Type: application/json" \
  -d '{
    "version": "4",
    "alerts": [{
      "status": "firing",
      "labels": {
        "alertname": "HighErrorRate",
        "severity": "critical",
        "job": "backend_1",
        "container": "backend"
      },
      "annotations": {
        "summary": "Error rate выше 5%",
        "description": "Текущий error rate: 12%. Начался 5 минут назад."
      }
    }]
  }'
```

**Что должно произойти:**
1. Агент получил вебхук → в логах `Processing alert: HighErrorRate`
2. Запросил Prometheus и Loki → `Context collected`
3. Отправил в Claude → `Diagnosis: action=restart`
4. В Telegram пришло сообщение с кнопками

**Нажми [✅ Approve]** — в логах появится `Restarted container` и в Telegram придёт отчёт.

---

## Шаг 8 — Тест с реальным алертом

Теперь вызовем настоящий алерт остановив контейнер под нагрузкой:

```bash
# Терминал 1: нагрузочный тест
k6 run ../level-2-scaling/load-tests/balancer-test.js

# Терминал 2: убиваем бэкенд
docker compose -f ../level-6-monitoring/docker-compose.yml stop backend_2
```

**Что наблюдать:**

**В Grafana** (`http://localhost:3000`):
- Error rate резко вырос (один инстанс из трёх упал)
- RPS упал на треть

**В Alertmanager** (`http://localhost:9093`):
- Через 30-60 секунд появится firing алерт

**В Telegram**:
- Придёт сообщение от AI-агента с анализом ситуации
- Confidence должен быть `medium` или `high`
- Предложенное действие: `restart backend_2`

**В логах агента:**
```
Processing alert: BackendDown
Context collected: metrics=['rps', 'error_rate_pct'...], log_lines=42
Diagnosis: action='restart', confidence='high', service='backend_2'
Diagnosis sent to Telegram, session=a1b2c3d4
```

**Нажми Approve** → backend_2 перезапустится → метрики нормализуются.

---

## Шаг 9 — Понять промпт и настроить под себя

```bash
cat agent/llm.py
```

Найди функцию `_build_prompt()`. Промпт спроектирован так чтобы:
1. Дать Claude максимум релевантного контекста (метрики + логи)
2. Ограничить действия безопасным списком (`restart / scale_up / scale_down / none`)
3. Получить структурированный ответ который легко парсить

**Поэкспериментируй:**
- Измени `MAX_LOG_LINES = 30` на `50` — больше контекста, выше стоимость
- Добавь новое допустимое действие в `actions.py` и разреши его в промпте
- Измени тон промпта — попробуй более осторожный ("предпочитай none если не уверен")

---

## Шаг 10 — Безопасность: что защищает систему

```bash
cat agent/actions.py
# Найди PROTECTED_CONTAINERS
```

**Уровни защиты:**

1. **PROTECTED_CONTAINERS** — список сервисов которые агент не трогает никогда:
   `prometheus, grafana, loki, alertmanager, promtail, cadvisor, ai-agent`

2. **Approve/Reject** — человек всегда в контуре принятия решения. Агент не делает ничего автоматически.

3. **Read-only API** — Prometheus и Loki доступны только для чтения. Агент не меняет конфигурацию мониторинга.

4. **Нет SSH** — агент не может подключиться к серверам. Все действия через Docker API.

5. **Минимальный список действий** — только `restart` и `scale`. Нет `stop`, нет `rm`, нет `exec`.

**Что улучшить в production:**
- Docker socket proxy (Tecnativa/docker-socket-proxy) — ограничивает API до конкретных endpoint-ов
- Добавить аутентификацию на `/webhook` (Bearer token от Alertmanager)
- Хранить `pending_actions` в Redis чтобы не терять при рестарте агента
- Rate limiting — не обрабатывать более N алертов в минуту

---

## Типичные ошибки

**"Telegram polling error: 401 Unauthorized"** → Неверный `TELEGRAM_BOT_TOKEN`. Проверь что скопировал полностью (начинается с `123456789:`).

**"Bot wrote but no message in Telegram"** → Скорее всего неверный `TELEGRAM_CHAT_ID`. Повтори шаг с `getUpdates` и убедись что написал боту сообщение первым.

**"Claude API: authentication error"** → Неверный `CLAUDE_API_KEY` или ключ деактивирован. Проверь в console.anthropic.com.

**"Container not found"** → Claude предложил имя сервиса которого нет. Логи покажут что искали. Агент вернёт "success: false" — в Telegram придёт сообщение об ошибке.

**"Loki query failed"** → Проверь что агент в сети мониторинга: `docker network inspect level-6-monitoring_default | grep ai-agent`.

**Prometheus метрики все `null`** → Метрики из level-6 backend используют специфичные labels. Убедись что `job` в алерте совпадает с job в Prometheus. Проверь в браузере: `http://localhost:9090/api/v1/label/job/values`.

---

## На собеседовании спросят

**Q: Как обеспечить безопасность AI-агента у которого есть доступ к инфраструктуре?**
A: Принцип минимальных привилегий — агент имеет только то что нужно для своих задач. Read-only доступ к API метрик, write только для restart через Docker API (и то через защищённый список). Человек всегда в контуре принятия решения (approve/reject). Никакого SSH, никакого доступа к данным.

**Q: Что такое Human-in-the-loop и когда он необходим?**
A: Паттерн где AI предлагает действие, а человек его подтверждает. Необходим когда действие необратимо или рискованно (рестарт БД), когда уверенность модели низкая, когда последствия широки (масштабирование дорогого ресурса). Для рутинных безопасных действий можно отказаться от подтверждения, но начинать всегда стоит с human-in-the-loop.

**Q: Как отлаживать промпт для LLM в production-системе?**
A: Логировать полные промпты и ответы (в отдельный файл/SIEM). Версионировать промпты как код. Иметь тестовый набор алертов с известными правильными ответами (evals). Мониторить метрики: процент action=none, процент confidence=low — рост этих цифр сигнализирует о деградации промпта.

**Q: Почему long polling а не webhook для Telegram?**
A: Webhook требует публичного HTTPS URL — не всегда есть в dev-окружении. Long polling работает за NAT/firewall, проще для локальной разработки. В production переключаются на webhook: меньше задержка, нет постоянного открытого соединения.

**Q: Как масштабировать этого агента если алертов сотни в минуту?**
A: Вынести pending_actions в Redis (shared state между инстансами). Добавить очередь (RabbitMQ/Kafka) между webhook-получателем и обработчиком. Rate limiting на уровне Alertmanager (group_interval, repeat_interval). Batching алертов одного типа — один вызов Claude вместо N.

---

## Итог уровня 6.5 — что ты умеешь

- [ ] Написать FastAPI сервис получающий Alertmanager webhooks
- [ ] Запрашивать Prometheus HTTP API и Loki API для сбора контекста
- [ ] Строить промпт для Claude с структурированным ответом
- [ ] Реализовать Telegram-бота на raw HTTP API (без heavy-weight библиотек)
- [ ] Организовать human-in-the-loop с inline кнопками Approve/Reject
- [ ] Выполнять safe actions через Docker API с защищённым списком
- [ ] Объяснить почему безопасность AI-агентов в инфраструктуре критична

**Следующий шаг:** упаковать всё это в Helm-чарт и деплоить в Kubernetes → Уровень 7.

---

## Коммит

```bash
cd ..
git add level-6.5-ai-agent/
git commit -m "level-6.5: ai diagnostic agent with claude api and telegram approve/reject"
git push origin main
```

---

## Архитектура

- [Концепция: LLM-in-the-loop агент в вакууме](../docs/architecture/level-6.5-ai-agent/concept.html) — LLM объясняет и предлагает, человек решает
- [Реализация: реальный поток обработки алерта](../docs/architecture/level-6.5-ai-agent/implementation.html) — sequence-диаграмма webhook → Prometheus/Loki → Claude → Telegram → Docker API
- [Боль → решение: Level 6 → Level 6.5](../docs/architecture/level-6.5-ai-agent/pain-solution.html) — от ручной интерпретации алертов к готовому диагнозу
- [Сеть: webhook внутрь, API наружу](../docs/architecture/level-6.5-ai-agent/network.html) — ingress от Alertmanager + egress к Claude/Telegram в одном сервисе

**Теория сетей глубже:**
- [Webhook (ingress) vs вызов API (egress)](../docs/architecture/networking-theory/08-webhooks-and-egress.html) — почему это разные направления трафика с разными требованиями к firewall

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
