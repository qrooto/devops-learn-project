# Уровень 2 — Горизонтальное масштабирование

## Зачем начинать отсюда?

На уровне 1 ты видел: один Python-процесс не справляется при 50+ concurrent users. Время ответа растёт, появляются 502. Очевидное решение — запустить несколько копий бэкенда.

Это называется **горизонтальное масштабирование (scale out)** — добавляем инстансы, а не мощность.
В отличие от **вертикального (scale up)** — взять сервер помощнее, что дорого и имеет физический предел.

**Важный урок этого уровня:** горизонтальное масштабирование бесплатным не бывает. Оно вскрывает архитектурные проблемы которые в монолите не были видны.

## Аналогия

Один повар не справляется — нанимаем трёх поваров.
Но теперь нужен метрдотель (Nginx) который распределяет заказы.
И у каждого повара своя голова — если повар 2 запомнил что клиент Иван хочет без лука, а заказ пришёл к повару 3 — он этого не знает.

Это и есть проблема **stateful** приложений при масштабировании.

## Архитектура

```
Браузер
    │
    └── HTTP :80 ──→ Nginx (балансировщик)
                        │
                        ├── upstream backend
                        │       ├── backend_1:8000  ← отдельный процесс
                        │       ├── backend_2:8000  ← отдельный процесс
                        │       └── backend_3:8000  ← отдельный процесс
                        │               │
                        │         PostgreSQL :5432 (ОБЩАЯ для всех)
                        │
                        └── static files → /frontend/
```

**Почему PostgreSQL одна?** Данные должны быть консистентны — нельзя чтобы объявление видели на одном инстансе и не видели на другом.

**Что изменилось в nginx.conf:**
```nginx
upstream backend {
    server backend_1:8000;
    server backend_2:8000;
    server backend_3:8000;
    # round-robin: каждый следующий запрос → следующий сервер
}
```

**Что изменилось в docker-compose.yml:**
- Три сервиса `backend_1`, `backend_2`, `backend_3` вместо одного `backend`
- `SECRET_KEY` — один для всех (иначе JWT подписанный на backend_1 не пройдёт проверку на backend_2)

---

## Шаг 1 — Разобрать конфигурацию (не запускать)

```bash
cat nginx/nginx.conf
```

**Найди и ответь:**
1. Что делает директива `proxy_next_upstream error timeout`? (Подсказка: что происходит если backend_2 упал прямо во время запроса?)
2. Почему `keepalive 32` в upstream — хорошая идея?
3. Почему `SECRET_KEY` должен быть **одинаковым** на всех инстансах?

---

## Шаг 2 — Запустить

```bash
cd level-2-scaling
docker compose up --build -d
docker compose ps
```

**Что должны увидеть:** 5 контейнеров со статусом `Up` — nginx, postgres, backend_1, backend_2, backend_3.

```
NAME          STATUS        PORTS
nginx         Up            0.0.0.0:80->80/tcp
postgres      Up (healthy)
backend_1     Up
backend_2     Up
backend_3     Up
```

**Логи** — убедись что миграции отработали:
```bash
docker compose logs backend_1 | head -20
# Running database migrations...
# INFO  [alembic.runtime.migration] Running upgrade -> 001, Initial schema
# Starting server...
```

---

## Шаг 3 — Убедиться что балансировка работает

```bash
# Запусти 9 запросов подряд — увидишь 3 разных hostname
for i in $(seq 1 9); do
  curl -s http://localhost/api/instance | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['instance_id'])"
done
```

**Что увидишь:**
```
level-2-scaling-backend_1-1
level-2-scaling-backend_2-1
level-2-scaling-backend_3-1
level-2-scaling-backend_1-1
level-2-scaling-backend_2-1
...
```

Nginx распределяет запросы по кругу (round-robin). Клиент этого не видит — ему кажется что он общается с одним сервером.

**Теперь посмотри на счётчик:**
```bash
for i in $(seq 1 6); do curl -s http://localhost/api/instance; echo; done
```

```json
{"instance_id": "backend_1", "request_count_on_this_instance": 1, ...}
{"instance_id": "backend_2", "request_count_on_this_instance": 1, ...}
{"instance_id": "backend_3", "request_count_on_this_instance": 1, ...}
{"instance_id": "backend_1", "request_count_on_this_instance": 2, ...}
```

**Ключевое наблюдение:** каждый инстанс считает свои запросы независимо. Если бы вместо этого счётчика здесь хранились **сессии пользователей** (в памяти) — каждый третий запрос уходил бы на "незнакомый" инстанс и пользователя выкидывало бы из системы.

**Почему JWT решает эту проблему:** токен содержит всю информацию о пользователе и подписан `SECRET_KEY`, который одинаков на всех инстансах. Любой бэкенд может проверить токен без обращения к общему хранилищу.

---

## Шаг 4 — Зарегистрироваться и создать объявление

Убедись что JWT работает корректно при балансировке:

```bash
# Зарегистрироваться
curl -s -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","password":"pass123","email":"bob@test.com"}' | python3 -m json.tool

# Залогиниться — токен может быть проверен ЛЮБЫМ из 3 инстансов
TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"bob","password":"pass123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Создать объявление 3 раза — каждый раз на другой инстанс
for i in 1 2 3; do
  curl -s -X POST http://localhost/api/ads \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"title\":\"Объявление $i\",\"description\":\"Тест\",\"price\":$((i*100))}" | python3 -m json.tool
done
```

**Что должно произойти:** все три объявления создались успешно — JWT проверялся на разных инстансах, но всё работает, потому что SECRET_KEY одинаковый.

---

## Шаг 5 — Убить контейнер во время нагрузки

Это ключевая демонстрация отказоустойчивости.

**Терминал 1** — запусти нагрузочный тест:
```bash
k6 run load-tests/balancer-test.js
```

**Терминал 2** — пока тест работает, убей backend_2:
```bash
docker compose stop backend_2
```

**Что наблюдать в Терминале 1:**
- Кратковременный всплеск ошибок (1-2 секунды)
- Затем всё нормализуется — Nginx перестал отправлять запросы на упавший инстанс

**Почему Nginx так быстро реагирует?**
Директива `proxy_next_upstream error timeout` говорит: "если получил ошибку от backend_2 — отправь тот же запрос на следующий доступный сервер". Клиент этого не заметит.

**Верни контейнер:**
```bash
docker compose start backend_2
```

После запуска Nginx автоматически начнёт слать на него запросы снова.

---

## Шаг 6 — Стресс-тест и сравнение с уровнем 1

```bash
# Два терминала одновременно:
# Терминал 1:
docker stats

# Терминал 2:
k6 run load-tests/stress.js
```

**Что наблюдать в docker stats:**
- Нагрузка CPU **распределяется** между backend_1, backend_2, backend_3
- PostgreSQL CPU растёт — он один на всех

**Что наблюдать в k6:**
- При 100 VU время ответа значительно лучше чем в уровне 1
- Но при очень высокой нагрузке — всё равно деградирует

**Почему деградирует несмотря на три инстанса?**
Каждый запрос `GET /api/ads` всё равно идёт в PostgreSQL. При трёх инстансах = в три раза больше запросов к базе. PostgreSQL один — он становится новым ботлнеком.

Это и есть боль которую мы решаем на уровне 3.

---

## Шаг 7 — Логи и диагностика

```bash
# Только ошибки:
docker compose logs backend_1 backend_2 backend_3 | grep -i error

# Посмотреть что происходит с конкретным инстансом:
docker compose exec backend_1 ps aux
docker compose exec backend_1 free -h

# Проверить сколько коннектов к БД от каждого инстанса:
docker compose exec postgres psql -U postgres -d bulletin_board \
  -c "SELECT count(*), state FROM pg_stat_activity GROUP BY state;"
```

**Что ожидать:** до 5 active connections от каждого инстанса (pool_size=5). Всего до 15 соединений к PostgreSQL.

---

## Шаг 8 — Остановить

```bash
docker compose down

# Чистый старт (удалить данные):
docker compose down -v
```

---

## Типичные ошибки

**"connection refused" у backend_2 при первом старте** → PostgreSQL стартует дольше чем кажется. Подожди — entrypoint.sh ретраит 10 раз.

**JWT Invalid/Expired при запросах** → Проверь что `SECRET_KEY` в docker-compose.yml одинаковый для всех трёх backend-сервисов. Если они разные — токен выданный backend_1 не будет принят backend_2.

**Некоторые объявления не появляются** → Этого не должно происходить, но если кажется что так — обнови страницу. У нас нет кэша ещё, каждый запрос идёт в БД.

**`proxy_next_upstream` пересылает POST-запрос на другой инстанс** → Осторожно: у нас настроено `non_idempotent` для демонстрации. В production для POST это опасно — запрос может выполниться дважды.

---

## На собеседовании спросят

**Q: В чём разница между горизонтальным и вертикальным масштабированием?**
A: Вертикальное (scale up) — добавить CPU/RAM существующему серверу. Ограничено железом, дорого. Горизонтальное (scale out) — добавить новые инстансы. Теоретически неограниченно, требует stateless архитектуры.

**Q: Что такое stateless архитектура и почему она важна?**
A: Stateless — каждый запрос содержит всю необходимую информацию, сервер не хранит состояние между запросами. JWT — stateless auth. Session cookie — stateful (сервер должен помнить сессию). Stateless можно масштабировать горизонтально без проблем.

**Q: Как Nginx определяет что бэкенд упал?**
A: passive health check: если бэкенд вернул ошибку или не ответил — Nginx помечает его как unavailable на `fail_timeout` (по умолчанию 10s). Есть также active health check (проверяет `/health` регулярно) — только в NGINX Plus или с модулем.

**Q: Какой алгоритм балансировки используется по умолчанию в Nginx?**
A: Round-robin — каждый следующий запрос на следующий сервер. Альтернативы: `least_conn` (на наименее загруженный), `ip_hash` (один клиент всегда на один сервер — нужно для stateful сессий), `random`.

**Q: Почему SECRET_KEY должен быть одинаковым на всех инстансах?**
A: JWT — это подписанный токен. Подпись проверяется с тем же ключом которым создавалась. Если инстансы имеют разные ключи — токен созданный на instance_1 будет отклонён instance_2 с "Invalid signature".

---

## Итог уровня 2 — что ты умеешь

- [ ] Настроить Nginx upstream с несколькими серверами
- [ ] Запустить несколько инстансов одного сервиса через docker-compose
- [ ] Убить контейнер под нагрузкой и наблюдать автоматический failover
- [ ] Объяснить почему JWT работает при scale-out а сессии в памяти — нет
- [ ] Найти новое узкое место (PostgreSQL) после решения старого (один бэкенд)

**Боль уровня 2:** каждый GET /api/ads = запрос в PostgreSQL. При N инстансах N×нагрузка на базу → Уровень 3: кэширование.

---

## Коммит

```bash
cd ..
git add level-2-scaling/
git commit -m "level-2: horizontal scaling with nginx load balancer"
git push origin main
```

---

## Security Block: Уровень 2

### Что важно при масштабировании

**1. Единый SECRET_KEY для всех инстансов**

Это одновременно и техническая необходимость, и security-момент. `SECRET_KEY` одинаковый — хорошо для JWT. Но это значит что если скомпрометировать любой один инстанс и достать переменную окружения — ты знаешь ключ для подделки токенов всех пользователей.

В production `SECRET_KEY` берётся из secrets manager (Vault, AWS Secrets Manager), не хранится в `docker-compose.yml`.

**2. PostgreSQL по-прежнему недоступен снаружи**

При масштабировании соблазн открыть порт postgres "для удобства диагностики". Не делай этого. Диагностируй через `docker compose exec postgres psql ...` — он работает изнутри Docker-сети без проброса порта.

**3. Изоляция сетей**

В идеале backend и postgres должны быть в разных Docker-сетях: backend → внешняя сеть → может принимать трафик из nginx. postgres → только внутренняя сеть → доступен только backend. В нашем `docker-compose.yml` все сервисы в одной сети — это нормально для учёбы.

**4. `proxy_next_upstream non_idempotent` — осторожно**

В учебных целях мы разрешили Nginx пересылать POST-запросы на следующий инстанс при ошибке. В production это опасно: POST-запрос (создание объявления) может выполниться дважды. Для идемпотентных запросов (GET) — безопасно. Для POST/PUT — только если у тебя есть защита от дублирования.

**5. Rate limiting в Nginx**

На этом уровне его нет. В production Nginx должен ограничивать количество запросов с одного IP чтобы защититься от DoS и брутфорса:

```nginx
# Пример rate limiting (добавить в будущем):
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;
limit_req zone=api burst=20 nodelay;
```

⚠️ **Антипаттерны:**

- **Разные SECRET_KEY на инстансах** — пользователи будут случайно получать 401 при каждом третьем запросе (когда попадают на "чужой" инстанс). Трудно дебажить потому что ошибка нестабильная.
- **Пробросить порт PostgreSQL для "удобства"** (`ports: "5432:5432"` в docker-compose) — база становится доступна всему интернету на IP-адресе сервера.

---

## Best Practices Checklist

- [ ] `SECRET_KEY` одинаковый для всех трёх инстансов — создание токена на одном, проверка на другом работает
- [ ] PostgreSQL порт не пробрасывается на хост
- [ ] `healthcheck` в postgres-сервисе настроен — `docker compose ps` показывает `(healthy)`
- [ ] `proxy_next_upstream` настроен — Nginx переключается при падении инстанса
- [ ] Все три инстанса видны в `docker compose ps` как `Up`
- [ ] Убил один инстанс во время нагрузки — сервис продолжил работу

---

## Troubleshooting: Уровень 2

### Проблемы с балансировкой и несколькими инстансами

**1. Все запросы идут на один инстанс**

Симптом: `curl http://localhost/api/instance` всегда возвращает один и тот же `instance_id`.

```bash
# Проверяем upstream в конфиге:
cat nginx/nginx.conf | grep -A 10 "upstream"

# Проверяем что все три инстанса запущены:
docker compose ps

# Смотрим логи nginx на предмет ошибок upstream:
docker compose logs nginx | grep -E "upstream|error|failed"

# Если инстанс помечен как unavailable — перезапусти его:
docker compose restart backend_2
```

**2. JWT ошибка: `Invalid signature` или `Could not validate credentials`**

Симптом: логинишься, получаешь токен, следующий запрос (на другой инстанс) даёт 401.

```bash
# Это почти всегда разные SECRET_KEY
# Проверяем значения у всех инстансов:
docker compose exec backend_1 env | grep SECRET_KEY
docker compose exec backend_2 env | grep SECRET_KEY
docker compose exec backend_3 env | grep SECRET_KEY
# Должны быть одинаковые

# Если разные — исправь docker-compose.yml и пересоздай контейнеры:
docker compose up -d --force-recreate
```

**3. Один инстанс постоянно падает, остальные работают**

Симптом: `docker compose ps` показывает `Restarting` у backend_2, остальные `Up`.

```bash
# Смотрим только логи проблемного инстанса:
docker compose logs backend_2

# Проверяем ресурсы — может не хватать памяти:
docker stats backend_2

# Типичная причина: миграция применилась дважды или конфликт
# Попробуй пересоздать только этот контейнер:
docker compose up -d --force-recreate backend_2
```

**4. PostgreSQL деградирует под нагрузкой**

Симптом: при нагрузочном тесте время ответа растёт, `docker stats` показывает высокий CPU у postgres.

```bash
# Смотрим активные запросы к PostgreSQL в реальном времени:
docker compose exec postgres psql -U postgres -d bulletin_board \
  -c "SELECT pid, state, query_start, left(query, 80) as query FROM pg_stat_activity WHERE state != 'idle' ORDER BY query_start;"

# Количество соединений по состоянию:
docker compose exec postgres psql -U postgres -d bulletin_board \
  -c "SELECT state, count(*) FROM pg_stat_activity GROUP BY state;"

# Долгоиграющие запросы (больше 5 секунд):
docker compose exec postgres psql -U postgres -d bulletin_board \
  -c "SELECT pid, now() - query_start as duration, left(query, 80) FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '5 seconds';"
```

**5. Nginx возвращает 504 Gateway Timeout**

Симптом: некоторые запросы зависают и возвращают 504.

```bash
# 504 = nginx дождался ответа от backend дольше timeout
# Смотрим логи nginx:
docker compose logs nginx | grep 504

# Проверяем что все backend отвечают локально:
docker compose exec nginx curl -s http://backend_1:8000/api/health
docker compose exec nginx curl -s http://backend_2:8000/api/health
docker compose exec nginx curl -s http://backend_3:8000/api/health

# Если один не отвечает — смотрим его логи:
docker compose logs backend_2

# Временно увеличить timeout в nginx.conf (proxy_read_timeout):
# proxy_read_timeout 60s;
```

---

## Архитектура

- [Концепция: горизонтальное масштабирование в вакууме](../docs/architecture/level-2-scaling/concept.html) — load balancer + N stateless-воркеров + общее хранилище состояния
- [Реализация: реальный docker-compose.yml](../docs/architecture/level-2-scaling/implementation.html) — nginx upstream round-robin, backend_1/2/3, один общий postgres
- [Боль → решение: Level 1 → Level 2](../docs/architecture/level-2-scaling/pain-solution.html) — было/стало/почему это работает и где новый предел
- [Сеть: балансировка внутри docker-сети](../docs/architecture/level-2-scaling/network.html) — снаружи VPS по-прежнему виден только порт 80, выбор инстанса скрыт внутри

**Теория сетей глубже:**
- [Алгоритмы балансировки нагрузки](../docs/architecture/networking-theory/05-load-balancing-algorithms.html) — round robin vs least connections vs ip hash, где у каждого предел

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
