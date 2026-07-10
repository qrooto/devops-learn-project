# Уровень 6 — Observability: Prometheus + Grafana + Loki

> **Тип сессии:** разделы «Зачем», «Аналогия», «Как это работает», «На собеседовании спросят», Security Block — **[голова]**: можно читать в дороге, без терминала. Шаги с командами, «Что сломать намеренно», Troubleshooting на живой поломке — **[руки]**: нужна домашняя сессия с VM. Легенда — в START_HERE.md.

## Зачем начинать отсюда?

До этого мы видели проблемы только когда они уже случились: пользователи пишут что сайт не работает → идём смотреть логи. Это **реактивный** подход.

В production нужен **проактивный**: алерт в Telegram/Slack за 5 минут до того как пользователи начнут жаловаться. Видеть тренды: "latency растёт последние 30 минут, надо разобраться".

## Три кита observability

```
                    ┌─ Metrics (Prometheus + Grafana)
Observability ──────┤  "Сколько запросов? Какое время ответа? Сколько ошибок?"
                    │
                    ├─ Logs (Loki + Promtail + Grafana)
                    │  "Что именно происходило в 14:32:15?"
                    │
                    └─ Traces (OpenTelemetry — не строим, но знай)
                       "Как конкретный запрос прошёл через все сервисы?"
```

**Метрики** — числа во времени: RPS=150, latency_p95=120ms, errors=2%.
**Логи** — текстовые события: `2025-01-01 14:32:15 POST /api/ads 201 45ms`.
**Трейсы** — граф запроса: nginx (2ms) → backend (40ms) → postgres (35ms) → redis (1ms).

Без всего этого — ты слепой.

## Архитектура

```
                         scrape каждые 15с
Prometheus ─────────────────────────────→ backend_1/2/3 /metrics
           ─────────────────────────────→ cAdvisor /metrics (CPU/RAM контейнеров)
           ─────────────────────────────→ prometheus самого себя

Grafana ───────────→ Prometheus (метрики — PromQL запросы)
        ───────────→ Loki (логи — LogQL запросы)

Promtail ──────────→ читает /var/lib/docker/containers/*/*-json.log
         ──────────→ отправляет в Loki с метками {container="backend_1"}

Loki ──────────────→ хранит логи, индексирует по меткам
```

**Почему pull-модель (Prometheus сам ходит к сервисам)?**
Сервис не знает куда отправлять метрики — он просто экспонирует `/metrics`. Prometheus сам решает что и как часто скрапить. Легко добавить новый сервис в конфиг без изменения кода.

---

## Шаг 1 — Понять `/metrics` в бэкенде

```bash
# После запуска стека:
curl http://localhost/api/metrics | head -30
```

**Что увидишь:**
```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{handler="/api/ads",method="GET",status_code="200"} 142.0
http_requests_total{handler="/api/ads",method="POST",status_code="201"} 7.0
http_requests_total{handler="/api/ads",method="POST",status_code="401"} 2.0

# HELP http_request_duration_seconds HTTP request duration
# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.01"} 89.0
http_request_duration_seconds_bucket{le="0.025"} 134.0
```

**Типы метрик Prometheus:**
- **Counter** — только растёт (requests_total, errors_total). Для скорости: `rate(counter[5m])`
- **Gauge** — может падать и расти (memory_bytes, connections). Текущее значение.
- **Histogram** — распределение (latency). Позволяет считать percentile: p50, p95, p99.
- **Summary** — похож на Histogram, но percentile считается на стороне клиента.

---

## Шаг 2 — Запустить стек мониторинга

```bash
cd level-6-monitoring
docker compose up --build -d
docker compose ps
```

**Должны запуститься:**
```
NAME          PORTS
nginx         0.0.0.0:80->80/tcp
postgres
redis
backend_1     8000
backend_2     8000
backend_3     8000
prometheus    0.0.0.0:9090->9090/tcp
alertmanager  0.0.0.0:9093->9093/tcp
grafana       0.0.0.0:3000->3000/tcp
cadvisor      0.0.0.0:8080->8080/tcp
loki          3100
promtail
```

**Проверь что Prometheus видит все таргеты:**
```
http://localhost:9090/targets
```

Все targets должны быть `State: UP`. Если `DOWN` — смотри `Error` рядом.

---

## Шаг 3 — Изучить Prometheus UI и PromQL

Открой `http://localhost:9090`

**Основные PromQL запросы:**
```promql
# Запросов в секунду (за последнюю минуту):
sum(rate(http_requests_total[1m]))

# RPS по эндпоинтам:
sum(rate(http_requests_total[1m])) by (handler)

# Только ошибки 5xx:
sum(rate(http_requests_total{status_code=~"5.."}[1m]))

# Процент ошибок:
sum(rate(http_requests_total{status_code=~"5.."}[1m]))
/
sum(rate(http_requests_total[1m])) * 100

# Latency p95 (95% запросов выполняются быстрее этого):
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[1m])) by (le)
)

# CPU контейнеров (из cAdvisor):
rate(container_cpu_usage_seconds_total{name=~"backend.*"}[1m]) * 100

# RAM контейнеров:
container_memory_usage_bytes{name=~"backend.*"} / 1024 / 1024
```

**Понять `rate()` vs `irate()`:**
- `rate([5m])` — среднее за 5 минут (сглаживает пики)
- `irate([5m])` — последние 2 точки (видит пики лучше)

Для алертов — `rate()`. Для диагностики — `irate()`.

**Задание:** Напиши запрос который показывает RPS только для `GET /api/ads`.

---

## Шаг 4 — Grafana: готовый дашборд

```
http://localhost:3000
Логин: admin / Пароль: admin
```

Перейди в **Dashboards → Bulletin Board**. Готовый дашборд с 6 панелями:
- **RPS** — запросов в секунду
- **Latency p50/p95/p99** — время ответа по percentile
- **Error rate** — процент ошибок
- **CPU by container** — из cAdvisor
- **Memory by container** — из cAdvisor
- **RPS by endpoint** — какие эндпоинты загружены

---

## Шаг 5 — Наблюдать нагрузку в реальном времени

**Terминал 1** — держи Grafana открытой на дашборде (F5 каждые 5 секунд или включи Auto-refresh: кнопка в правом верхнем углу → `5s`)

**Терминал 2:**
```bash
k6 run ../level-2-scaling/load-tests/stress.js
```

**Что наблюдать в Grafana:**
1. RPS растёт по мере увеличения виртуальных пользователей
2. Latency p95 начинает расти при 50+ VU — это сигнал о перегрузке
3. CPU по контейнерам backend_1/2/3 распределяется равномерно
4. Redis CPU низкий — большинство запросов отдаётся из кэша

**Останови тест** — смотри как все метрики возвращаются к baseline.

---

## Шаг 6 — Симулировать сбой и видеть его на графиках

```bash
# Убьём один из бэкендов
docker compose stop backend_2
```

**В Grafana через несколько секунд увидишь:**
- RPS упал примерно на треть (один инстанс из трёх убран)
- Error rate кратковременно вырос (запросы которые уже шли на backend_2)
- CPU оставшихся бэкендов вырос — нагрузка перераспределилась

```bash
# Верни обратно
docker compose start backend_2
```

Grafana покажет recovery. Именно так в production выглядит инцидент на графике.

---

## Шаг 7 — Централизованные логи через Loki

Loki + Promtail читают логи всех Docker-контейнеров и индексируют по меткам.

**Открой Grafana → Explore (компас в левом меню)**

Выбери datasource **Loki**.

**LogQL запросы:**
```logql
# Все логи backend_1:
{container="level-6-monitoring-backend_1-1"}

# Только ошибки (поиск по тексту):
{container=~"backend.*"} |= "ERROR"

# Только 5xx ответы:
{container=~"backend.*"} |= " 5"

# Количество ошибок в минуту (метрика из логов):
sum(rate({container=~"backend.*"} |= "ERROR" [1m]))
```

**Почему Loki, а не ELK (Elasticsearch + Logstash + Kibana)?**
Loki не индексирует содержимое логов — только метки (container, namespace). Намного меньше ресурсов. Для полнотекстового поиска нужно `|=` (медленнее), но для большинства задач достаточно.

**Задание:** найди через Loki все запросы к `POST /api/auth/register` за последние 30 минут.

---

## Шаг 7.5 — Traces: третий кит observability

У нас есть метрики (Prometheus) и логи (Loki). Но иногда они не дают ответа. Пример:

`POST /api/ads` занимает 800ms. По метрикам — вырос p95. По логам — запрос выполнился. Но **где именно** эти 800ms? В бэкенде? В базе? В Redis? В сети?

Метрики не скажут. Логи разбросаны по контейнерам. **Трейс** скажет:

```
Request: POST /api/ads  total: 800ms
├── nginx: proxy                   2ms
├── backend: JWT verify            5ms
├── backend: db connection pool  320ms  ← ВОТ ОНО
│   └── postgres: INSERT ads      315ms
└── backend: redis DEL ads:list    1ms
```

Без трейсинга ты бы смотрел на 800ms и гадал. С трейсингом — сразу видишь: 315ms в INSERT, нужен индекс или PgBouncer.

### Что такое трейс и спан

**Трейс** — граф прохождения одного запроса через все сервисы.
**Спан (span)** — один именованный шаг внутри трейса: имя операции, начало, конец, теги, статус.

```
trace_id: a7f3c2b1-...
  span: HTTP POST /api/ads          0-800ms
  ├── span: jwt.verify              5-10ms
  ├── span: db.acquire_connection   10-330ms  ← connection pool exhausted!
  │     └── span: pg.INSERT ads     330-645ms
  └── span: redis.DEL               645-646ms
```

Спаны вкладываются образуя дерево. Корневой спан — весь запрос, дочерние — отдельные операции.

### Correlation ID: трейсинг без инфраструктуры

Полный трейсинг (Jaeger, Tempo) требует инструментации кода и дополнительных сервисов. Но есть простой первый шаг — **Correlation ID**.

Идея: каждому запросу присваиваем уникальный ID. Этот ID логируется везде — в nginx, в бэкенде, в PostgreSQL. Теперь по ID можно собрать все логи одного запроса:

```
nginx:    [a7f3c2b1] POST /api/ads 800ms
backend:  [a7f3c2b1] JWT verified user_id=1
backend:  [a7f3c2b1] DB query start
postgres: [a7f3c2b1] INSERT duration=315ms
backend:  [a7f3c2b1] Cache invalidated
```

### Практика

**Шаг 1 — Наблюдать логи без correlation ID**

```bash
# Делаем несколько параллельных запросов:
for i in $(seq 1 5); do
  curl -s http://localhost/api/ads > /dev/null &
done
wait

# Смотрим логи:
docker compose logs --tail=30 backend_1 backend_2 backend_3
```

Видишь логи от разных запросов вперемешку. Непонятно какая строка от какого запроса.

**Шаг 2 — Добавить X-Request-ID через Nginx**

Nginx умеет генерировать уникальный ID для каждого запроса. Открой `nginx/nginx.conf`:

```bash
grep -n "request_id\|X-Request" nginx/nginx.conf
```

Если есть — хорошо. Если нет — добавь в секцию `http {}`:

```nginx
http {
    # Генерировать уникальный ID для каждого запроса:
    map $http_x_request_id $req_id {
        default $http_x_request_id;
        ""      $request_id;      # если клиент не передал — генерируем сами
    }

    # Передавать ID в бэкенд:
    proxy_set_header X-Request-ID $req_id;

    # Включить в лог-формат:
    log_format main '$remote_addr - $req_id "$request" $status $body_bytes_sent';
    access_log /var/log/nginx/access.log main;

    # Возвращать клиенту:
    add_header X-Request-ID $req_id always;
}
```

```bash
docker compose restart nginx
```

**Шаг 3 — Проверить что ID передаётся**

```bash
# Видим X-Request-ID в ответе:
curl -sv http://localhost/api/ads 2>&1 | grep -i "x-request-id"
# < X-Request-ID: 4d3a2b1c...

# Передаём свой ID (для тестирования):
curl -H "X-Request-ID: my-debug-123" http://localhost/api/ads
# Nginx вернёт этот же ID в ответе
```

**Шаг 4 — Найти запрос в Loki по Request ID**

```bash
# Берём ID из ответа:
REQ_ID=$(curl -sI http://localhost/api/ads | grep -i x-request-id | awk '{print $2}' | tr -d '\r')
echo "Looking for: $REQ_ID"
```

В Grafana → Explore → Loki:
```logql
{container=~".*backend.*"} |= "$REQ_ID"
```

Видишь все логи именно этого запроса от всех бэкендов.

**Шаг 5 — Понять полный стек distributed tracing**

Correlation ID — это ручной трейсинг. Полноценный автоматический трейсинг строится на:

```
FastAPI (код) ──→ OpenTelemetry SDK ──→ OTLP protocol ──→ Tempo (хранилище)
                                                                ↓
                                                    Grafana Traces UI
```

**OpenTelemetry (OTel)** — vendor-neutral стандарт для метрик, логов и трейсов. Инструментируешь код один раз → отправляешь в любой backend (Jaeger, Tempo, Datadog, New Relic). Устанавливается как библиотека:

```bash
pip install opentelemetry-distro opentelemetry-instrumentation-fastapi opentelemetry-exporter-otlp
```

После этого FastAPI автоматически создаёт спан для каждого HTTP-запроса — без ручного кода.

**Tempo** — хранилище трейсов от Grafana Labs. Добавляется в `docker-compose.yml` как ещё один сервис.

**Grafana correlation** — главная сила observability: кликаешь на спайк latency на дашборде → переходишь в логи этого времени → из логов переходишь к трейсу → видишь где именно потеря. Всё в одном инструменте.

```
Grafana (Prometheus метрики)
    ↓ спайк p95 в 14:32 — кликаешь
Loki (логи этого периода)
    ↓ видишь request_id медленного запроса
Tempo (трейс этого request_id)
    ↓ postgres.INSERT = 800ms → нет индекса!
```

**Для самостоятельного изучения (не строим в курсе, но понять нужно):**

```yaml
# Добавить в docker-compose.yml:
tempo:
  image: grafana/tempo:latest
  command: ["-config.file=/etc/tempo/tempo.yml"]
  volumes:
    - ./tempo/tempo.yml:/etc/tempo/tempo.yml

# В backend — инструментация FastAPI:
# opentelemetry-instrument --traces_exporter otlp \
#   --exporter-otlp-endpoint http://tempo:4317 \
#   uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## Шаг 8 — Алерты: Prometheus + Alertmanager

Алертинг состоит из двух ролей:
- **Prometheus** вычисляет алерты — правила лежат в `prometheus/alerts.yml` (BackendDown, HighErrorRate, HighLatency)
- **Alertmanager** доставляет их — группирует, подавляет дубликаты, шлёт получателям; конфиг в `alertmanager/alertmanager.yml`

Оба уже подключены в `docker-compose.yml` (сервис `alertmanager`, порт 9093) и в `prometheus.yml` (секции `rule_files` и `alerting`). Открой все три файла и разбери каждую строку — комментарии внутри.

```bash
# Убедись что всё поднялось:
docker compose up -d
curl -s localhost:9093/-/healthy   # Alertmanager отвечает

# Алерты в Prometheus (состояния: inactive / pending / firing):
# http://localhost:9090/alerts
# Что дошло до Alertmanager:
# http://localhost:9093
```

**Симулируй алерт:**
```bash
docker compose stop backend_1 backend_2 backend_3
# Подожди 30 секунд — алерт BackendDown: pending → firing
# http://localhost:9090/alerts  → firing
# http://localhost:9093         → алерт доехал до Alertmanager
docker compose start backend_1 backend_2 backend_3
# Ещё через минуту алерт погаснет (resolved)
```

Пока receiver в Alertmanager — заглушка (`default` без каналов): алерты видны в UI, но никуда не отправляются. Реальные каналы — Шаг 9 (Telegram) и уровень 6.5 (webhook AI-агенту).

---

## Шаг 9 — Алерт в Telegram (опционально)

```bash
# Создать Telegram бота:
# 1. Откройте Telegram → @BotFather → /newbot
# 2. Получи bot_token
# 3. Напиши боту любое сообщение
# 4. Получи chat_id:
#    curl https://api.telegram.org/bot<TOKEN>/getUpdates
```

Alertmanager уже запущен — добавь receiver в `alertmanager/alertmanager.yml`:

```yaml
route:
  receiver: telegram   # было: default

receivers:
  - name: telegram
    telegram_configs:
      - bot_token: "ВАШ_BOT_TOKEN"   # 🔒 секрет! не коммить в Git (см. Security Block)
        chat_id: ВАШ_CHAT_ID
        message: "{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}"
```

```bash
docker compose restart alertmanager
```

---

## Шаг 10 — Остановить

```bash
docker compose down
docker compose down -v  # удалить volumes (данные)
```

---

## Типичные ошибки

**Prometheus Target "DOWN"** → Проверь что бэкенд доступен по адресу указанному в prometheus.yml. Внутри Docker-сети имена контейнеров — это DNS. `backend_1:8000`, не `localhost:8000`.

**Grafana "No data"** → Проверь datasource: Grafana → Connections → Data sources → Test. Если Prometheus не отвечает — проверь что он поднят.

**Loki "No logs found"** → Promtail нужен доступ к `/var/lib/docker/containers`. В docker-compose.yml должен быть volume mount: `- /var/lib/docker/containers:/var/lib/docker/containers:ro`.

**Алерты не приходят** → Нужен Alertmanager. Prometheus только создаёт алерты, Alertmanager их маршрутизирует (Telegram, Slack, PagerDuty).

---

## На собеседовании спросят

**Q: Что такое observability и чем она отличается от мониторинга?**
A: Мониторинг — ты заранее знаешь что проверять (uptim, CPU). Observability — система позволяет ответить на любой вопрос о её состоянии с помощью метрик, логов и трейсов. Можно найти причину проблемы которую ты не предвидел.

**Q: Почему p95 latency важнее среднего?**
A: Среднее маскирует хвост. Если 100 запросов заняли 10ms и 1 запрос — 1000ms, среднее = 19ms, а p95 = 1000ms. Реальный пользователь в 5% случаев ждёт секунду — это видно только в percentile.

**Q: Что такое "cardinality" в Prometheus и почему это проблема?**
A: Количество уникальных комбинаций label. Если в метрику добавить label `user_id` — для 1 миллиона пользователей будет 1 миллион time series. Prometheus хранит все в памяти — OOM. Никогда не добавляй в labels неограниченные значения (user_id, request_id).

**Q: Чем Loki отличается от Elasticsearch?**
A: Elasticsearch индексирует всё содержимое логов — полнотекстовый поиск быстрый, но требует много дискового и RAM. Loki индексирует только labels (container, job) — поиск по тексту медленнее (перебирает файлы), зато в 10x меньше ресурсов.

**Q: Что такое pull vs push в мониторинге?**
A: Pull (Prometheus): сервер мониторинга сам обходит таргеты. Прозрачно, легко добавить service discovery, таргеты не знают где Prometheus. Push (Graphite, InfluxDB): сервисы сами отправляют метрики. Лучше работает через firewall, проще для короткоживущих задач.

**Q: Что такое distributed tracing и чем он отличается от логов?**
A: Логи — события от одного сервиса в текстовом виде, разрозненные. Трейс — граф прохождения конкретного запроса через все сервисы с временем каждого шага (span). Логи отвечают на "что случилось в сервисе X", трейс — "где именно потеряно время по всей цепочке". Без трейсинга найти bottleneck в многосервисной архитектуре занимает часы; с трейсингом — секунды.

**Q: Что такое OpenTelemetry и зачем он нужен?**
A: Vendor-neutral стандарт и SDK для сбора метрик, логов и трейсов. Инструментируешь код один раз через OTel API → данные можно отправить в любой backend: Jaeger, Tempo, Datadog, New Relic. Без OTel каждый vendor требует свой SDK — при смене инструмента переписывать весь код.

**Q: Что такое Correlation ID и зачем он нужен?**
A: Уникальный ID запроса который передаётся через все сервисы и пишется в каждый лог. Без него логи от разных сервисов не связаны — непонятно какие строки относятся к одному запросу. С correlation ID: `{container=~".*"} |= "a7f3c2b1"` в Loki покажет весь путь запроса по всем сервисам.

---

## Итог уровня 6 — что ты умеешь

- [ ] Запустить стек Prometheus + Grafana + Loki + Promtail + cAdvisor
- [ ] Писать PromQL: rate, histogram_quantile, by, label matcher
- [ ] Читать готовый Grafana-дашборд и создавать новые панели
- [ ] Искать логи в Loki через LogQL
- [ ] Написать alerting rule в Prometheus
- [ ] Симулировать инцидент и наблюдать его на графиках
- [ ] Объяснить разницу counter/gauge/histogram

**Следующий шаг:** упаковать всё в Helm-чарт чтобы деплоить в K8s одной командой → Уровень 7.

---

## Коммит

```bash
cd ..
git add level-6-monitoring/
git commit -m "level-6: prometheus + grafana + loki full observability stack"
git push origin main
```

---

## Security Block: Уровень 6

### Мониторинг — новая поверхность атаки

Инструменты observability сами по себе содержат чувствительную информацию о системе и требуют защиты.

**1. Grafana с дефолтным паролем `admin/admin`**

Grafana открыта на порту 3000. Если сервер публичный — Grafana доступна всему интернету с паролем по умолчанию. Атакующий видит все метрики, RPS, эндпоинты, топологию системы.

```bash
# Сменить пароль сразу после запуска:
# http://localhost:3000 → Admin → Change password

# Или через переменную окружения в docker-compose.yml:
grafana:
  environment:
    - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_PASSWORD}
    - GF_SECURITY_ADMIN_USER=admin
    - GF_USERS_ALLOW_SIGN_UP=false   # запретить регистрацию новых пользователей
```

**2. Prometheus не должен быть публично доступен**

`http://server-ip:9090` — это полный доступ ко всем метрикам, конфигурации таргетов, и возможность выполнять произвольные PromQL-запросы. В docker-compose.yml мы пробрасываем порт 9090 только для учёбы (доступ с localhost).

В production Prometheus не имеет публичного порта — Grafana подключается к нему изнутри Docker-сети:
```yaml
# НЕ делай в production:
prometheus:
  ports:
    - "9090:9090"  # убрать

# Grafana подключается через внутреннее имя:
# http://prometheus:9090
```

Как реально закрыть эти порты через ufw (а не просто убрать из docker-compose) и при этом дать доступ AI-агенту с локальной машины через WireGuard-туннель — см. Level 6.5, Шаг 4.

**3. Loki читает логи контейнеров — что туда попадает**

Promtail читает все Docker-логи. Если приложение логирует пароли, токены, персональные данные — они попадают в Loki и будут храниться там. Проверяй что логируешь.

```python
# Плохо — пароль в логах:
logger.info(f"User login attempt: {username} / {password}")

# Хорошо:
logger.info(f"User login attempt: {username}")
```

**4. Alertmanager Telegram token — это секрет**

`bot_token` для Telegram в alertmanager.yml — это секрет. Не коммить его в git. Используй переменную окружения:

```yaml
# alertmanager.yml:
telegram_configs:
  - bot_token: "{{ .Env.TELEGRAM_BOT_TOKEN }}"
```

**5. Метрики могут раскрыть структуру системы**

Эндпоинт `/metrics` публично доступен в нашей конфигурации (через nginx). Метрики содержат: имена эндпоинтов, коды ответов, внутренние имена. В production `/metrics` должен быть доступен только для Prometheus, не для внешних пользователей.

```nginx
# В nginx.conf — запретить внешний доступ к /metrics:
location /metrics {
    deny all;
    return 403;
}
```

⚠️ **Антипаттерны:**

- **Grafana с дефолтным паролем в production** — это один из первых паролей которые пробуют при атаке на инфраструктуру. Всегда меняй сразу при первом запуске.
- **Логировать чувствительные данные** — пароли, токены, номера карт в логах. Loki будет хранить это годами. Правило: никогда не логировать то что не хочешь видеть на экране у незнакомца.

---

## Best Practices Checklist

- [ ] Grafana пароль изменён с `admin/admin`
- [ ] `GF_USERS_ALLOW_SIGN_UP=false` — регистрация новых пользователей запрещена
- [ ] `/metrics` эндпоинт недоступен внешним пользователям через nginx
- [ ] Prometheus не имеет публичного порта (только для локальной отладки)
- [ ] Алерт `BackendDown` настроен и протестирован
- [ ] Telegram bot_token не захардкожен в файле конфига
- [ ] В логах нет паролей и токенов — проверь `{container=~"backend.*"} |= "password"` в Loki
- [ ] X-Request-ID передаётся через Nginx — можешь найти конкретный запрос в Loki по его ID
- [ ] Понимаешь три кита observability: metrics / logs / traces — и когда каждый из них нужен

---

## Troubleshooting: Уровень 6

### Проблемы с мониторингом

**1. Prometheus Target показывает `DOWN`**

Симптом: `http://localhost:9090/targets` — один или несколько таргетов красные.

```bash
# Смотрим детальную ошибку рядом с DOWN-таргетом на странице /targets
# Или в логах Prometheus:
docker compose logs prometheus | grep -E "error|failed|unreachable"

# Проверяем что бэкенд отвечает на /metrics изнутри сети:
docker compose exec prometheus curl -s http://backend_1:8000/metrics | head -5

# Частые причины:
# - Неверное имя контейнера в prometheus.yml (имя изменилось)
# - Бэкенд не экспортирует /metrics (нет prometheus_client в коде)
# - Сетевая изоляция (Prometheus в другой Docker-сети)

# Проверить конфиг prometheus.yml:
docker compose exec prometheus cat /etc/prometheus/prometheus.yml
```

**2. Grafana "No data" на дашборде**

Симптом: открываешь дашборд, все панели пустые.

```bash
# Шаг 1: проверить datasource
# Grafana → Connections → Data sources → Prometheus → Save & Test
# Должно быть "Data source is working"

# Если ошибка подключения к Prometheus:
docker compose exec grafana curl -s http://prometheus:9090/-/healthy
# Если нет ответа — Prometheus не запущен или другое имя в docker-compose

# Шаг 2: проверить что есть данные в Prometheus
# http://localhost:9090 → Graph → введи: up
# Должны быть точки на графике

# Шаг 3: проверить временной диапазон в Grafana
# Правый верхний угол → "Last 15 minutes" → убедись что данные за этот период есть
```

**3. Loki: "No logs found" в Grafana**

Симптом: Explore → Loki → запрос → пустой результат.

```bash
# Проверяем что Promtail работает:
docker compose logs promtail | tail -20
# Ищи "Successfully sent batch" или ошибки

# Проверяем что Loki принимает логи:
docker compose logs loki | grep -E "error|level=error"

# Promtail читает Docker-логи через volume mount:
docker compose exec promtail ls /var/lib/docker/containers/ | head -5
# Если пусто — volume не примонтирован, проверь docker-compose.yml

# Проверяем через API что в Loki есть потоки:
curl -s http://localhost:3100/loki/api/v1/labels | python3 -m json.tool

# Правильный LogQL запрос (имена контейнеров включают compose prefix):
# {container="level-6-monitoring-backend_1-1"}
# не просто {container="backend_1"}
docker ps --format '{{.Names}}' | grep backend
```

**4. Алерты в состоянии `Pending` но не переходят в `Firing`**

Симптом: в Prometheus `/alerts` видишь алерт в `Pending`, но он не становится `Firing`.

```bash
# Pending → Firing: алерт должен быть активен дольше чем "for:" в правиле
# Если for: 1m — алерт станет Firing через 1 минуту после появления

# Проверяем правило:
curl -s http://localhost:9090/api/v1/rules | python3 -m json.tool | grep -A 10 "HighErrorRate"

# Проверяем что выражение возвращает данные:
# В Prometheus UI вбей выражение из "expr:" напрямую
# Если ничего не возвращает — выражение не срабатывает

# Частая ошибка: labels не совпадают
# status_code="5xx" vs status_code=~"5.." — первое не сработает
```

**5. Высокое потребление RAM у Prometheus**

Симптом: `docker stats` показывает Prometheus потребляет несколько GB.

```bash
# Смотрим количество time series:
curl -s http://localhost:9090/api/v1/query?query=prometheus_tsdb_head_series | python3 -m json.tool
# Более 1 миллиона — высокая cardinality, нужно оптимизировать

# Найти метрики с высокой cardinality:
curl -s "http://localhost:9090/api/v1/query?query=topk(10,count by (__name__)({__name__!=\"\"}))" | python3 -m json.tool

# Настроить retention (хранить только 15 дней вместо default 15d):
# В docker-compose.yml:
# command: --storage.tsdb.retention.time=7d --storage.tsdb.retention.size=1GB
```

---

## Архитектура

- [Концепция: pull-based мониторинг в вакууме](../docs/architecture/level-6-monitoring/concept.html) — почему сервер метрик сам приходит за данными, а не наоборот
- [Реализация: реальный docker-compose.yml](../docs/architecture/level-6-monitoring/implementation.html) — Prometheus scrape, Grafana, Loki/Promtail
- [Боль → решение: Level 5 → Level 6](../docs/architecture/level-6-monitoring/pain-solution.html) — от слепоты между инцидентами к видимым трендам
- [Сеть: антипаттерн этого конфига](../docs/architecture/level-6-monitoring/network.html) — 4 новых published-порта без аутентификации и захардкоженный пароль Grafana

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
