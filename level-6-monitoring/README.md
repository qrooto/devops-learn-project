# Уровень 6 — Observability: Prometheus + Grafana + Loki

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

## Шаг 8 — Написать алерт в Prometheus

```bash
# Создать файл с правилами алертов:
cat > level-6-monitoring/prometheus/alerts.yml << 'EOF'
groups:
  - name: bulletin-board
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status_code=~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m])) * 100 > 5
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "Error rate выше 5%"
          description: "Текущий error rate: {{ $value | printf \"%.1f\" }}%"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          ) > 1.0
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "p95 latency выше 1 секунды"

      - alert: BackendDown
        expr: up{job=~"backend.*"} == 0
        for: 30s
        labels:
          severity: critical
        annotations:
          summary: "Бэкенд {{ $labels.job }} недоступен"
EOF
```

Добавь в `prometheus/prometheus.yml`:
```yaml
rule_files:
  - /etc/prometheus/alerts.yml
```

```bash
docker compose restart prometheus

# Посмотреть алерты:
# http://localhost:9090/alerts
```

**Симулируй алерт:**
```bash
docker compose stop backend_1 backend_2 backend_3
# Подожди 30 секунд — алерт BackendDown должен перейти в Firing
# http://localhost:9090/alerts
docker compose start backend_1 backend_2 backend_3
```

---

## Шаг 9 — Алерт в Telegram (опционально)

```bash
# Создать Telegram бота:
# 1. Откройте Telegram → @BotFather → /newbot
# 2. Получи bot_token
# 3. Напиши боту любое сообщение
# 4. Получи chat_id:
#    curl https://api.telegram.org/bot<TOKEN>/getUpdates

# Добавь Alertmanager в docker-compose.yml:
# image: prom/alertmanager
# volumes:
#   - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
```

```yaml
# alertmanager/alertmanager.yml:
route:
  receiver: telegram

receivers:
  - name: telegram
    telegram_configs:
      - bot_token: "ВАШ_BOT_TOKEN"
        chat_id: ВАШ_CHAT_ID
        message: "{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}"
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
