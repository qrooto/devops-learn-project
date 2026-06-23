# Уровень 1 — Монолит: первый живой сервис

## Зачем начинать отсюда?

Нельзя понять зачем нужен Kubernetes не увидев сначала боль от одного контейнера.
Нельзя оценить Redis не почувствовав как база данных задыхается.

Мы начинаем с самой простой рабочей конфигурации — не потому что она правильная, а потому что она понятная. Каждый следующий уровень будет добавлять сложность только тогда, когда ты лично увидишь проблему которую эта сложность решает.

## Аналогия

Представь кафе. Уровень 1 — это один повар, одна касса, один столик с меню.
Всё работает пока посетителей мало. Когда очередь вырастает — повар не справляется.
Следующие уровни: нанимаем второго повара (масштабирование), добавляем кэшир (Redis),
пишем автоматизацию для найма (CI/CD).

## Архитектура

```
Браузер
    │
    └── HTTP :80 ──→ Nginx
                       │
                       ├── GET /         → статика (HTML/CSS/JS) из /frontend/
                       └── GET,POST /api/ → proxy_pass → FastAPI :8000
                                                              │
                                                       PostgreSQL :5432
```

**Почему именно такая схема?**
- Nginx перед бэкендом — потому что Python-серверы (uvicorn) плохо справляются с раздачей статики и медленными клиентами. Nginx держит тысячи соединений асинхронно.
- PostgreSQL отдельно от бэкенда — потому что данные должны переживать перезапуск приложения.

## Что нового в этой версии (v2)

| Раньше | Сейчас |
|--------|--------|
| `CREATE TABLE IF NOT EXISTS` в коде | Alembic миграции |
| Автор объявления — строка | Авторизация через JWT |
| Любой может удалить чужое | Только владелец удаляет своё |
| Контейнер от root | Контейнер от non-root пользователя |

---

## Шаг 1 — Разобрать структуру (не запускать пока)

```
level-1-monolith/
├── docker-compose.yml
├── backend/
│   ├── main.py           ← REST API
│   ├── auth.py           ← JWT: создание/проверка токенов
│   ├── alembic.ini       ← конфиг миграций
│   ├── alembic/
│   │   ├── env.py        ← читает DATABASE_URL из env
│   │   └── versions/
│   │       └── 001_initial_schema.py  ← создаёт таблицы users и ads
│   ├── entrypoint.sh     ← запускает миграции, потом сервер
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── index.html        ← форма входа + список объявлений
│   ├── style.css
│   └── app.js            ← JWT в localStorage, fetch с Authorization header
├── nginx/
│   └── nginx.conf        ← static files + proxy /api/
└── load-tests/
    ├── smoke.js          ← быстрая проверка: живо ли?
    └── stress.js         ← нагрузочный: сколько выдержит?
```

**Прочитай `docker-compose.yml` и найди ответы:**
1. По какому `condition` бэкенд ждёт postgres?
2. Что такое `healthcheck` и почему он нужен?
3. Зачем `postgres_data` объявлен в `volumes:` внизу файла?

---

## Шаг 2 — Понять Dockerfile

```bash
cat backend/Dockerfile
```

**Обрати внимание:**
- `RUN useradd --create-home appuser` — создаём пользователя
- `USER appuser` — запускаем процесс НЕ от root

**Почему это важно:**
Если в приложении есть уязвимость и злоумышленник получил выполнение кода — он окажется внутри контейнера от пользователя `appuser` без прав sudo. Это не панацея (container escape существует), но обязательная базовая практика.

**Проверь как это работает:**
```bash
docker compose up --build -d
docker compose exec backend whoami
# Должен вывести: appuser
```

---

## Шаг 3 — Запустить

```bash
cd level-1-monolith
docker compose up --build -d

# Следить за стартом
docker compose logs -f
```

**Что смотреть в логах:**

В логах `backend` ищи:
```
Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade -> 001, Initial schema
Starting server...
INFO:     Application startup complete.
```

Это означает:
1. Alembic запустился и применил миграцию 001
2. Uvicorn запустил FastAPI

Если видишь `psycopg2.OperationalError: could not connect` — нормально, бэкенд ретраит каждые 2 секунды пока postgres не поднимется.

---

## Шаг 4 — Проверить через curl

```bash
# Здоровье сервиса
curl http://localhost/api/health
# {"status":"ok"}

# Зарегистрироваться
curl -s -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123","email":"alice@test.com"}' | python3 -m json.tool

# Сохранить токен
TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"

# Создать объявление (требует токен)
curl -s -X POST http://localhost/api/ads \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Продам велосипед","description":"Почти новый","price":5000}' | python3 -m json.tool

# Список объявлений (без токена — публично)
curl -s http://localhost/api/ads | python3 -m json.tool

# Попробовать создать без токена → должна быть ошибка 401
curl -s -X POST http://localhost/api/ads \
  -H "Content-Type: application/json" \
  -d '{"title":"test","description":"test","price":1}'
# {"detail":"Authentication required"}
```

---

## Шаг 5 — Разобрать JWT

```bash
# JWT состоит из трёх частей разделённых точкой: header.payload.signature
# Payload можно раскодировать (он не зашифрован — только подписан!)
echo $TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | python3 -m json.tool
```

**Что увидишь:**
```json
{
    "sub": "1",        ← user_id
    "username": "alice",
    "exp": 1234567890  ← Unix timestamp истечения
}
```

**Важно:** payload виден любому кто держит токен. Поэтому в JWT **нельзя** хранить пароли, карточные данные, секреты.

**Задание:** Измени `SECRET_KEY` в docker-compose.yml, перезапусти бэкенд и попробуй использовать старый токен. Что произойдёт? Почему?

---

## Шаг 6 — Разобрать Alembic

```bash
# Зайти в контейнер бэкенда
docker compose exec backend bash

# Внутри контейнера:
alembic history          # история миграций
alembic current          # текущая версия
alembic heads            # последняя версия

# Посмотреть SQL который будет выполнен (dry run)
alembic upgrade head --sql
exit
```

```bash
# Зайти в PostgreSQL и посмотреть что создалось
docker compose exec postgres psql -U postgres -d bulletin_board

# Внутри psql:
\dt                     -- список таблиц
\d ads                  -- структура таблицы ads
\d users                -- структура таблицы users
SELECT * FROM alembic_version;  -- текущая версия миграций
\q
```

**Что видишь:** таблица `alembic_version` — Alembic хранит здесь текущую версию миграций. При следующем запуске он сравнивает её с файлами в `versions/` и применяет только новые.

---

## Шаг 7 — Нагрузочный тест (ломаем)

```bash
# Терминал 1: смотрим потребление ресурсов
docker stats

# Терминал 2: лёгкий тест
k6 run load-tests/smoke.js

# Терминал 2: стресс-тест
k6 run load-tests/stress.js
```

**Что наблюдать в `docker stats`:**
- Колонка `CPU %` у контейнера `backend` — растёт при нагрузке
- Колонка `MEM USAGE` — должна быть стабильной (нет утечек памяти)
- Колонка `NET I/O` — входящий/исходящий трафик

**Что наблюдать в k6:**
- `http_req_duration` — время ответа. При 50+ VU начнёт расти.
- `http_req_failed` — процент ошибок. При перегрузке появятся 502/503.
- `✓ status 200` vs `✗ status 200` — соотношение успешных/неуспешных.

**Боль которую ты видишь:** один Python-процесс не может обрабатывать много запросов одновременно. При 50+ concurrent users время ответа деградирует. Это и есть мотивация для Уровня 2.

---

## Шаг 8 — Логи и диагностика

```bash
# Хвост логов конкретного сервиса
docker compose logs --tail=50 -f backend

# Логи всех сервисов с временными метками
docker compose logs -t

# Посмотреть что внутри работающего контейнера
docker compose exec backend ps aux
docker compose exec backend df -h      # место на диске
docker compose exec backend free -h    # память
```

**Зайти "как в SSH" внутрь:**
```bash
docker compose exec backend bash
# Теперь ты внутри контейнера — можешь исследовать файлы, смотреть процессы
ls /app
cat /app/main.py
exit
```

---

## Шаг 9 — Остановить и очистить

```bash
# Остановить (данные сохраняются)
docker compose down

# Остановить + удалить volumes (чистый старт)
docker compose down -v

# Удалить образы (пересобрать с нуля)
docker compose down --rmi all
```

**Разница важна:** `down` без флагов сохраняет данные в volume `postgres_data`. Если остановишь и запустишь снова — объявления и пользователи на месте. `down -v` — чистый лист.

---

## Типичные ошибки

**"port is already allocated"** → порт 80 занят. Найди кто: `sudo lsof -i :80` и останови.

**"health check failing"** → PostgreSQL стартует медленно. Подожди 30 секунд и перепроверь.

**Бэкенд падает с "Cannot connect to database after 10 attempts"** → PostgreSQL не запустился. Проверь: `docker compose logs postgres`.

**"Authentication required" при создании объявления** → JWT не передаётся. В браузере: DevTools → Network → смотри заголовок `Authorization` в запросе.

---

## На собеседовании спросят

**Q: Что такое Docker volume и зачем он нужен?**
A: Volume — хранилище данных вне контейнера. Контейнеры ephemeral (данные теряются при удалении). Volume переживает перезапуски и удаление контейнера. PostgreSQL хранит данные в volume.

**Q: Зачем Nginx перед Python-приложением?**
A: Nginx (async, C) эффективно держит тысячи одновременных соединений, отдаёт статику, умеет gzip, rate limiting. Python-сервер (uvicorn) лучше справляется с бизнес-логикой, но плохо — с медленными клиентами.

**Q: Объясни JWT. Как он работает?**
A: Три части: header (алгоритм), payload (данные), signature (HMAC от header+payload с secret_key). Сервер проверяет подпись — если сошлась, доверяет данным из payload. Stateless: сервер не хранит сессии.

**Q: Что такое database migration и зачем нужен Alembic?**
A: Migration — изменение схемы БД с историей. Alembic версионирует изменения как git — для кода. Позволяет откатиться (`downgrade`), воспроизвести схему на новой БД, синхронизировать dev/prod.

**Q: Что означает `depends_on` с `condition: service_healthy` в docker-compose?**
A: Бэкенд стартует только после того как postgres прошёл healthcheck (`pg_isready`). Без этого бэкенд может стартовать раньше postgres → коннект упадёт.

---

## Итог уровня 1 — что ты умеешь

- [ ] Запустить многоконтейнерное приложение одной командой
- [ ] Читать логи и понимать sequence запуска
- [ ] Работать с БД напрямую через psql
- [ ] Использовать curl для тестирования API
- [ ] Понимать как работает JWT
- [ ] Запустить нагрузочный тест и читать его вывод
- [ ] Видеть деградацию под нагрузкой
- [ ] Объяснить зачем Nginx перед бэкендом

**Боль уровня 1:** один бэкенд не справляется → Уровень 2.

---

## Коммит

```bash
cd ..
git add level-1-monolith/
git commit -m "level-1: monolith with jwt auth and alembic migrations"
git push origin main
```

---

## Security Block: Уровень 1

### Что мы применили

**1. Non-root пользователь в контейнере** (`Dockerfile`: `RUN useradd ... && USER appuser`)

Если атакующий найдёт уязвимость в приложении и получит выполнение кода внутри контейнера — он окажется пользователем `appuser` без прав. Не root. Это не панацея (container escape существует), но обязательная базовая практика.

**2. Секреты через переменные окружения, не в коде**

`SECRET_KEY`, `DATABASE_URL` — в `docker-compose.yml` через `environment:`, не захардкожены в `main.py`. Причина: код попадает в git, git попадает на GitHub. Секрет в коде = секрет в публичном репозитории навсегда (даже если удалишь — он остаётся в истории коммитов).

**3. JWT — stateless аутентификация**

Сервер не хранит сессии в памяти. Токен подписан и содержит всё необходимое. Нет хранилища сессий = нет точки отказа и нет данных которые можно украсть из памяти процесса.

**4. PostgreSQL недоступен снаружи**

В `docker-compose.yml` у postgres нет секции `ports:` — значит порт 5432 не проброшен на хост. База доступна только внутри Docker-сети между контейнерами.

**5. Принцип Least Privilege для базы данных**

Идеальный вариант (для самостоятельного улучшения): создавать отдельного PostgreSQL-пользователя с правами только на `SELECT/INSERT/UPDATE/DELETE` для конкретной базы. Сейчас мы используем суперпользователя `postgres` — это нормально для учёбы, но не для production.

### Как это улучшить в production

```sql
-- Создать пользователя приложения с минимальными правами
CREATE USER app_user WITH PASSWORD 'strong_password';
GRANT CONNECT ON DATABASE bulletin_board TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_user;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO app_user;
-- app_user не может DROP TABLE, CREATE TABLE, создавать других пользователей
```

⚠️ **Антипаттерны:**

- **Запускать контейнер от root** — `USER root` в Dockerfile или его отсутствие. Большинство базовых образов запускаются от root по умолчанию. Всегда явно добавляй `USER`.
- **Хранить `SECRET_KEY` в коде** — например, `SECRET_KEY = "mysecret123"` прямо в `main.py`. Если репозиторий публичный — это немедленная компрометация. Даже в приватном — это плохая практика: секрет должен быть отделён от кода.

---

## Best Practices Checklist

Пройдись после завершения уровня:

- [ ] Контейнер не запускается от root — `docker compose exec backend whoami` возвращает не `root`
- [ ] Порт PostgreSQL не проброшен на хост — `ss -tulpn | grep 5432` на сервере пуст
- [ ] `SECRET_KEY` не захардкожен в коде — только через переменную окружения
- [ ] JWT не содержит пароль или другие секреты в payload — проверь декодированием
- [ ] Миграции применяются автоматически, руками `CREATE TABLE` не делается
- [ ] `.dockerignore` существует и исключает `.env`, `*.log`, `.git`
- [ ] Версии образов в `docker-compose.yml` закреплены (не `latest`)

---

## Troubleshooting: Уровень 1

### Общая диагностика Docker

```bash
# Статус всех контейнеров:
docker compose ps

# Логи конкретного сервиса (последние 50 строк):
docker compose logs --tail=50 backend

# Логи в реальном времени:
docker compose logs -f backend

# Потребление ресурсов:
docker stats

# Зайти внутрь контейнера:
docker compose exec backend bash
```

### Типичные проблемы

**1. Контейнер постоянно перезапускается (Restarting)**

Симптом: `docker compose ps` показывает статус `Restarting` или `Exit 1`.

```bash
# Смотри логи — там будет ошибка:
docker compose logs backend

# Частая причина: бэкенд стартует раньше PostgreSQL
# Смотри: "could not connect to server" или "Connection refused"
docker compose logs postgres

# Решение: подождать или перезапустить только упавший сервис:
docker compose restart backend
```

**2. Nginx отдаёт 502 Bad Gateway**

Симптом: открываешь браузер, видишь 502.

```bash
# 502 = Nginx не может достучаться до бэкенда
# Проверяем запущен ли бэкенд:
docker compose ps

# Смотрим логи nginx — там будет "connect() failed":
docker compose logs nginx

# Смотрим логи бэкенда:
docker compose logs backend

# Проверяем отвечает ли бэкенд изнутри Docker-сети:
docker compose exec nginx curl http://backend:8000/api/health
```

**3. "Authentication required" — 401 на все запросы**

Симптом: curl возвращает `{"detail":"Authentication required"}` даже с токеном.

```bash
# Проверяем что токен передаётся:
curl -v http://localhost/api/ads -H "Authorization: Bearer $TOKEN" 2>&1 | grep -E "Authorization|401"

# Декодируем payload токена — не истёк ли:
echo $TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | python3 -m json.tool
# Смотри поле "exp" — это Unix timestamp. Сравни с date +%s

# Если SECRET_KEY изменили — все старые токены невалидны, нужно перелогиниться
```

**4. PostgreSQL не запускается**

Симптом: `docker compose logs postgres` показывает ошибки.

```bash
# Смотрим логи базы:
docker compose logs postgres

# Частая причина: volume с поломанными данными
# Ядерный вариант — удалить volume и начать чисто (ДАННЫЕ УДАЛЯТСЯ):
docker compose down -v
docker compose up -d

# Проверяем что база живая:
docker compose exec postgres pg_isready -U postgres
# /var/run/postgresql:5432 - accepting connections
```

**5. Миграции не применились**

Симптом: `curl http://localhost/api/ads` возвращает ошибку про несуществующую таблицу.

```bash
# Проверяем что entrypoint.sh отработал:
docker compose logs backend | grep -E "migration|alembic|error"

# Запустить миграции вручную:
docker compose exec backend alembic upgrade head

# Проверить текущую версию:
docker compose exec backend alembic current

# Посмотреть таблицы в базе:
docker compose exec postgres psql -U postgres -d bulletin_board -c "\dt"
```
