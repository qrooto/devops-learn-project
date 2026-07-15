# Уровень 6.5 — AI-агент диагностики инцидентов

> **Это [руки]** — практический маршрут уровня. Агент запускается на локальной машине, нужны API-ключи (Claude, Telegram) и туннель до VPS.
> **Теория уровня — в `CURRICULUM.md` → «Уровень 6.5»**: зачем AI-агент, как устроен цикл webhook → диагностика → Telegram, вопросы с собеседований. Легенда `[голова]`/`[руки]` — в START_HERE.md.

## Архитектура

Агент живёт **не на VPS**, а на локальной рабочей машине. Даже квантованная LLM требует 4-8 ГБ RAM только под саму модель — раздувать под это тариф VPS ради процесса, который вызывается раз в несколько минут, не имеет смысла. Локальная машина тянет это без апгрейда сервера, а до Prometheus/Loki на VPS агент достаёт по сети через приватный туннель (см. Шаг 4).

```
┌───────────────────────── VPS ──────────────────────────┐
│                                                         │
│  Alertmanager ──POST /webhook──┐                        │
│  Prometheus :9090  (ufw: закрыт для интернета)  │       │
│  Loki :3100         (ufw: закрыт для интернета) │       │
│                                  │               │       │
└──────────────────────────────┼──┼───────────────┼───────┘
                                 │  │               │
                    WireGuard-туннель (или SSH fallback)
                                 │  │               │
┌────────────────── Локальная машина ──┼───────────┼───────┐
│                                ▼      ▼           ▼        │
│  ┌────────────────────────────────────────────────────┐   │
│  │              AI Diagnostic Agent                    │   │
│  │  main.py                                            │   │
│  │  ├── diagnostics.py ──────→ Prometheus API (туннель)│   │
│  │  │   collect_context()  ──→ Loki API (туннель)      │   │
│  │  ├── llm.py                                         │   │
│  │  │   diagnose() ──────────────────────→ Claude API   │   │
│  │  └── telegram_bot.py                                │   │
│  │      send_diagnosis() ────────────────→ Telegram API │   │
│  └────────────────────────────────────────────────────┘   │
│                         │                                  │
│              Оператор видит в Telegram:                    │
│              "Error rate 12%. Причина: OOM-killed.         │
│               Действие: restart backend_2                  │
│               [✅ Approve] [❌ Reject]"                     │
│                         │                                  │
│                    Approve → actions.py                    │
│                    DOCKER_HOST=ssh://user@vps-ip            │
│                    docker.restart("backend_2") ─────────────┼──→ SSH на VPS
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**Что изменилось по сравнению с наивной схемой "всё на VPS":**
- Агент, вызовы Claude и Telegram-бот — на локальной машине, не в docker-compose VPS
- Prometheus и Loki остаются на VPS, но их порты закрыты для интернета — агент достаёт до них только через туннель (Шаг 4)
- Restart-действия идут не через локальный `docker.sock`, а через `DOCKER_HOST=ssh://user@vps-ip` — тот же Docker API агента, но транспортом служит SSH до VPS вместо локального сокета

**Что агент НЕ делает:**
- Не имеет интерактивного shell-доступа к серверам — DOCKER_HOST=ssh — это транспорт для того же ограниченного Docker API, не произвольные команды
- Не удаляет данные и не останавливает БД/мониторинг
- Не выполняет действия без Approve оператора
- Не хранит логи и метрики — только читает API

---

## Предварительные требования

- Запущен стек из уровня 6 (`level-6-monitoring/`) на VPS
- Локальная машина для агента: Docker, доступ в интернет, SSH-доступ к VPS
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
# 10.8.0.1 — адрес VPS ВНУТРИ WireGuard-туннеля (Шаг 4), не публичный IP.
# Без туннеля эти URL недостижимы — порты 9090/3100 закрыты для интернета.
PROMETHEUS_URL=http://10.8.0.1:9090
LOKI_URL=http://10.8.0.1:3100
```

**Проверь что level-6 стек запущен (на VPS, по SSH):**
```bash
ssh user@vps-ip "docker compose -f ~/devops-project/level-6-monitoring/docker-compose.yml ps"
# prometheus, grafana, loki, backend_1/2/3 должны быть Up
```

---

## Шаг 4 — Закрыть Prometheus/Loki от интернета и открыть туннель для агента

Агент теперь не в одной docker-сети с мониторингом (она осталась только на VPS) — ему нужен собственный сетевой путь до Prometheus и Loki. Заодно закрываем то, что и так не должно было быть открыто наружу с Level 6.

### 4.1 — ufw: закрыть 9090 и 3100 для интернета (на VPS)

```bash
# Если раньше открывал явно — удали общий allow:
sudo ufw delete allow 9090/tcp
sudo ufw delete allow 3100/tcp

# Разрешаем эти порты ТОЛЬКО из подсети туннеля (настроим её ниже, 10.8.0.0/24):
sudo ufw allow from 10.8.0.0/24 to any port 9090 proto tcp
sudo ufw allow from 10.8.0.0/24 to any port 3100 proto tcp
sudo ufw status numbered
```

### 4.2 — WireGuard-туннель (основной вариант)

**На VPS:**
```bash
sudo apt install -y wireguard
wg genkey | sudo tee /etc/wireguard/privatekey | wg pubkey | sudo tee /etc/wireguard/publickey
sudo chmod 600 /etc/wireguard/privatekey

sudo nano /etc/wireguard/wg0.conf
```
```ini
[Interface]
Address = 10.8.0.1/24
PrivateKey = <содержимое /etc/wireguard/privatekey>
ListenPort = 51820

[Peer]
PublicKey = <публичный ключ локальной машины — получишь на следующем шаге>
AllowedIPs = 10.8.0.2/32
```
```bash
sudo ufw allow 51820/udp
sudo wg-quick up wg0
sudo systemctl enable wg-quick@wg0
```

**На локальной машине:**
```bash
wg genkey | tee privatekey | wg pubkey > publickey

sudo nano /etc/wireguard/wg0.conf
```
```ini
[Interface]
Address = 10.8.0.2/24
PrivateKey = <содержимое privatekey>

[Peer]
PublicKey = <публичный ключ VPS>
Endpoint = <публичный IP VPS>:51820
AllowedIPs = 10.8.0.1/32
PersistentKeepalive = 25
```
```bash
sudo wg-quick up wg0

# Проверка туннеля в обе стороны:
ping 10.8.0.1                              # с локальной машины до VPS
curl http://10.8.0.1:9090/-/healthy        # Prometheus через туннель
curl http://10.8.0.1:3100/ready            # Loki через туннель
```

WireGuard — полноценная приватная сеть, а не однонаправленный проброс: VPS видит локальную машину по 10.8.0.2 так же, как локальная машина видит VPS по 10.8.0.1. Это важно для Шага 5 — Alertmanager должен достучаться до вебхука агента в ОБРАТНОМ направлении (VPS → локальная машина).

### 4.3 — SSH-туннель (временный/учебный fallback)

Обычный SSH-проброс однонаправленный, поэтому нужны оба варианта сразу:

```bash
# Локальная машина → VPS: доступ агента к Prometheus/Loki (pull)
ssh -N -L 9090:localhost:9090 -L 3100:localhost:3100 user@vps-ip &

# VPS → локальная машина: Alertmanager стучится в вебхук агента (push, обратное направление)
ssh -N -R 8080:localhost:8080 user@vps-ip &
```

🔒 **Security:** обратный проброс (`-R`) по умолчанию слушает только на `localhost` VPS — чтобы Alertmanager (тоже на VPS) до него достучался, этого достаточно и ничего дополнительно открывать не нужно. Если увидишь совет добавить `GatewayPorts yes` в `sshd_config` — не делай этого без крайней необходимости: это открывает порт всем, кто может подключиться к VPS, а не только локальным процессам. WireGuard этой проблемы не имеет вообще, поэтому он основной вариант, а SSH — только когда совсем нет времени поднимать VPN.

### 4.4 — Telegram Bot API может быть недоступен из РФ

`api.telegram.org` периодически блокируется/троттлится для российских IP. Если long polling агента (см. Q&A ниже про polling vs webhook) не получает обновления или зависает:
- Проверь доступность напрямую: `curl -v https://api.telegram.org` с локальной машины
- Если недоступно — нужен прокси/VPN именно для исходящих запросов к Telegram (это отдельная история от WireGuard-туннеля к VPS выше: тот туннель — для Prometheus/Loki/webhook, а этот — для доступа к самому Telegram)

---

## Шаг 5 — Настроить Alertmanager webhook

Alertmanager уже есть в стеке уровня 6 (`docker-compose.yml`, конфиг `alertmanager/alertmanager.yml`, связка с Prometheus через `alerting:` в `prometheus.yml`) — устанавливать ничего не нужно. Осталось добавить receiver для агента.

**Добавь в `level-6-monitoring/alertmanager/alertmanager.yml`** маршруты и receiver `ai-agent` — полный пример с комментариями лежит в `alerts/alertmanager-webhook.yml` этой папки.

⚠️ **Важно поменять при копировании:** в шаблоне `url: 'http://ai-agent:8080/webhook'` — это docker DNS-имя из старой схемы, где агент жил в одной сети с Alertmanager. Теперь агент на локальной машине, замени на адрес локальной машины внутри туннеля:
```yaml
receivers:
  - name: ai-agent
    webhook_configs:
      - url: 'http://10.8.0.2:8080/webhook'   # 10.8.0.2 — локальная машина в WireGuard-туннеле
```
Это и есть то самое обратное направление трафика (VPS → локальная машина) из Шага 4 — убедись что туннель поднят и агент слушает `:8080` ДО того как Alertmanager попробует достучаться.

**Перезапусти level-6 стек (на VPS, по SSH):**
```bash
ssh user@vps-ip "cd ~/devops-project/level-6-monitoring && docker compose up -d"
```

---

## Шаг 6 — Запустить агента (на локальной машине)

Сначала поправь `level-6.5-ai-agent/docker-compose.yml`: секция `networks.monitoring_net` (`external: true, name: level-6-monitoring_default`) — это остаток старой схемы, когда агент и мониторинг были на одном хосте в одной docker-сети. Такой сети на локальной машине нет и не будет — агент достаёт до Prometheus/Loki через WireGuard (Шаг 4), а не через docker network. Удали упоминания `monitoring_net` из сервиса `agent` и из секции `networks`, оставь только `agent_net`.

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
# Терминал 1 (локальная машина или VPS — k6 достаточно HTTP-доступа к nginx): нагрузочный тест
k6 run ../level-2-scaling/load-tests/balancer-test.js

# Терминал 2: убиваем бэкенд НА VPS
ssh user@vps-ip "cd ~/devops-project/level-6-monitoring && docker compose stop backend_2"
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

4. **Нет интерактивного доступа к серверам** — `DOCKER_HOST=ssh://user@vps-ip` использует SSH только как транспорт для того же ограниченного Docker API (restart/scale конкретных контейнеров), это не shell и не произвольные команды на VPS.

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

**"Loki query failed"** → Проверь туннель, а не docker-сеть (агент и мониторинг теперь на разных хостах): `ping 10.8.0.1` и `curl http://10.8.0.1:3100/ready` с локальной машины. Если недоступно — `sudo wg show` на обеих сторонах, проверь что интерфейс `up`.

**Prometheus метрики все `null`** → Метрики из level-6 backend используют специфичные labels. Убедись что `job` в алерте совпадает с job в Prometheus. Проверь через туннель: `http://10.8.0.1:9090/api/v1/label/job/values` (не `localhost` — Prometheus теперь на другом хосте).

---

## Итог уровня 6.5 — что ты умеешь

- [ ] Написать FastAPI сервис получающий Alertmanager webhooks
- [ ] Запрашивать Prometheus HTTP API и Loki API для сбора контекста
- [ ] Строить промпт для Claude с структурированным ответом
- [ ] Реализовать Telegram-бота на raw HTTP API (без heavy-weight библиотек)
- [ ] Организовать human-in-the-loop с inline кнопками Approve/Reject
- [ ] Выполнять safe actions через Docker API с защищённым списком
- [ ] Объяснить почему безопасность AI-агентов в инфраструктуре критична
- [ ] Поднять WireGuard-туннель между двумя хостами и объяснить чем он отличается от однонаправленного SSH-проброса
- [ ] Закрыть внутренние сервисы (Prometheus, Loki) от интернета через ufw, оставив доступ только из нужной подсети

**Следующий шаг:** упаковать всё это в Helm-чарт и деплоить в Kubernetes → Уровень 7.

---

## Security Block: Уровень 6.5

### AI-агент с доступом к инфраструктуре — новая поверхность атаки

Этот уровень добавляет компонент, который может ВЫПОЛНЯТЬ действия на инфраструктуре (не только читать), да ещё и на основе решения LLM. Каждый принцип ниже — конкретный барьер против того, что может пойти не так.

**1. Principle of Least Privilege — агент не может почти ничего**

`PROTECTED_CONTAINERS` (`prometheus, grafana, loki, alertmanager, promtail, cadvisor, ai-agent`) — жёсткий allowlist того, что агент не тронет никогда, даже если LLM это предложит. Список разрешённых действий — только `restart`/`scale`, нет `stop`, `rm`, `exec`.

**2. Default Deny на сети — закрыли то, что не должно быть открыто**

Prometheus (`:9090`) и Loki (`:3100`) на VPS закрыты через ufw для всех, кроме подсети WireGuard-туннеля (`10.8.0.0/24`). До Level 6.5 эти порты были открыты в интернет — см. Security Block Level 6.

**3. Defence in Depth — несколько независимых барьеров, не один**

Даже если атакующий скомпрометирует агента (например, через prompt injection в логах, которые агент читает и передаёт в LLM), у него всё ещё нет: SSH shell-доступа (только Docker API через `DOCKER_HOST=ssh://`), доступа к защищённым контейнерам (`PROTECTED_CONTAINERS`), возможности действовать без Approve человека.

**4. Human-in-the-loop — необратимые действия требует подтверждать человек**

Агент не выполняет ничего автоматически — только предлагает через Telegram с кнопками Approve/Reject. Это осознанный компромисс скорости ради безопасности: LLM может галлюцинировать неверное действие, человек — последний фильтр.

**5. Secrets Management**

`CLAUDE_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` — в `.env`, не в коде и не в docker-compose.yml напрямую.

⚠️ **Антипаттерны:**

- **Публиковать порт 8080 агента наружу VPS без необходимости** — реальный трафик на webhook должен идти только по WireGuard-туннелю от Alertmanager; публикация на 0.0.0.0 расширяет поверхность атаки без пользы.
- **`GatewayPorts yes` на SSH ради удобства reverse-tunnel** — открывает порт VPS всем, кто может подключиться, а не только нужному процессу. Почти всегда есть способ обойтись без этого (см. Шаг 4.3) — а лучше просто использовать WireGuard.

---

## Best Practices Checklist

- [ ] `PROTECTED_CONTAINERS` в `actions.py` включает весь observability-стек и самого агента
- [ ] Разрешённые действия агента — только `restart`/`scale`, никакого `exec`/`rm`/`stop`
- [ ] Approve/Reject в Telegram работает и требуется на каждое действие — агент не действует автоматически
- [ ] Порты 9090 (Prometheus) и 3100 (Loki) закрыты ufw для интернета, доступны только из `10.8.0.0/24`
- [ ] WireGuard-туннель поднят на обеих сторонах (`wg show` показывает `latest handshake` недавним)
- [ ] `DOCKER_HOST=ssh://` используется вместо примонтированного локального `docker.sock`
- [ ] `.env` с `CLAUDE_API_KEY`/`TELEGRAM_BOT_TOKEN` не закоммичен в Git
- [ ] Понимаешь разницу между ingress (webhook) и egress (Claude/Telegram) для этого сервиса

---

## Troubleshooting: Уровень 6.5

### Проблемы с агентом и туннелем

**1. Алерт сработал, но сообщение в Telegram не пришло**

Симптом: `docker compose logs -f agent` не показывает `Processing alert`.

```bash
# Проверь что вебхук вообще дошёл до агента:
curl http://localhost:8080/health
# Проверь что Alertmanager реально пытался достучаться (на VPS):
ssh user@vps-ip "docker compose -f ~/devops-project/level-6-monitoring/docker-compose.yml logs alertmanager | tail -30"
```
Вероятная причина: URL в `alertmanager.yml` указывает на docker DNS-имя (`ai-agent:8080`) вместо туннельного IP локальной машины (`10.8.0.2:8080`) — см. Шаг 5. Или туннель не поднят (`sudo wg show` на VPS).

**2. `collect_context()` падает / `Loki query failed`**

Симптом: в логах агента `Failed to process alert` с traceback внутри `diagnostics.py`.

```bash
ping 10.8.0.1
curl http://10.8.0.1:9090/-/healthy
curl http://10.8.0.1:3100/ready
```
Вероятная причина: WireGuard не поднят или ufw блокирует именно подсеть туннеля (проверь `sudo ufw status numbered` на VPS — правило должно разрешать `10.8.0.0/24`, не конкретный IP).

**3. `execute_action` возвращает "Docker API error"**

Симптом: в Telegram приходит отчёт с `success: false` после Approve.

```bash
docker -H ssh://user@vps-ip ps
```
Вероятная причина: `DOCKER_HOST` не экспортирован в окружении процесса агента, или SSH-ключ не подхватывается (агент запущен не тем пользователем, у которого настроен `~/.ssh/config` для VPS).

**4. Telegram-бот не отвечает совсем, `getUpdates` пуст**

Симптом: `long polling started` в логах есть, но callback от кнопок Approve/Reject не долетает.

Вероятная причина: `api.telegram.org` заблокирован/троттлится в твоём регионе (см. Шаг 4.4) — проверь `curl -v https://api.telegram.org` напрямую, при необходимости нужен прокси/VPN для исходящих запросов к Telegram (отдельно от WireGuard-туннеля к VPS).

**5. Alertmanager не может достучаться до агента, но с VPS всё выглядит нормально**

Симптом: `curl http://10.8.0.2:8080/health` с VPS зависает или таймаутит.

Вероятная причина: локальный firewall (ufw/Windows Defender/macOS Firewall) на самой рабочей машине блокирует входящие на `:8080` даже через интерфейс WireGuard — разреши явно для `wg0`/`utun` интерфейса.

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
- [Сеть: агент вне VPS](../docs/architecture/level-6.5-ai-agent/network.html) — WireGuard-туннель между VPS и локальной машиной, ufw закрывает 9090/3100 для интернета

**Теория сетей глубже:**
- [Webhook (ingress) vs вызов API (egress)](../docs/architecture/networking-theory/08-webhooks-and-egress.html) — почему это разные направления трафика с разными требованиями к firewall

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
