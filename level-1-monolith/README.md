# Уровень 1 — Монолит: первый живой сервис

> **Это [руки]** — практический маршрут уровня: команды, эксперименты, поломки. Нужна сессия с VM.
> **Теория уровня — в `CURRICULUM.md` → «Уровень 1»**: зачем всё это, анатомия Dockerfile / docker-compose.yml / nginx.conf, вопросы с собеседований. Читай её до или параллельно — здесь она не дублируется. Легенда `[голова]`/`[руки]` — в START_HERE.md.

## Архитектура — карта уровня

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

**Что нового в этой версии (v2):**

| Раньше | Сейчас |
|--------|--------|
| `CREATE TABLE IF NOT EXISTS` в коде | Alembic миграции |
| Автор объявления — строка | Авторизация через JWT |
| Любой может удалить чужое | Только владелец удаляет своё |
| Контейнер от root | Контейнер от non-root пользователя |

---

## 1.1 — Практика: один контейнер, ничего лишнего

> Теория: CURRICULUM → «1.1 — Один контейнер» (анатомия Dockerfile, слои, кэш, non-root, ENTRYPOINT vs CMD).

**Шаг 1 — Запустить один контейнер с FastAPI**

```bash
cd level-1-monolith

# Собрать образ
docker build -t bulletin-backend ./backend

# Запустить контейнер
docker run -d \
  --name my-backend \
  -p 8000:8000 \
  -e DATABASE_URL="sqlite:///./test.db" \
  bulletin-backend

# Проверить что работает
curl http://localhost:8000/api/health
# {"status": "ok"}
```

**Что увидишь:** ответ от FastAPI — приложение работает без установки Python локально.

**Почему это важно:** образ `bulletin-backend` можно передать на любой сервер — он запустится ровно так же.

**Шаг 2 — Изучить что внутри**

```bash
# Зайти "как в SSH" внутрь работающего контейнера
docker exec -it my-backend bash

# Внутри контейнера:
whoami          # appuser — не root
python3 --version
ls /app
cat /app/main.py
exit
```

**Шаг 3 — Остановить**

```bash
docker stop my-backend
docker rm my-backend
```

> **Как в проде:** никогда не запускают один контейнер напрямую через `docker run` в production — используют оркестратор (Docker Compose, Kubernetes). Прямой запуск — только для отладки и изучения.

---

## 1.2 — Практика: Compose-стек с PostgreSQL

> Теория: CURRICULUM → «1.2 — Добавляем PostgreSQL» (анатомия docker-compose.yml: healthcheck, volumes, restart-политики, networks).

**Шаг 1 — Разобрать структуру (не запускать пока)**

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
3. Зачем `postgres_data` объявлен в `volumes:` внизу файла? Что происходит с данными при `docker compose down`?

**Шаг 2 — Запустить стек**

```bash
docker compose up --build -d

# Следить за стартом
docker compose logs -f
```

**Что смотреть в логах** `backend`:
```
Running database migrations...
INFO  [alembic.runtime.migration] Running upgrade -> 001, Initial schema
Starting server...
INFO:     Application startup complete.
```

Это означает: Alembic применил миграцию 001, затем Uvicorn запустил FastAPI. Если видишь `psycopg2.OperationalError: could not connect` — нормально, бэкенд ретраит каждые 2 секунды пока postgres не поднимется.

Проверь что процесс не под root:
```bash
docker compose exec backend whoami
# Должен вывести: appuser
```

**Шаг 3 — Зайти в PostgreSQL напрямую**

```bash
docker compose exec postgres psql -U postgres -d bulletin_board

# Внутри psql:
\dt                    -- список таблиц
\d ads                 -- структура таблицы ads
\d users               -- структура таблицы users
SELECT * FROM alembic_version;  -- версия миграций
\q
```

**Шаг 4 — Проверить что данные переживают перезапуск**

```bash
# Создать объявление
curl -s -X POST http://localhost:8000/api/ads \
  -H "Content-Type: application/json" \
  -d '{"title":"Тест данных","description":"Переживёт ли перезапуск?","price":1}'

# Перезапустить бэкенд (не трогая postgres)
docker compose restart backend

# Данные на месте?
curl -s http://localhost:8000/api/ads | python3 -m json.tool
```

**Что увидишь:** объявление осталось — данные хранятся в volume `postgres_data`, не в контейнере.

**Шаг 5 — Удалить данные намеренно**

```bash
docker compose down -v   # -v удаляет volumes
docker compose up -d
curl -s http://localhost:8000/api/ads
# [] — пусто, данные сброшены
```

**Почему это важно:** `docker compose down` без флагов безопасен — данные сохранены. `down -v` — полный сброс. Знать разницу критично.

### Что сломать намеренно — 1.2

**Поломка 1 — Убрать healthcheck**

Открой `docker-compose.yml`, закомментируй блок `healthcheck` у postgres и блок `condition: service_healthy` у бэкенда. Запусти `docker compose up --build -d`. Смотри логи:

```bash
docker compose logs -f backend
```

Иногда бэкенд стартует раньше postgres и падает с `could not connect to database`. Без healthcheck — нет гарантии порядка старта.

**Что диагностировать:** `docker compose ps` — статус контейнеров. `docker compose logs postgres` — когда именно postgres принял соединения.

**Верни:** раскомментируй и пересобери.

**Поломка 2 — Неверный пароль к базе**

Измени `POSTGRES_PASSWORD` в `docker-compose.yml` так, чтобы у postgres и бэкенда были разные пароли. Запусти — увидишь:

```bash
docker compose logs backend
# sqlalchemy.exc.OperationalError: FATAL:  password authentication failed
```

**Что диагностировать:** `docker compose exec postgres psql -U postgres` — если зашёл без пароля, значит проблема в переменной бэкенда, а не в самом postgres.

**Верни:** одинаковые пароли.

---

## 1.3 — Практика: Nginx перед бэкендом

> Теория: CURRICULUM → «1.3 — Добавляем Nginx» (анатомия nginx.conf: worker-модель, location, proxy_pass, заголовки X-Forwarded-*).

**Шаг 1 — Прочитать конфиг Nginx**

```bash
cat nginx/nginx.conf
```

Найди и объясни:
- Где nginx отдаёт статику сам, а где передаёт на бэкенд
- Что означает `proxy_pass http://backend:8000`
- Зачем `proxy_set_header Host $host`

**Шаг 2 — Запустить полный стек**

```bash
docker compose up --build -d
docker compose ps
```

Теперь все запросы идут через nginx на порт 80.

**Шаг 3 — Сравнить прямой доступ и через nginx**

```bash
# Через Nginx (порт 80) — так видит браузер
curl -v http://localhost/api/health
# < Server: nginx/1.25.x

# Напрямую к бэкенду (если проброшен 8000) — так видим только мы
curl -v http://localhost:8000/api/health
# < Server: uvicorn
```

**Шаг 4 — Убедиться что статика отдаётся Nginx, а не Python**

```bash
# Запросить index.html
curl -I http://localhost/

# В заголовках:
# Server: nginx
# Content-Type: text/html
# — Nginx сам отдал файл, не спрашивая Python
```

---

## 1.4 — Практика: JWT и миграции

> Теория: CURRICULUM → «1.4 — Полный монолит» и вопрос про JWT в «На собеседовании спросят».

**Шаг 1 — Полный цикл работы с API**

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

**Шаг 2 — Разобрать JWT**

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

**Задание:** `SECRET_KEY` читается из переменной окружения с дефолтом `dev-only-change-in-production` (`auth.py`) — в docker-compose.yml её сейчас нет вообще. Добавь `SECRET_KEY: some-other-value` в `environment:` бэкенда, перезапусти, попробуй использовать старый токен. Что произошло и почему?

**Шаг 3 — Разобрать Alembic**

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

**Что видишь:** таблица `alembic_version` в базе (смотрел её в 1.2, Шаг 3) — Alembic хранит там текущую версию миграций. При следующем запуске он сравнивает её с файлами в `versions/` и применяет только новые.

---

## Нагрузочный тест — видим боль

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

## OOM Killer: что происходит когда память кончается

**OOM Killer** (Out of Memory Killer) — механизм ядра Linux который убивает процессы когда система исчерпала физическую память. В Docker он работает через cgroups: контейнеру установлен лимит, он его превысил — ядро отправляет SIGKILL. Exit code **137** = 128 + 9 (SIGKILL).

В production утечки памяти случаются. Видишь `Exit 137` — значит контейнер убил OOM Killer, а не он сам упал.

**Шаг 1 — Добавить mem_limit в docker-compose.yml**

Открой `docker-compose.yml` и добавь к секции `backend`:

```yaml
  backend:
    mem_limit: 150m       # добавь
    memswap_limit: 150m   # отключаем swap — чтобы OOM наступил сразу, без буфера
```

```bash
docker compose up -d
```

**Шаг 2 — Открыть два терминала**

```bash
# Терминал 1: смотрим потребление в реальном времени
docker stats
```

**Шаг 3 — Запустить memory hog**

```bash
# Терминал 2: выделяем память по 1 MB каждые 0.2 секунды
docker compose exec backend python3 -c "
import time
data = []
for i in range(1000):
    data.append(b'x' * 1024 * 1024)
    print(f'Выделено: {i+1} MB', flush=True)
    time.sleep(0.2)
"
```

**Что увидишь:**

В `docker stats` — `MEM USAGE` растёт: 50MB → 100MB → 140MB → контейнер исчезает из списка.
В Терминале 2 — соединение обрывается без сообщения об ошибке.

**Шаг 4 — Прочитать exit code**

```bash
docker compose ps
# NAME      STATUS
# backend   Exit 137      ← OOM Kill

# Системный лог хоста — подтверждение от ядра:
sudo dmesg | grep -i "killed process\|out of memory" | tail -5
# [12345.678] Killed process 9876 (python3) total-vm:200000kB ...
```

**Шаг 5 — Сравнить exit codes**

| Ситуация | Сигнал | Exit Code |
|---|---|---|
| `docker stop` (graceful) | SIGTERM → SIGKILL | 0 |
| OOM Kill (нет памяти) | SIGKILL от ядра | **137** |
| `kill -9` внутри контейнера | SIGKILL | **137** |
| Приложение упало само | — | 1 или другое ненулевое |

**Шаг 6 — Восстановить**

Убери `mem_limit` и `memswap_limit` из `docker-compose.yml` (или оставь — это хорошая практика) и запусти снова:

```bash
docker compose up -d
```

**Почему лимиты важны в production:**

Без `mem_limit` контейнер с утечкой съедает RAM всего сервера. Когда память заканчивается — OOM Killer убивает случайный процесс. Этим процессом может оказаться PostgreSQL. С лимитами — виноватый контейнер умирает сам, остальные живут.

---

## Логи и диагностика

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

## Бэкап и восстановление PostgreSQL

Данные живут в volume `postgres_data`. Volume переживает перезапуски — но не `down -v`, не умерший диск, не `DROP TABLE` уставшим вечером. **База без бэкапа — это данные, которые ты согласился потерять.** А вопрос «как вы бэкапили базы» задают почти на каждом собеседовании.

**Сделать дамп (логический бэкап):**

```bash
# pg_dump выполняется ВНУТРИ контейнера, дамп складываем на хост:
mkdir -p ~/backups
docker compose exec -T postgres pg_dump -U postgres bulletin_board \
  > ~/backups/bulletin_board_$(date +%F_%H%M).sql

# Посмотри что внутри — это обычный SQL (CREATE TABLE, COPY с данными):
head -40 ~/backups/bulletin_board_*.sql
```

**По расписанию — cron на хосте:**

```bash
crontab -e
# Каждый день в 03:00, дампы старше 7 дней удаляются:
0 3 * * * cd ~/devops-project/level-1-monolith && docker compose exec -T postgres pg_dump -U postgres bulletin_board > ~/backups/bulletin_board_$(date +\%F).sql && find ~/backups -name "*.sql" -mtime +7 -delete
```

🔒 Security: бэкап — это копия ВСЕХ данных, включая хэши паролей пользователей. Права на папку — только владелец (`chmod 700 ~/backups`), а хранить дампы нужно **вне этого хоста**: умрёт диск — умрут и база, и её «бэкап» рядом. Минимум — копируй на другую машину (`scp`/`rsync`), правильный вариант — объектное хранилище (S3/Yandex Object Storage, встретится на уровне 9).

**Restore drill — обязательная часть.** Бэкап, из которого ни разу не восстанавливались — это не бэкап, а файл с надеждой. Проверяется только одним способом:

В реальности восстановление проверяют на отдельной базе, не трогая продакшн:


```bash
# Создать тестовую базу и восстановить туда
docker compose exec -T postgres psql -U postgres -c "CREATE DATABASE bulletin_board_test;"
docker compose exec -T postgres psql -U postgres bulletin_board_test \
  < ~/backups/bulletin_board_*.sql

```bash
# Проверить что данные на месте
docker compose exec postgres psql -U postgres -d bulletin_board_test -c "SELECT COUNT(*) FROM ads;"

```bash
# Убрать тестовую базу
docker compose exec postgres psql -U postgres -c "DROP DATABASE bulletin_board_test;"
```

Если шаг 4 прошёл — у тебя есть бэкап. Если нет — только что ты узнал это на учебном стенде, а не при инциденте.

**Логический vs физический бэкап (пока просто знать):**
- **Логический** (`pg_dump`) — SQL-текст «как пересоздать базу». Переносим между версиями PostgreSQL, человекочитаем, но на больших базах медленный и держит долгую транзакцию.
- **Физический** (`pg_basebackup`, снапшоты диска) — копия файлов данных как есть. Быстро на любых размерах, позволяет point-in-time recovery по WAL, но только та же мажорная версия PostgreSQL. Для нашей базы в мегабайты хватает pg_dump; в проде большие базы бэкапят физически.

**Задание для самопроверки:** объясни, почему `docker compose down` (без `-v`) — не защита данных, и от каких трёх сценариев потери не спасает volume вообще.

---

## Остановить и очистить

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

## Что сломать намеренно — Уровень 1

**Поломка 1 — Заполнить диск**

```bash
# Создать большой файл внутри контейнера бэкенда
docker compose exec backend dd if=/dev/zero of=/tmp/bigfile bs=1M count=500

# Что упадёт первым?
docker compose logs backend
# Смотри на ошибки записи, ошибки SQLite/postgres
```

**Диагностика:**
```bash
docker compose exec backend df -h    # место в контейнере
docker system df                      # место занятое Docker вообще
```

**Почему это важно:** в production диск заполняют логи. Это одна из самых частых причин инцидентов.

**Поломка 2 — Убить процесс внутри контейнера**

```bash
# Найти PID uvicorn
docker compose exec backend ps aux

# Убить процесс
docker compose exec backend kill -9 <PID>

# Контейнер остановится сам
docker compose ps
# backend   Exit 137
```

**Диагностика:** `docker compose logs backend --tail=5`. `Exit 137` = процесс убит сигналом (128 + SIGKILL=9).

**Что важно знать:** Docker Compose с `restart: unless-stopped` перезапустит контейнер автоматически. Kubernetes сделает это надёжнее.

**Поломка 3 — OOM Kill: выход за лимит памяти**

Полный разбор — выше, раздел «OOM Killer: что происходит когда память кончается». Если пропустил его — самое время: это самая показательная поломка уровня.

**Поломка 4 — Сломать миграцию**

Открой `backend/alembic/versions/001_initial_schema.py`, измени `ads` на `advertisements` в CREATE TABLE. Запусти `docker compose up --build -d`. Что произойдёт с уже существующими данными? Что в логах?

---

## Типичные ошибки

**"port is already allocated"** → порт 80 занят. Найди кто: `sudo lsof -i :80` и останови.

**"health check failing"** → PostgreSQL стартует медленно. Подожди 30 секунд и перепроверь.

**Бэкенд падает с "Cannot connect to database after 10 attempts"** → PostgreSQL не запустился. Проверь: `docker compose logs postgres`.

**"Authentication required" при создании объявления** → JWT не передаётся. В браузере: DevTools → Network → смотри заголовок `Authorization` в запросе.

---

## Справочник команд — Уровень 1

| Команда | Описание |
|---------|---------|
| `docker build -t bulletin-backend ./backend` | Собрать образ бэкенда |
| `docker run -d -p 8000:8000 bulletin-backend` | Запустить один контейнер в фоне |
| `docker logs my-backend` | Логи одиночного контейнера |
| `docker stop my-backend && docker rm my-backend` | Остановить и удалить одиночный контейнер |
| `docker compose up --build -d` | Собрать и запустить все контейнеры |
| `docker compose ps` | Статус всех контейнеров |
| `docker compose logs -f backend` | Следить за логами бэкенда |
| `docker compose logs -t` | Логи всех сервисов с метками времени |
| `docker compose exec backend bash` | Зайти внутрь контейнера |
| `docker compose exec postgres psql -U postgres -d bulletin_board` | Зайти в PostgreSQL |
| `docker compose restart backend` | Перезапустить только бэкенд |
| `docker compose down` | Остановить, данные сохранить |
| `docker compose down -v` | Остановить, данные удалить |
| `docker stats` | Мониторинг CPU/RAM контейнеров |
| `docker system df` | Место занятое Docker |
| `docker system prune` | Очистить неиспользуемые образы и контейнеры |
| `k6 run load-tests/smoke.js` | Лёгкий дым-тест |
| `k6 run load-tests/stress.js` | Стресс-тест |

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
- [ ] Сделать бэкап базы и восстановиться из него

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
- [ ] Бэкап настроен по расписанию и хранится не на этом же хосте
- [ ] Restore drill пройден: `down -v` → восстановление из дампа → данные на месте

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

**6. Контейнер внезапно умирает (Exit 137)**

Симптом: `docker compose ps` показывает `Exit 137`, контейнер пересоздался сам по `restart: unless-stopped`.

```bash
# Exit 137 = OOM Kill (убит ядром из-за нехватки памяти)
# Логи обрываются внезапно — нет graceful shutdown:
docker compose logs backend --tail=20

# Подтверждение от ядра Linux:
sudo dmesg | grep -i "killed process\|out of memory" | tail -5
# [12345.678] Killed process 9876 (python3) total-vm:150000kB rss:148000kB

# Наблюдать рост памяти в реальном времени:
docker stats
# Если MEM USAGE приближается к лимиту — жди OOM Kill

# Решение A: найди утечку (heap profiler — memory_profiler для Python)
# Решение B: увеличь mem_limit в docker-compose.yml
# Решение C: оптимизируй запросы — меньше данных грузить в память
```

---

## Архитектура

- [Концепция: reverse proxy + монолит в вакууме](../docs/architecture/level-1-monolith/concept.html) — единая точка входа, один backend, одна база, без привязки к проекту
- [Реализация: реальный docker-compose.yml](../docs/architecture/level-1-monolith/implementation.html) — nginx, FastAPI на uvicorn :8000, postgres, конкретные volume и healthcheck
- [Сеть: host → docker network → контейнер](../docs/architecture/level-1-monolith/network.html) — что публикуется наружу VPS (только порт 80), что доступно только внутри docker-сети

**Теория сетей глубже:**
- [Анатомия HTTP-запроса](../docs/architecture/networking-theory/03-http-anatomy.html) — метод, заголовки, коды состояния, почему HTTP stateless
- [Docker bridge-сеть изнутри](../docs/architecture/networking-theory/04-docker-bridge-networking.html) — что реально происходит за `ports: "80:80"` и `DATABASE_URL=...@postgres:5432`

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
