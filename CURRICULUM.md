# Практический учебник DevOps: Доска объявлений

> **Принцип:** каждый инструмент появляется только тогда, когда ты лично почувствовал боль которую он решает.
> Строим → Ломаем → Наблюдаем → Чиним → Переходим дальше.
>
> **Разметка по типу сессии:** разделы «Зачем это нужно», «Как это работает», «Анатомия» — `[голова]`, читаются без терминала (метро, короткие сессии). Разделы «Практика» и «Что сломать» — `[руки]`, нужна VM (домашние сессии). Подробнее — START_HERE.md.

---

## Содержание

- [Подготовка среды](#подготовка-среды)
- [Уровень 1 — Первый контейнер до полного монолита](#уровень-1--первый-контейнер-до-полного-монолита)
- [Уровень 2 — Горизонтальное масштабирование](#уровень-2--горизонтальное-масштабирование)
- [Уровень 3 — Кэширование и оптимизация БД](#уровень-3--кэширование-и-оптимизация-бд)
- [Уровень 3.5 — HTTPS и TLS](#уровень-35--https-и-tls)
- [Уровень 4 — CI/CD](#уровень-4--cicd)
- [Уровень 5 — Kubernetes](#уровень-5--kubernetes)
- [Уровень 5.5 — Ingress и cert-manager](#уровень-55--ingress-и-cert-manager)
- [Уровень 6 — Observability](#уровень-6--observability)
- [Уровень 6.5 — AI-агент диагностики](#уровень-65--ai-агент-диагностики)
- [Уровень 7 — Helm](#уровень-7--helm)
- [Уровень 8 — GitOps / ArgoCD](#уровень-8--gitops--argocd)
- [Уровень 8.5 — Секреты в GitOps](#уровень-85--секреты-в-gitops)
- [Уровень 9 — Terraform](#уровень-9--terraform)
- [Уровень 10 — Ansible](#уровень-10--ansible)
- [Карта прогрессии боли](#карта-прогрессии-боли)

---

## Подготовка среды

**Требования:** Ubuntu 24.04 / Debian 12. Для старта (уровни 1-4, 9-10) хватит 1-2 CPU / 2GB RAM / 20GB SSD; для Kubernetes и мониторинга (уровни 5-8) — от 4GB RAM. Подробный разбор по фазам — INFRASTRUCTURE_PLANNING.md.

```bash
# 1. Обновить систему
sudo apt update && sudo apt upgrade -y

# 2. Установить Docker
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER
newgrp docker
docker --version && docker compose version

# 3. Установить Git
sudo apt install -y git
git config --global user.name "Твоё Имя"
git config --global user.email "твой@email.com"

# 4. Установить k6 (нагрузочное тестирование)
sudo gpg --no-default-keyring \
  --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69
echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list
sudo apt update && sudo apt install -y k6

# 5. Клонировать проект
git clone https://github.com/<username>/devops-project.git
cd devops-project
```

---

## Уровень 1 — Первый контейнер до полного монолита

### Зачем это нужно

Представь: ты написал FastAPI-приложение. Оно работает на твоей машине. Коллега клонирует — падает с `ModuleNotFoundError`. На сервере — `python3: command not found`. Деплой превращается в перебор: "а какую версию Python ты используешь? а зависимости установил? а переменные окружения?"

**Docker решает это так:** приложение упаковывается вместе со всем окружением — Python, зависимости, конфиги — в один портативный образ. Запускается одной командой на любой машине где есть Docker. Результат одинаковый везде.

Уровень 1 состоит из **четырёх мини-шагов** — от одного контейнера до полного стека с базой данных и nginx.

---

### 1.1 — Один контейнер, ничего лишнего

#### Как это работает

Docker — это как термос с едой: внутри изолированная среда с нужной температурой (runtime), едой (приложение) и крышкой (порт). Снаружи — просто термос, который можно передать кому угодно, и еда внутри останется такой же.

**Dockerfile** — рецепт сборки термоса. **Image** — готовый термос (неизменяемый). **Container** — работающий термос.

---

#### Анатомия Dockerfile

Открой `backend/Dockerfile` и разберём каждую строку:

```dockerfile
FROM python:3.12-slim
```
**FROM** — базовый образ, с которого начинается сборка. Это "операционная система + runtime" внутри контейнера.
- `python:3.12` весит ~1 ГБ (полный Debian + Python). `python:3.12-slim` весит ~150 МБ — тот же Python, но без компиляторов, документации и лишних пакетов.
- Почему не `python:alpine`? Alpine использует musl libc вместо glibc. Многие Python-пакеты (psycopg2, numpy) собираются под glibc и падают на Alpine с непонятными ошибками. Slim — лучший баланс между размером и совместимостью.
- Почему `3.12` а не `latest`? Тег `latest` меняется с каждым новым релизом Python. Сегодня собрал образ с Python 3.12, завтра `latest` уже 3.13 — и твой `pip install` может упасть из-за несовместимости. Всегда пиши конкретную версию.

```dockerfile
WORKDIR /app
```
**WORKDIR** — рабочая директория внутри контейнера для всех последующих команд (RUN, COPY, CMD).
- Создаёт директорию если не существует.
- Все относительные пути в COPY и CMD будут отсчитываться отсюда.
- Альтернатива `RUN mkdir /app && cd /app` — не работает: каждый RUN запускает новый shell, состояние `cd` не сохраняется между командами.

```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt --no-cache-dir
```
**Почему requirements.txt копируется ОТДЕЛЬНО и РАНЬШЕ кода?**

Docker строит образ послойно. Каждая инструкция (FROM, COPY, RUN) — отдельный слой. Слои кэшируются: если содержимое не изменилось — слой берётся из кэша, команда не выполняется повторно.

Логика такая:
- `requirements.txt` меняется редко (только когда добавляешь новую библиотеку)
- Код меняется при каждом коммите

Если написать `COPY . . → RUN pip install` — любое изменение в любом файле кода инвалидирует кэш pip install. Сборка будет качать зависимости каждый раз заново (минуты).

Правильный порядок: сначала копируем только то что нужно для pip → устанавливаем зависимости (кэшируется) → потом копируем код. Изменение кода не трогает кэшированный pip-слой.

`--no-cache-dir` — не хранить скачанные пакеты внутри образа. pip по умолчанию кэширует в `~/.cache/pip`. В контейнере этот кэш бесполезен (используется один раз при сборке), но занимает место в образе.

```dockerfile
COPY . .
```
Теперь копируем весь код. Этот слой будет инвалидироваться при каждом изменении кода — но это нормально, он лёгкий (только файлы проекта, без зависимостей).

```dockerfile
RUN useradd --create-home appuser
USER appuser
```
**Принцип минимальных привилегий.** По умолчанию процессы в контейнере запускаются от `root`. Если в приложении есть уязвимость (RCE — Remote Code Execution) и злоумышленник получил выполнение кода — он оказывается внутри контейнера с правами root.

`useradd --create-home appuser` создаёт пользователя. `USER appuser` переключает все последующие инструкции (и сам процесс при запуске) на этого пользователя. Теперь даже при успешной атаке атакующий — непривилегированный пользователь без sudo.

Это не панацея (container escape существует), но **обязательная базовая практика** которую проверяют на security аудитах.

```dockerfile
COPY entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
```
**ENTRYPOINT + shell-скрипт** — реальный паттерн в этом проекте:
```bash
# entrypoint.sh
#!/bin/sh
set -e
echo "Running database migrations..."
alembic upgrade head
echo "Starting server..."
exec uvicorn main:app --host 0.0.0.0 --port 8000
```
Сначала прогоняем миграции (`alembic upgrade head`), потом запускаем сервер — это гарантирует что схема БД всегда актуальна при старте контейнера, а не только когда кто-то не забыл сделать это руками отдельным шагом.

**Зачем `exec` перед uvicorn.** Без `exec` uvicorn запустился бы как дочерний процесс shell-скрипта — `docker stop` отправил бы SIGTERM самому entrypoint.sh, а не uvicorn, и приложение могло не успеть корректно завершиться. `exec` заменяет процесс shell-скрипта процессом uvicorn — тот становится PID 1 и получает сигналы напрямую. Тот же принцип, что у exec-form vs shell-form в CMD/ENTRYPOINT.

`--host 0.0.0.0` — слушать на всех сетевых интерфейсах контейнера. Если написать `127.0.0.1` (localhost) — снаружи контейнера приложение будет недоступно, nginx не сможет к нему подключиться.

**ENTRYPOINT vs CMD:**
- `ENTRYPOINT` — неизменяемая точка входа. В нашем Dockerfile это `/bin/sh /entrypoint.sh` — всегда прогоняет миграции перед стартом, это нельзя случайно перезаписать при `docker run <image> <другая-команда>`.
- `CMD` — команда по умолчанию, легко переопределяется при `docker run`. В этом Dockerfile `CMD` не используется вообще — вся логика запуска (миграции → сервер) зафиксирована в ENTRYPOINT.
- Частый альтернативный паттерн — `ENTRYPOINT ["python3"]` + `CMD ["main.py"]`, где ENTRYPOINT фиксирует интерпретатор, а CMD (аргумент) легко переопределить.

**EXPOSE — документация, не конфигурация.** В этом Dockerfile инструкции `EXPOSE` нет вообще — она необязательна и ничего не открывает функционально. Если бы она была (`EXPOSE 8000`), это была бы просто подсказка читателю "контейнер слушает на 8000". Реальное открытие порта происходит только через `docker run -p` или `ports:` в docker-compose.yml.

**Итого — почему именно такой порядок в Dockerfile:**
```
FROM        ← 1. Базовая среда
WORKDIR     ← 2. Рабочая директория
COPY req    ← 3. Зависимости (редко меняются)
RUN pip     ← 4. Установка зависимостей (кэшируется)
COPY .      ← 5. Код (часто меняется — в конце)
RUN chown   ← 6. Права на файлы для непривилегированного пользователя
USER        ← 7. Переключить на непривилегированного пользователя
ENTRYPOINT  ← 8. Команда запуска (миграции → сервер)
```

---

#### Практика

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

### Ключевые команды уровня 1.1

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `docker build -t <name> <dir>` | Собрать образ из Dockerfile | `docker build -t bulletin-backend ./backend` |
| `docker run -d -p <host>:<cont> <image>` | Запустить контейнер в фоне | `docker run -d -p 8000:8000 bulletin-backend` |
| `docker ps` | Список запущенных контейнеров | `docker ps` |
| `docker logs <name>` | Логи контейнера | `docker logs my-backend` |
| `docker exec -it <name> bash` | Зайти внутрь | `docker exec -it my-backend bash` |
| `docker stop <name>` | Остановить контейнер | `docker stop my-backend` |
| `docker rm <name>` | Удалить контейнер | `docker rm my-backend` |

---

### 1.2 — Добавляем PostgreSQL: проблема данных

#### Зачем

Ты остановил контейнер командой выше — и все данные исчезли. SQLite файл был внутри контейнера, который ты удалил. Для реального приложения нужна база которая **переживает** перезапуск.

Но и это не всё: база данных — отдельный сервис. Запускать postgres вручную перед бэкендом каждый раз — боль. Нужно описать весь стек и запускать одной командой.

**Docker Compose** — инструмент для описания многоконтейнерных приложений в одном `docker-compose.yml`.

#### Как это работает

Analogy: Docker Compose — это дирижёр оркестра. Каждый музыкант (контейнер) умеет играть сам, но дирижёр говорит кому начинать первым (depends_on), в каком темпе (resource limits) и как они слышат друг друга (networks).

---

#### Анатомия docker-compose.yml

```yaml
services:
```
Корневой раздел. Всё что внутри — описание отдельных контейнеров. До версии Compose v2 был обязательный заголовок `version: '3.8'` — сейчас он устарел и игнорируется.

```yaml
  postgres:
    image: postgres:16-alpine
```
`image:` — использовать готовый образ из Docker Hub (не собирать). `postgres:16-alpine` — PostgreSQL версии 16 на Alpine Linux (~80 МБ против ~400 МБ для `postgres:16`). Для базы данных Alpine безопасен — там нет Python-пакетов с проблемами совместимости.

```yaml
    environment:
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
      POSTGRES_DB: bulletin_board
```
Переменные окружения, которые читает образ при первом старте для создания базы и пользователя. Эти конкретные переменные — часть официального postgres образа, задокументированы в Docker Hub.

**Почему не хранить пароли в файле?** Для разработки — допустимо. Для production — переменные должны приходить из внешнего хранилища секретов (Vault, AWS Secrets Manager). В compose можно использовать `environment: POSTGRES_PASSWORD: ${DB_PASSWORD}` — значение берётся из `.env` файла или переменной оболочки.

```yaml
    healthcheck:
      test: ["CMD", "pg_isready", "-U", "postgres"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 10s
```
**Зачем healthcheck?** Docker считает контейнер "запущенным" как только процесс стартовал. Но PostgreSQL нужно несколько секунд чтобы инициализировать файлы данных и начать принимать соединения. Без healthcheck backend стартует сразу, пытается подключиться к postgres — получает `connection refused` и падает.

- `test` — команда проверки. `pg_isready` — утилита из postgresql-client, проверяет готовность принимать соединения.
- `interval: 5s` — проверять каждые 5 секунд.
- `timeout: 5s` — если проверка не ответила за 5 секунд — считается провалом.
- `retries: 5` — после 5 провалов подряд контейнер переходит в статус `unhealthy`.
- `start_period: 10s` — первые 10 секунд провалы не считаются. Дать postgres время на инициализацию без немедленного unhealthy.

```yaml
    volumes:
      - postgres_data:/var/lib/postgresql/data
```
Монтирует именованный volume в директорию где postgres хранит данные. `/var/lib/postgresql/data` — это хардкодированный путь внутри образа postgresql.

**Именованный volume** (`postgres_data:`) vs **bind mount** (`./data:/var/lib/postgresql/data`):
- Именованный — Docker управляет где физически хранится. Переносимо, изолировано.
- Bind mount — монтируешь конкретную директорию с хоста. Удобно для разработки (код живёт в ./backend, правки сразу видны внутри).

```yaml
    restart: unless-stopped
```
Политика перезапуска контейнера:
- `no` — никогда не перезапускать (умер — умер)
- `always` — всегда перезапускать, даже если вручную остановил
- `unless-stopped` — перезапускать при сбое, но не если вручную остановил через `docker compose stop`
- `on-failure` — только при ненулевом exit code (значит приложение само упало, не было остановлено)

`unless-stopped` — стандартный выбор для production-подобных сред.

```yaml
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
```
`build:` — собрать образ из Dockerfile, а не тянуть готовый. `context: ./backend` — директория которая отправляется Docker daemon как "контекст сборки". Все пути в `COPY` внутри Dockerfile — относительно этой директории. Если написать `context: .` — весь проект попадёт в контекст (медленно, `node_modules` и `.git` уйдут в daemon).

```yaml
    depends_on:
      postgres:
        condition: service_healthy
```
Бэкенд не стартует пока postgres не пройдёт healthcheck. `condition: service_healthy` vs просто `depends_on: postgres` (без condition) — без condition Docker только ждёт старта процесса, не его готовности. С condition — ждёт `healthy` статуса.

```yaml
    networks:
      - internal
```
Контейнеры в одной сети видят друг друга по имени сервиса (`postgres`, `backend`, `nginx`). Без явного указания сети — Compose создаёт сеть по умолчанию, все контейнеры в ней. Явное указание нужно когда хочешь изолировать группы: например nginx в `external` сети (доступен снаружи), а postgres только во `internal` (недоступен снаружи).

```yaml
volumes:
  postgres_data:
```
Объявление именованных volumes. Без этого раздела использование `postgres_data:` в сервисе — ошибка. Можно добавить `external: true` если volume создан за пределами compose.

---

#### Практика

**Шаг 1 — Прочитать docker-compose.yml**

```bash
cat docker-compose.yml
```

Найди в файле и объясни себе:
- `depends_on: condition: service_healthy` — что это?
- `healthcheck` у postgres — зачем?
- `volumes: postgres_data:` внизу файла — что происходит с данными при `docker compose down`?

**Шаг 2 — Запустить стек с базой**

```bash
docker compose up --build -d

# Следить за стартом
docker compose logs -f
```

Что искать в логах:
```
level-1-monolith-postgres-1  | database system is ready to accept connections
level-1-monolith-backend-1   | Running database migrations...
level-1-monolith-backend-1   | INFO  [alembic.runtime.migration] Running upgrade -> 001
level-1-monolith-backend-1   | Application startup complete.
```

**Шаг 3 — Зайти в PostgreSQL напрямую**

```bash
docker compose exec postgres psql -U postgres -d bulletin_board

# Внутри psql:
\dt                    -- список таблиц
\d ads                 -- структура таблицы ads
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

---

#### Что сломать намеренно — 1.2

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

### 1.3 — Добавляем Nginx: зачем прокси перед Python

#### Зачем

Сейчас бэкенд слушает на порту 8000 и сам отдаёт и API, и статику. Проблемы:
- Python-сервер (uvicorn) **плохо справляется с тысячами медленных клиентов** — он блокируется на каждом соединении
- Статичные файлы (HTML/CSS/JS) Python читает с диска при каждом запросе — медленно и дорого
- Нет точки для SSL-терминации, gzip, rate limiting, логирования доступа

**Nginx** — высокопроизводительный асинхронный сервер на C. Держит 10,000 соединений с минимальным потреблением памяти. Отдаёт статику из RAM. Python-процесс получает только то, что умеет делать — бизнес-логику.

#### Как это работает

Nginx — вахтёр на входе в здание. Посетители приходят к нему: кому нужен склад (статика — сам выдаёт), кому нужен менеджер (API — провожает к бэкенду). Без вахтёра — менеджер (Python) сам встречает всех и отвлекается на каждого.

---

#### Анатомия nginx.conf (монолит)

```nginx
worker_processes auto;
```
Количество рабочих процессов Nginx. `auto` — по числу CPU-ядер. Каждый worker обрабатывает тысячи соединений асинхронно (event loop). Не путай с Apache где один процесс = одно соединение.

```nginx
events {
    worker_connections 1024;
}
```
Максимальное количество одновременных соединений на один worker. При `worker_processes auto` на 4-ядерном сервере = 4 × 1024 = 4096 соединений всего. Для production с высокой нагрузкой увеличивают до 4096 или 10240.

```nginx
http {
    include       /etc/nginx/mime.types;
    default_type  application/octet-stream;
```
`mime.types` — таблица соответствий расширений файлов и Content-Type заголовков. Без неё браузер не знает что `.js` — это JavaScript, скачает как файл вместо выполнения. `default_type` — если расширение не в таблице — отдаём как бинарный файл.

```nginx
    sendfile on;
    tcp_nopush on;
```
`sendfile on` — использует системный вызов `sendfile()` для передачи файлов напрямую из файловой системы в сокет, минуя userspace. Значительно быстрее при отдаче статики. `tcp_nopush` — собирает HTTP-заголовок и начало файла в один TCP-пакет. Уменьшает число пакетов.

```nginx
    gzip on;
    gzip_types text/plain text/css application/javascript application/json;
    gzip_min_length 1024;
```
Сжатие ответов на лету. Текст и JSON сжимаются в 3-10 раз. `gzip_min_length 1024` — не сжимать файлы меньше 1 КБ (сжатие тратит CPU, для маленьких файлов выигрыш минимален).

```nginx
    server {
        listen 80;
        server_name _;
```
`listen 80` — принимать соединения на порту 80 (HTTP). `server_name _` — виртуальный хост-перехватчик: принимать запросы с любым Host заголовком. При нескольких `server {}` блоках Nginx выбирает нужный по `server_name`.

```nginx
        location / {
            root /usr/share/nginx/html;
            try_files $uri $uri/ /index.html;
        }
```
`location /` — блок обработки для всех запросов не попавших в более специфичные блоки ниже. `root` — физическая директория с файлами. `try_files $uri $uri/ /index.html` — логика:
1. Попробовать отдать файл `$uri` (например `/style.css` → файл `style.css`)
2. Попробовать как директорию `$uri/` (ищет `index.html` внутри)
3. Если ничего не нашёл — отдать `/index.html`

Третий вариант — паттерн для SPA (Single Page Application). React/Vue роутинг работает на стороне браузера, все URL должны возвращать `index.html`.

```nginx
        location /api/ {
            proxy_pass http://backend:8000;
            proxy_set_header Host              $host;
            proxy_set_header X-Real-IP         $remote_addr;
            proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
```
`location /api/` — более специфичный блок, перехватывает все запросы начинающиеся с `/api/`. Nginx выбирает самый длинный подходящий prefix.

`proxy_pass http://backend:8000` — перенаправить запрос на бэкенд. `backend` — DNS-имя внутри Docker-сети (имя сервиса в docker-compose.yml).

**Почему нужны эти заголовки:**
- `Host: $host` — передаём оригинальный хост запроса. Без этого бэкенд видит `backend:8000` вместо `example.com`.
- `X-Real-IP: $remote_addr` — реальный IP клиента. Без него бэкенд видит IP nginx (172.x.x.x) вместо IP пользователя. Важно для логов, rate limiting, геолокации.
- `X-Forwarded-For` — список всех прокси через которые прошёл запрос. При нескольких уровнях прокси: `X-Forwarded-For: client_ip, proxy1_ip`.
- `X-Forwarded-Proto: $scheme` — был ли оригинальный запрос http или https. Нужен бэкенду чтобы генерировать правильные ссылки в ответах (redirect на https, а не http).

```nginx
        proxy_connect_timeout 5s;
        proxy_read_timeout    30s;
```
`proxy_connect_timeout` — сколько ждать установки соединения с бэкендом. 5 секунд — если бэкенд не отвечает 5 секунд — ошибка 502. `proxy_read_timeout` — сколько ждать ответа от бэкенда после отправки запроса. 30 секунд — для медленных операций (загрузка файла, сложный запрос к БД).

---

#### Практика

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

### 1.4 — Полный монолит: JWT и миграции

#### Практика: полный цикл работы с API

```bash
# Зарегистрироваться
curl -s -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123","email":"alice@test.com"}' \
  | python3 -m json.tool

# Получить токен
TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

echo "Token: $TOKEN"

# Создать объявление (с токеном)
curl -s -X POST http://localhost/api/ads \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"title":"Продам велосипед","description":"Почти новый","price":5000}' \
  | python3 -m json.tool

# Получить список (без токена — публично)
curl -s http://localhost/api/ads | python3 -m json.tool

# Попробовать создать без токена — должна быть ошибка 401
curl -s -X POST http://localhost/api/ads \
  -H "Content-Type: application/json" \
  -d '{"title":"test","description":"test","price":1}'
# {"detail":"Authentication required"}
```

**Разобрать JWT:**

```bash
# JWT состоит из трёх частей: header.payload.signature
# Payload не зашифрован — только подписан!
echo $TOKEN | cut -d'.' -f2 | base64 -d 2>/dev/null | python3 -m json.tool
```

```json
{
    "sub": "1",
    "username": "alice",
    "exp": 1234567890
}
```

**Задание:** `SECRET_KEY` читается из переменной окружения с дефолтом `dev-only-change-in-production` (`auth.py`) — в docker-compose.yml её сейчас нет вообще. Добавь `SECRET_KEY: some-other-value` в `environment:` бэкенда, перезапусти, попробуй использовать старый токен. Что произошло и почему?

---

### Нагрузочный тест — видим боль

```bash
# Терминал 1: смотрим ресурсы
docker stats

# Терминал 2: лёгкий тест
k6 run load-tests/smoke.js

# Терминал 2: стресс-тест
k6 run load-tests/stress.js
```

**Что смотреть в docker stats:**
- `CPU %` у `backend` — растёт при нагрузке
- `MEM USAGE` — должна быть стабильной

**Что смотреть в k6:**
- `http_req_duration p(95)` — время ответа у 95% запросов
- `http_req_failed` — процент ошибок

**Боль которую ты видишь:** при 50+ VU один Python-процесс начинает задыхаться. Время ответа растёт. Появляются 502. Это и есть мотивация для Уровня 2.

---

### Что сломать намеренно — Уровень 1

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

**OOM Killer** (Out of Memory Killer) — механизм ядра Linux который убивает процессы при нехватке физической памяти. Он посылает SIGKILL — принудительное завершение без возможности cleanup. Exit code **137** (= 128 + 9) — это его подпись.

Добавь к секции `backend` в `docker-compose.yml`:
```yaml
mem_limit: 150m
memswap_limit: 150m   # отключаем swap — OOM наступит предсказуемо
```

```bash
docker compose up -d

# Терминал 1: смотреть память в реальном времени
docker stats

# Терминал 2: выделяем +1 MB каждые 0.2 секунды
docker compose exec backend python3 -c "
import time
data = []
for i in range(1000):
    data.append(b'x' * 1024 * 1024)
    print(f'Выделено: {i+1} MB', flush=True)
    time.sleep(0.2)
"
```

**Что диагностировать:**
```bash
docker compose ps
# backend   Exit 137      ← OOM Kill

# Подтверждение от ядра:
sudo dmesg | grep -i "killed process\|out of memory" | tail -5
# [12345.678] Killed process 9876 (python3) total-vm:...
```

**Почему это важно:** без `mem_limit` OOM Killer выбирает жертву сам — может убить PostgreSQL вместо виновного бэкенда. С лимитами — умирает виновник, остальные живут.

**Верни:** убери `mem_limit` и `memswap_limit` из `docker-compose.yml`.

**Поломка 4 — Сломать миграцию**

Открой `backend/alembic/versions/001_initial_schema.py`, измени `ads` на `advertisements` в CREATE TABLE. Запусти `docker compose up --build -d`. Что произойдёт с уже существующими данными? Что в логах?

---

### Справочник команд — Уровень 1

| Команда | Описание |
|---------|---------|
| `docker build -t bulletin-backend ./backend` | Собрать образ бэкенда |
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

### На собеседовании спросят

**Q: Чем контейнер отличается от виртуальной машины?**
A: ВМ эмулирует полное железо + отдельное ядро ОС — тяжёлая, гигабайты RAM. Контейнер использует ядро хоста, изолирован через namespaces и cgroups — лёгкий, мегабайты RAM, стартует за секунды.

**Q: Что такое Docker volume и зачем он нужен?**
A: Volume — хранилище данных вне контейнера. Контейнер эфемерен (данные теряются при удалении). Volume переживает перезапуск и удаление контейнера. PostgreSQL хранит данные в volume.

**Q: Зачем Nginx перед Python-приложением?**
A: Nginx (async, C) держит тысячи соединений, отдаёт статику, умеет gzip, rate limiting. Python-сервер (uvicorn) лучше справляется с бизнес-логикой, но плохо с медленными клиентами.

**Q: Что такое JWT?**
A: Три части: header (алгоритм), payload (данные), signature (HMAC от header+payload с secret). Сервер проверяет подпись — если сошлась, доверяет данным из payload. Stateless: сервер не хранит сессии.

**Q: Что означает `depends_on: condition: service_healthy`?**
A: Бэкенд стартует только после того как postgres прошёл healthcheck (`pg_isready`). Без этого бэкенд стартует раньше postgres и падает с ошибкой коннекта.

---

### Итог уровня 1

Ты умеешь:
- [ ] Запустить многоконтейнерное приложение одной командой
- [ ] Читать логи и понимать sequence запуска
- [ ] Работать с базой напрямую через psql
- [ ] Использовать curl для тестирования API
- [ ] Понимать как работает JWT
- [ ] Запустить нагрузочный тест и читать его вывод
- [ ] Видеть деградацию под нагрузкой

**Боль которую ты чувствуешь:** один Python-процесс не справляется с 50+ пользователями. Очевидное решение — запустить несколько копий. Переходим к Уровню 2.

---

## Уровень 2 — Горизонтальное масштабирование

### Зачем это нужно

Ты видел: при 50+ VU время ответа деградирует. Первая мысль — "возьмём сервер помощнее". Это **вертикальное масштабирование** (scale up). Работает, но:
- Серверы большого размера стоят непропорционально дорого
- Есть физический предел — самое мощное железо всё равно не справится с YouTube-нагрузкой
- Один сервер = одна точка отказа. Упал — всё упало

**Горизонтальное масштабирование (scale out)** — запускаем 3 копии бэкенда. Нагрузка делится. Упала одна копия — две работают.

Но вот что интересно: горизонтальное масштабирование бесплатным не бывает. Оно вскрывает архитектурные проблемы которых в монолите не было видно.

### Как это работает

Один повар не справляется — нанимаем трёх поваров. Но теперь нужен метрдотель (Nginx upstream) который распределяет заказы. И каждый повар думает независимо: если повар №2 запомнил что клиент Иван хочет без лука, а заказ пришёл к повару №3 — он этого не знает.

Это проблема **stateful** приложений при масштабировании. JWT решает её: токен несёт всю информацию сам, никто ничего не должен "помнить".

---

### Балансировка в nginx.conf — что есть, и что можно добавить

Наш реальный `nginx.conf` — минимальный:
```nginx
upstream backend {
    server backend_1:8000;
    server backend_2:8000;
    server backend_3:8000;
}
```
`upstream` — группа серверов для балансировки. Nginx распределяет запросы между ними.

**Алгоритмы балансировки** (директива внутри upstream блока):
- По умолчанию (ничего не указано, как у нас) — **round-robin**: запросы по кругу. backend_1 → backend_2 → backend_3 → backend_1...
- `least_conn;` — на сервер с наименьшим числом активных соединений. Лучше чем round-robin когда запросы имеют разное время выполнения (одни быстрые, другие медленные).
- `ip_hash;` — хэш от IP клиента, один клиент всегда попадает на один сервер. Нужно для stateful сессий в памяти. Но если backend_2 упал — все его клиенты "потеряны".
- `random;` — случайный выбор.

**Ниже — директивы, которых в нашем `nginx.conf` нет, но полезно знать (пригодятся когда захочешь усложнить конфиг):**

```nginx
    keepalive 32;
```
Пул до 32 постоянных HTTP-соединений к каждому бэкенду. Без keepalive: для каждого запроса — новое TCP-соединение (3-way handshake: SYN → SYN-ACK → ACK). При 100 RPS это 100 рукопожатий в секунду. С keepalive — соединение переиспользуется, лишние ~1ms на каждый запрос экономятся.

```nginx
    server backend_1:8000 weight=3;
    server backend_2:8000 weight=1;
```
`weight` — вес при round-robin. backend_1 получит 75% запросов, backend_2 — 25%. Нужно когда серверы разной мощности. В нашем случае все три инстанса одинаковые — weight не используем.

```nginx
    server backend_2:8000 max_fails=3 fail_timeout=30s;
```
**Passive health check** (всегда работает, бесплатно):
- `max_fails=3` — после 3 провалов подряд сервер помечается как недоступный.
- `fail_timeout=30s` — исключить из ротации на 30 секунд, потом попробовать снова.
- Nginx ждёт реальных ошибок от живых запросов — не ходит проверять сам по расписанию.

**Active health check** (только в NGINX Plus, платный): Nginx сам периодически ходит на `/api/health` у каждого бэкенда независимо от трафика. Бесплатная альтернатива в open-source — переложить на Kubernetes readiness probe.

**А это в нашем `nginx.conf` реально есть:**
```nginx
        proxy_next_upstream error timeout http_502 http_503;
```
Если бэкенд вернул ошибку, повторить запрос на следующий сервер:
- `error` — ошибка TCP-соединения (бэкенд недоступен)
- `timeout` — превышено время ожидания
- `http_502`, `http_503` — бэкенд вернул 502/503

Опционально можно добавить `proxy_next_upstream_tries 3` — ограничить число попыток (без ограничения при падении всех бэкендов Nginx будет крутиться бесконечно), у нас этого ограничения пока нет.

**Осторожно с POST:** `proxy_next_upstream non_idempotent` позволяет retry для POST. Опасно — запрос может выполниться дважды (два созданных объявления). Включай только если бэкенд использует идемпотентный ключ для защиты.

---

### Ключевые команды

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `docker compose up --scale backend=3` | Запустить 3 копии (если настроено) | — |
| `docker compose stop backend_2` | Остановить конкретный инстанс | `docker compose stop backend_2` |
| `docker compose start backend_2` | Запустить обратно | `docker compose start backend_2` |
| `docker compose exec backend_1 ps aux` | Процессы внутри инстанса | — |
| `docker compose exec postgres psql ... -c "SELECT count(*), state FROM pg_stat_activity..."` | Коннекты к БД | — |

### Практика

**Шаг 1 — Разобрать конфиг перед запуском**

```bash
cd level-2-scaling
cat nginx/nginx.conf
```

Найди блок `upstream backend` — три сервера перечислены явно. Найди `proxy_next_upstream error timeout` — что будет если backend_2 упадёт прямо во время запроса?

**Шаг 2 — Запустить**

```bash
docker compose up --build -d
docker compose ps
```

Ожидаешь увидеть 5 контейнеров: nginx, postgres, backend_1, backend_2, backend_3.

**Шаг 3 — Убедиться что балансировка работает**

```bash
for i in $(seq 1 9); do
  curl -s http://localhost/api/instance \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['instance_id'])"
done
```

Увидишь чередование: backend_1, backend_2, backend_3, backend_1... Это round-robin.

**Шаг 4 — Проверить что JWT работает на любом инстансе**

```bash
# Токен создан на backend_1 (возможно), но проверяется на backend_2 и backend_3
TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# Создать 3 объявления — каждый запрос попадёт на другой инстанс
for i in 1 2 3; do
  curl -s -X POST http://localhost/api/ads \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"title\":\"Объявление $i\",\"description\":\"Тест\",\"price\":$((i*100))}" \
    | python3 -m json.tool
done
```

Все три создались — JWT проверяется на разных инстансах, потому что `SECRET_KEY` одинаковый.

**Шаг 5 — Убить инстанс под нагрузкой (ключевая демонстрация)**

```bash
# Терминал 1: нагрузочный тест
k6 run load-tests/balancer-test.js

# Терминал 2: убиваем backend_2 ПОКА ТЕСТ РАБОТАЕТ
docker compose stop backend_2
```

Наблюдай в Терминале 1: кратковременный всплеск ошибок (1-2 секунды) — потом нормализуется. Nginx перестал посылать запросы на упавший инстанс.

```bash
# Вернуть инстанс
docker compose start backend_2
```

После запуска Nginx автоматически снова включит его в ротацию.

**Шаг 6 — Сравнить с Уровнем 1**

```bash
# Два терминала:
docker stats          # Терминал 1
k6 run load-tests/stress.js  # Терминал 2
```

Смотри: нагрузка CPU распределяется между backend_1/2/3. Но CPU у postgres растёт. Три инстанса = в три раза больше запросов к базе. PostgreSQL один — он становится новым узким местом.

---

### Что сломать намеренно — Уровень 2

**Поломка 1 — Разные SECRET_KEY на инстансах**

В `docker-compose.yml` добавь `SECRET_KEY` в `environment:` у `backend_2` со значением, отличным от остальных (по умолчанию везде используется одно и то же `dev-only-change-in-production` из `auth.py`, в файле переменная не задана). Запусти. Залогинься (токен выдан на backend_1 или backend_3). Потом делай запросы — каждый третий будет падать с 401, когда попадёт на backend_2.

**Диагностика:**
```bash
docker compose logs backend_2 | grep -i "invalid\|signature\|error"
# JWTError: Signature verification failed
```

**Поломка 2 — Отключить proxy_next_upstream**

Закомментируй строку `proxy_next_upstream error timeout;` в nginx.conf. Перезапусти nginx: `docker compose restart nginx`. Убей backend_2. Запусти k6. Теперь каждый третий запрос попадает на мёртвый сервер и получает 502 — без retry.

**Диагностика:** `docker compose logs nginx | grep 502`

**Поломка 3 — Исчерпать пул соединений к БД**

В `backend/main.py` измени `pool_size=5` на `pool_size=1`. Пересобери. Запусти стресс-тест. При высокой нагрузке увидишь `QueuePool limit of size 1 overflow 10 reached`.

```bash
docker compose exec postgres psql -U postgres -d bulletin_board \
  -c "SELECT count(*), state FROM pg_stat_activity WHERE datname='bulletin_board' GROUP BY state;"
```

---

> **Как в проде:** в реальных компаниях вместо 3 хардкодированных сервисов используют service discovery (Consul, Kubernetes DNS). Nginx не знает IP заранее — получает актуальный список при каждом запросе. При масштабировании добавляют инстанс, он регистрируется — nginx автоматически начинает посылать на него трафик.

---

### Справочник команд — Уровень 2

| Команда | Описание |
|---------|---------|
| `docker compose ps` | Статус всех инстансов |
| `docker compose stop backend_2` | Выключить один инстанс |
| `docker compose start backend_2` | Включить обратно |
| `docker compose logs backend_1 backend_2 backend_3 \| grep -i error` | Только ошибки |
| `curl -s http://localhost/api/instance` | Какой инстанс ответил |
| `docker compose exec postgres psql -U postgres -d bulletin_board -c "SELECT ..."` | Запрос к БД |

### Итог уровня 2

Ты умеешь:
- [ ] Настроить Nginx upstream с несколькими серверами
- [ ] Убить контейнер под нагрузкой и наблюдать failover
- [ ] Объяснить почему JWT работает при scale-out а сессии в памяти — нет
- [ ] Находить узкое место после решения предыдущего

**Боль которую ты чувствуешь:** при 100 RPS три инстанса делают 100 запросов к PostgreSQL. При `GET /api/ads` каждый раз — JOIN + ORDER BY + весь список. PostgreSQL задыхается. Кэширование → Уровень 3.

---

## Уровень 3 — Кэширование и оптимизация БД

### Зачем это нужно

Три бэкенда хорошо делят нагрузку. Но PostgreSQL один. При 100 RPS — 100 запросов в секунду к базе. `GET /api/ads` делает JOIN + ORDER BY + перебирает всю таблицу. Список объявлений меняется раз в несколько минут, а читается тысячи раз.

**Зачем каждый раз идти в БД если данные не менялись последние 30 секунд?**

Redis — быстрое in-memory хранилище (~0.1ms vs ~10ms у PostgreSQL). Кладём туда результат запроса на 30 секунд. 99% запросов идут в Redis, не в PostgreSQL.

### Как это работает

У нас есть справочная (PostgreSQL) — туда за каждым ответом ходить долго. Но у входа висит доска объявлений (Redis) — туда раз в 30 секунд переписывают самую популярную информацию. 99% посетителей получают ответ у доски мгновенно. Только при изменении — обновляем доску.

### Ключевые понятия

| Термин | Что означает |
|--------|-------------|
| **Cache HIT** | Данные нашлись в Redis — PostgreSQL не трогаем |
| **Cache MISS** | В Redis пусто — идём в PostgreSQL, результат кладём в кэш |
| **Cache invalidation** | При изменении данных удаляем ключ из Redis |
| **TTL** | Время жизни ключа в кэше (у нас 30 секунд) |

### Практика

**Шаг 1 — Понять паттерн в коде**

```bash
cd level-3-caching
cat backend/main.py
```

Найди функцию `list_ads()`:
```python
cached = cache.get("ads:list")      # 1. Проверяем Redis
if cached:
    return json.loads(cached)        # 2. HIT — возвращаем без БД

rows = db.execute(...)               # 3. MISS — идём в PostgreSQL
cache.setex("ads:list", 30, ...)    # 4. Сохраняем на 30 секунд
```

Найди `create_ad()` — там `cache.delete("ads:list")`. Что произойдёт если убрать эту строку? Как долго новое объявление будет невидимо?

**Шаг 2 — Запустить**

```bash
docker compose up --build -d

# Проверить Redis
docker compose exec redis redis-cli ping
# PONG
```

**Шаг 3 — Наблюдать кэш в реальном времени**

```bash
# Терминал 1: мониторинг Redis
docker compose exec redis redis-cli monitor

# Терминал 2: запросы
curl -s http://localhost/api/ads > /dev/null  # MISS
curl -s http://localhost/api/ads > /dev/null  # HIT
curl -s http://localhost/api/ads > /dev/null  # HIT
```

В Терминале 1 при MISS видишь:
```
GET "ads:list"    → (nil)
SETEX "ads:list" 30 "[...]"
```
При HIT:
```
GET "ads:list"    → "[{...}]"
```

**Шаг 4 — Работать с Redis напрямую**

```bash
docker compose exec redis redis-cli
```

```
KEYS *                     # все ключи
GET ads:list               # содержимое
TTL ads:list               # секунд до истечения
INFO stats                 # keyspace_hits / keyspace_misses
DEL ads:list               # принудительная инвалидация
quit
```

**Задание:** создай объявление через curl, потом проверь `KEYS *`. Ключ `ads:list` должен исчезнуть — инвалидация сработала.

**Шаг 5 — Замерить разницу в скорости**

```bash
# Прогреть кэш
curl -s http://localhost/api/ads > /dev/null

# Тест с прогретым кэшем — запиши p95
k6 run load-tests/cache-test.js

# Сбросить кэш
docker compose exec redis redis-cli FLUSHALL

# Тест без кэша — сравни p95
k6 run load-tests/cache-test.js
```

Ожидаемая разница: p95 в 5-20 раз меньше при прогретом кэше.

**Шаг 6 — Посмотреть hit rate**

```bash
curl -s http://localhost/api/cache-stats | python3 -m json.tool
```

```json
{
    "hits": 142,
    "misses": 7,
    "hit_rate_percent": 95.3
}
```

**Хороший hit rate** — 90%+. Это значит 90% запросов не трогают PostgreSQL.

**Шаг 7 — Медленные запросы и индексы**

```bash
# Включить логирование всех запросов
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  ALTER SYSTEM SET log_min_duration_statement = 0;
  SELECT pg_reload_conf();
"

# Сбросить кэш и сделать несколько запросов
docker compose exec redis redis-cli FLUSHALL
curl -s http://localhost/api/ads > /dev/null

# Посмотреть логи
docker compose logs postgres | grep "duration"
# duration: 12.341 ms  statement: SELECT a.id, a.title...
```

```bash
# Посмотреть план выполнения запроса
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  EXPLAIN ANALYZE
  SELECT a.id, a.title, a.price, u.username, a.created_at
  FROM ads a LEFT JOIN users u ON a.user_id = u.id
  ORDER BY a.created_at DESC;
"
```

Ищи в выводе:
- `Index Scan using ix_ads_created_at` — хорошо, индекс используется
- `Seq Scan on ads` — плохо, полный перебор таблицы

```bash
# Сравни что будет без индекса
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  DROP INDEX ix_ads_created_at;
  EXPLAIN ANALYZE SELECT a.id, a.title FROM ads a ORDER BY a.created_at DESC;
"
# Теперь: Seq Scan — медленно

# Вернуть индекс
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  CREATE INDEX ix_ads_created_at ON ads(created_at DESC);
"
```

---

### Что сломать намеренно — Уровень 3

**Поломка 1 — Убрать инвалидацию**

В `backend/main.py` закомментируй `cache.delete("ads:list")` в функции `create_ad()`. Пересобери. Создай объявление — оно не появится в списке ещё 30 секунд (до истечения TTL). Это классическая ошибка которую делают при первом знакомстве с кэшем.

**Диагностика:** `docker compose exec redis redis-cli TTL ads:list` — сколько секунд до обновления.

**Поломка 2 — FLUSHALL в "production"**

Запусти нагрузочный тест. В другом терминале выполни `docker compose exec redis redis-cli FLUSHALL`. Смотри на k6 — всплеск latency (все запросы пошли в PostgreSQL одновременно). Это "thundering herd" — гром стада.

**Диагностика:** `docker stats` — CPU postgres резко вырастет в момент FLUSHALL.

**Поломка 3 — Redis упал**

```bash
docker compose stop redis
curl -s http://localhost/api/ads
# Что произошло? Зависит от graceful degradation в коде
docker compose logs backend | tail -20
```

Если в коде нет try/except вокруг Redis — сервис упадёт. Если есть — сервис деградирует (работает медленнее но не падает). **Урок:** кэш — не критичная часть архитектуры, сервис должен работать без него.

---

> **Как в проде:** в крупных компаниях используют Redis Cluster для высокой доступности (несколько шардов, репликация). TTL для разных типов данных разный: список объявлений — 30с, страница конкретного объявления — 5 минут, профиль пользователя — 1 час. Инвалидацию делают через Pub/Sub: при изменении данных публикуют событие, подписчики удаляют соответствующие ключи.

---

### Справочник команд — Уровень 3

| Команда | Описание |
|---------|---------|
| `docker compose exec redis redis-cli ping` | Проверить Redis |
| `docker compose exec redis redis-cli monitor` | Все команды в реальном времени |
| `docker compose exec redis redis-cli KEYS '*'` | Все ключи |
| `docker compose exec redis redis-cli GET ads:list` | Значение ключа |
| `docker compose exec redis redis-cli TTL ads:list` | Время жизни ключа |
| `docker compose exec redis redis-cli INFO stats` | Статистика hits/misses |
| `docker compose exec redis redis-cli FLUSHALL` | Очистить весь кэш (только dev!) |
| `EXPLAIN ANALYZE SELECT ...` | План выполнения запроса в PostgreSQL |
| `ALTER SYSTEM SET log_min_duration_statement = 100` | Логировать запросы дольше 100ms |

### На собеседовании спросят

**Q: Что такое cache invalidation и почему это сложно?**
A: Инвалидация — удаление устаревших данных из кэша. Сложность: нужно знать в точности когда данные изменились. Наш подход (delete при write) прост, но при высокой конкурентности возникает thundering herd — сотни запросов одновременно уходят в БД после инвалидации.

**Q: Чем Redis отличается от Memcached?**
A: Redis: персистентность, структуры данных (hash, list, set, sorted set), pub/sub, cluster, Lua. Memcached: только простой key-value, нет персистентности, чуть быстрее для простого случая. Сегодня Redis используют везде.

**Q: Что такое thundering herd?**
A: Истёк популярный ключ в кэше. 1000 параллельных запросов увидели Cache MISS и все пошли в БД. База получила 1000 одинаковых запросов. Решение: mutex lock — первый запрос идёт в БД, остальные ждут результата.

**Q: Чем pg_dump отличается от pg_basebackup?**
A: pg_dump — логический бэкап: SQL-команды для воссоздания структуры и данных. Портабелен, можно восстановить на другой версии PostgreSQL. pg_basebackup — физический бэкап: побайтовая копия файлов данных. Быстрее для больших баз, нужен для PITR (Point-in-Time Recovery). Для большинства задач используют pg_dump с `--format=custom` — позволяет выборочное восстановление таблиц.

**Q: Что такое RPO и RTO?**
A: RPO (Recovery Point Objective) — максимально допустимая потеря данных по времени. "Если база упала, сколько данных можем потерять?" При бэкапе раз в сутки — RPO=24h. RTO (Recovery Time Objective) — сколько времени допустимо для восстановления. "Через сколько минут сервис должен снова работать?" Эти метрики определяют стратегию бэкапов: чем меньше RPO — тем чаще бэкап и дороже.

### Итог уровня 3

Ты умеешь:
- [ ] Реализовать cache-aside pattern (check → miss → load → store)
- [ ] Инвалидировать кэш при изменении данных
- [ ] Читать статистику Redis и понимать hit rate
- [ ] Объяснить EXPLAIN ANALYZE и Seq Scan vs Index Scan
- [ ] Создать pg_dump бэкап и протестировать восстановление в отдельную БД
- [ ] Написать скрипт ротации бэкапов с cron
- [ ] Объяснить разницу RPO и RTO и как они влияют на стратегию бэкапов

**Боль которую ты чувствуешь:** при деплое новой версии бэкенда надо остановить все три инстанса — сервис недоступен несколько секунд (или минут). Нужен автоматический деплой без даунтайма → Уровень 4.

---

## Уровень 3.5 — HTTPS и TLS

### Зачем это нужно

Сейчас всё работает по HTTP. Браузер показывает "Not Secure". Пароли и токены летят в открытом виде. Любой кто находится в той же сети (например, в кафе) может перехватить запросы и прочитать JWT-токены.

HTTPS — HTTP поверх TLS. Трафик зашифрован, сервер аутентифицирован сертификатом.

Проблема: сертификаты стоят денег (раньше) или требуют сложной настройки. **Traefik** автоматически получает бесплатные сертификаты от Let's Encrypt и обновляет их — без единой команды с твоей стороны.

### Как это работает

Traefik — умный прокси-сервер. Он читает labels у Docker-контейнеров и автоматически настраивает маршруты. Увидел контейнер с `traefik.http.routers.backend.rule=Host('api.example.com')` — сам создаёт маршрут. Для HTTPS — сам запрашивает сертификат у Let's Encrypt через ACME-протокол.

### Практика

```bash
cd level-3.5-https
# Замени example.com на твой домен в docker-compose.yml
cat docker-compose.yml | grep "example.com"

docker compose up -d

# Traefik dashboard
curl http://localhost:8080/api/rawdata | python3 -m json.tool

# Проверить HTTPS
curl https://yourdomain.com/api/health
```

**Что должен увидеть:**
```
* SSL connection using TLSv1.3 / TLS_AES_256_GCM_SHA384
* Server certificate:
*   subject: CN=yourdomain.com
*   issuer: Let's Encrypt
```

> **Как в проде:** Let's Encrypt имеет rate limits — 5 сертификатов на домен в неделю. При тестировании всегда используй staging-сервер (`caServer: https://acme-staging-v02.api.letsencrypt.org/directory`). Для wildcard-сертификатов (*.example.com) нужна DNS-валидация.

---

## Уровень 4 — CI/CD

### Зачем это нужно

Сейчас деплой выглядит так: написал код → вручную подключился к серверу → `git pull` → `docker compose up --build -d`. Проблемы:
- Забыл запустить тесты перед деплоем — сломанный код ушёл на прод
- Деплой занимает 3-5 минут пока пересобирается образ — сервис недоступен
- Если что-то пошло не так — надо вручную откатывать
- Каждый разработчик деплоит по-своему

**CI/CD** автоматизирует весь путь: коммит → тесты → сборка образа → пуш в registry → деплой на сервер. Всё детерминировано, версионировано, воспроизводимо.

### Как это работает

CI/CD pipeline — конвейер на заводе. Сырой материал (код) попадает на первую станцию (тесты), потом на вторую (сборка), потом на третью (деплой). Если на любой станции бракованная деталь — конвейер останавливается, тревога, люди смотрят что пошло не так. Хорошая деталь проходит весь конвейер и появляется на полке (production).

### 4a — GitHub Actions

### Анатомия .github/workflows/deploy.yml

```yaml
name: Deploy Bulletin Board
```
Название workflow — отображается в GitHub Actions UI. Не влияет на логику.

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
```
**Триггеры** — когда запускать workflow:
- `push: branches: [main]` — при каждом пуше в ветку `main` (после мержа PR). Здесь запустятся и тесты, и деплой.
- `pull_request: branches: [main]` — при открытии/обновлении PR в `main`. Здесь запустятся только тесты (job `deploy` исключим через `if`). Нельзя деплоить каждый PR — только финальный мерж.

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
```
`jobs:` — параллельные или последовательные задачи. `runs-on: ubuntu-latest` — запускать на GitHub-hosted runner (виртуальная машина ubuntu). GitHub предоставляет бесплатно 2000 минут в месяц для публичных репо. Альтернатива: `self-hosted` — свой runner на своём сервере.

```yaml
    steps:
      - uses: actions/checkout@v4
```
`uses:` — использовать готовый action из GitHub Marketplace. `actions/checkout@v4` — клонировать репозиторий в рабочую директорию runner-а. Без этого шага код недоступен. `@v4` — конкретная версия action. Никогда не пиши `@main` — может сломаться в любой момент.

```yaml
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
          cache: 'pip'
```
`with:` — параметры для action. `cache: 'pip'` — кэшировать pip-зависимости между запусками. Если `requirements.txt` не изменился — pip install берётся из кэша (~30 секунд экономии).

```yaml
      - name: Run tests
        run: pytest level-4-cicd/tests/ -v
```
`run:` — выполнить shell-команды. В реальном пайплайне тесты вообще не поднимают базу: `level-4-cicd/tests/test_api.py` мокирует PostgreSQL и Redis через `unittest.mock` и просто присваивает `DATABASE_URL`/`REDIS_URL` фиктивные значения (`os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"`) — реального соединения не происходит. Это и есть идея unit-тестов: быстро, без инфраструктуры.

```yaml
  build:
    needs: test
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
```
`needs: test` — этот job запустится только после успешного завершения job `test`. `if: github.event_name == 'push'` — запускать сборку только при пуше (не при каждом PR). Экономит минуты GitHub Actions и не засоряет registry тестовыми образами.

```yaml
    steps:
      - uses: actions/checkout@v4

      - name: Log in to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
```
`${{ secrets.GITHUB_TOKEN }}` — автоматически создаваемый токен с доступом к ресурсам репозитория, включая GitHub Container Registry. Не нужно создавать вручную и класть в Secrets самому.

```yaml
      - name: Build and push Docker image
        uses: docker/build-push-action@v5
        with:
          context: level-3-caching/backend
          push: true
          tags: |
            ghcr.io/${{ github.repository }}/bulletin-board-backend:latest
            ghcr.io/${{ github.repository }}/bulletin-board-backend:sha-${{ github.sha }}
```
Два тега: `latest` — всегда последняя версия, `sha-<хэш>` — конкретный коммит. Тег по sha позволяет откатиться к точной версии: `docker pull ghcr.io/user/repo/bulletin-board-backend:sha-abc1234`.

**Между build и deploy в реальном пайплайне есть ещё job `scan`** — сканирует собранный образ через Trivy на CVE и блокирует деплой, если нашлись уязвимости уровня CRITICAL (`exit-code: '1'`). Итого пайплайн — четыре job: `test → build → scan → deploy`, а не три.

```yaml
  deploy:
    needs: [build, scan]
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - name: Deploy to server via SSH
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd ~/devops-project/level-3-caching
            echo ${{ secrets.GITHUB_TOKEN }} | docker login ghcr.io -u ${{ github.actor }} --password-stdin
            for instance in backend_1 backend_2 backend_3; do
              docker compose pull $instance
              docker compose up -d --no-deps $instance
              sleep 5
            done
```
`secrets.SERVER_SSH_KEY` — приватный ключ для SSH. Хранится зашифрованным в GitHub Secrets. Action устанавливает его во временный файл, подключается к серверу, выполняет `script`, удаляет ключ.

Rolling update: обновляем backend_1, ждём 5 секунд (даём время на прогрев), обновляем backend_2, потом backend_3. Во время обновления минимум два бэкенда всегда работают. Пользователи не замечают деплой.

---

#### Анатомия .gitlab-ci.yml

```yaml
stages:
  - test
  - build
  - deploy
```
Порядок выполнения этапов. Jobs одного stage запускаются параллельно. Jobs следующего stage — только после успешного завершения предыдущего. Если нужно принудительно последовательно — используй `needs:`.

```yaml
variables:
  BACKEND_IMAGE: $CI_REGISTRY_IMAGE/backend
```
`variables:` — переменные доступные во всех jobs. `$CI_REGISTRY_IMAGE` — автоматическая переменная GitLab: адрес образа в GitLab Registry (`registry.gitlab.com/user/project`).

```yaml
unit-tests:
  stage: test
  image: python:3.12-slim
  before_script:
    - pip install -r level-3-caching/backend/requirements.txt pytest httpx
  script:
    - pytest level-4-cicd/tests/ -v --tb=short
```
`image:` — Docker-образ в котором запускается job (GitLab Runner запускает все jobs в контейнерах). Реальный пайплайн также содержит соседний job `lint` (тот же stage `test`, прогоняет `ruff check`, с `allow_failure: true` — линтер не блокирует pipeline).

```yaml
build-backend:
  stage: build
  image: docker:27
  services:
    - docker:dind
  before_script:
    - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
  script:
    - docker build -t $BACKEND_IMAGE:$CI_COMMIT_SHA level-3-caching/backend/
    - docker push $BACKEND_IMAGE:$CI_COMMIT_SHA
  only:
    - main
```
`image: docker:27` + `services: docker:dind` — Docker-in-Docker: запускаем Docker внутри Docker-контейнера Runner-а, нужно для сборки образов прямо в GitLab CI. `$CI_REGISTRY_USER`, `$CI_REGISTRY_PASSWORD`, `$CI_REGISTRY` — автоматические переменные GitLab для авторизации во встроенном Registry.

```yaml
deploy-prod:
  stage: deploy
  environment:
    name: production
    url: http://$SERVER_HOST
  when: manual
  needs:
    - build-backend
    - unit-tests
```
`environment:` — привязка к GitLab Environments. В UI видно какая версия сейчас на production, история деплоев. `when: manual` — деплой не автоматический, требует нажатия кнопки в GitLab UI. Страховка от случайных деплоев. Реальный `deploy-prod` внутри устанавливает SSH-клиент (`apk add openssh-client`), поднимает `ssh-agent` и выполняет rolling update по SSH на сервере — тот же паттерн `for svc in backend_1 backend_2 backend_3`, что и в GitHub Actions версии.

---

#### Практика

**Шаг 1 — Изучить pipeline**

```bash
cd level-4-cicd
cat .github/workflows/deploy.yml
```

Pipeline состоит из четырёх jobs:
1. `test` — запускает `pytest`, если падают — дальше не идём
2. `build` — собирает Docker образ, пушит в `ghcr.io`
3. `scan` — сканирует образ через Trivy, блокирует деплой при CRITICAL-уязвимостях
4. `deploy` — SSH на сервер, делает rolling update по одному инстансу `backend_1/2/3`

**Шаг 2 — Настроить secrets в GitHub**

Перейди в Settings → Secrets → Actions:
- `SERVER_HOST` — IP твоего сервера
- `SERVER_USER` — имя пользователя (обычно `ubuntu`)
- `SERVER_SSH_KEY` — содержимое приватного SSH-ключа (`~/.ssh/id_rsa` или отдельный deploy-ключ)

`GITHUB_TOKEN` для входа в `ghcr.io` создавать не нужно — GitHub генерирует его автоматически на каждый запуск pipeline.

**Шаг 3 — Запустить pipeline**

```bash
git add .
git commit -m "level-4: add CI/CD pipeline"
git push origin main
```

Открой GitHub → Actions — увидишь запущенный workflow.

**Шаг 4 — Намеренно сломать тесты**

В `backend/main.py` сломай один endpoint — верни неправильный статус-код. Закоммить и запушь. Убедись что pipeline падает на шаге `test` и деплой не происходит.

```bash
git revert HEAD
git push origin main
```

**Шаг 5 — Rolling update (zero downtime)**

Посмотри как настроен rolling update в `deploy.yml`:
```yaml
# Поднимаем новые контейнеры, потом убиваем старые
docker compose pull
docker compose up -d --no-deps --build backend_1
sleep 5  # ждём health check
docker compose up -d --no-deps --build backend_2
sleep 5
docker compose up -d --no-deps --build backend_3
```

Запусти k6 во время деплоя — ошибок быть не должно.

---

### 4b — Self-hosted GitLab CE

#### Зачем отдельный уровень

GitHub Actions — облачный CI/CD. Код уходит в Microsoft/GitHub. Для многих компаний это неприемлемо: финансы, медицина, государство, военный сектор. Там ставят GitLab на своём железе — и git, и CI/CD под полным контролем.

#### Практика

**Шаг 1 — Запустить GitLab**

```bash
cd level-4-gitlab
docker compose up -d gitlab

# GitLab стартует долго — 3-5 минут
docker compose logs -f gitlab
# Жди: "GitLab is up and running"

# Получить начальный пароль root
docker compose exec gitlab cat /etc/gitlab/initial_root_password
```

Открой `http://localhost:8929` — GitLab UI (порт именно 8929, не 80 — чтобы не конфликтовать с nginx уровней 1-3, см. `external_url` в docker-compose.yml).

**Шаг 2 — Запустить GitLab Runner**

```bash
docker compose up -d gitlab-runner

# Токен возьми в GitLab UI: твой проект → Settings → CI/CD → Runners → New project runner
./runner/register.sh <RUNNER_TOKEN>
```
Скрипт внутри делает `docker compose exec gitlab-runner gitlab-runner register` с `--executor docker`, `--docker-image alpine:latest`, `--docker-privileged` (нужно для Docker-in-Docker в самих job'ах) и `--docker-volumes /var/run/docker.sock:/var/run/docker.sock`.

**Шаг 3 — Изучить .gitlab-ci.yml**

```bash
cat .gitlab-ci.yml
```

Этапы: `test` → `build` → `deploy`. Очень похоже на GitHub Actions, но синтаксис немного отличается.

**Шаг 4 — Создать Merge Request**

В GitLab создай ветку, сделай изменение в коде, создай MR. Увидишь что CI запускается автоматически. После успешного CI — разрешён мерж.

> **Как в проде:** GitLab позволяет настроить Environments и Deployments — видно какая версия на каком окружении. Protected branches — в `main` можно мержить только после review двух человек. Compliance framework — все изменения аудитируются.

---

### Что сломать намеренно — Уровень 4

**Поломка 1 — Сломать Dockerfile**

Добавь синтаксическую ошибку в `level-3-caching/backend/Dockerfile` (это реальный build-контекст пайплайна). Запушь. Pipeline должен упасть на стадии `build`. Верни и запушь снова.

**Поломка 2 — Симуляция ошибки деплоя**

В `deploy.yml` добавь `exit 1` в начало шага deploy. Запушь. Pipeline падает. Твои пользователи видят старую (рабочую) версию — rolling update не начался. Верни.

**Поломка 3 — Деплой без rolling update**

Измени deploy на: `docker compose down && docker compose up -d`. Запусти k6 во время деплоя. Увидишь 100% ошибок пока сервис перезапускается.

---

### Справочник команд — Уровень 4

| Команда | Описание |
|---------|---------|
| `docker pull ghcr.io/<owner>/<repo>/bulletin-board-backend:<tag>` | Скачать образ из registry |
| `docker compose pull` | Обновить образы из registry |
| `docker compose up -d --no-deps backend_1` | Обновить только один сервис |
| `git tag v1.2.3 && git push --tags` | Создать тег (триггер для release pipeline) |
| `docker images \| grep bulletin` | Список образов с тегами |
| `trivy image bulletin-board-backend:local` | Сканировать образ на CVE |
| `trivy image --severity HIGH,CRITICAL --exit-code 1 <image>` | Блокирующая проверка |

### На собеседовании спросят

**Q: Что такое CVE и как Trivy помогает?**
A: CVE (Common Vulnerabilities and Exposures) — база известных уязвимостей с уникальными идентификаторами (CVE-2024-1234) и CVSS-баллами (0-10). Trivy сканирует слои Docker-образа: сравнивает установленные пакеты с базами уязвимостей (NVD, GitHub Advisory). Результат: список CVE с severity (CRITICAL/HIGH/MEDIUM/LOW). Блокируем деплой если есть CRITICAL с доступным патчем.

**Q: Почему ALTER TABLE ADD COLUMN NOT NULL DEFAULT блокирует таблицу на минуты?**
A: PostgreSQL переписывает весь файл таблицы: читает каждую строку, добавляет новое поле, записывает обратно. На таблице 10M строк — это минуты, всё время держится ACCESS EXCLUSIVE LOCK. Правильно: ADD COLUMN NULL (мгновенно) → UPDATE батчами → SET NOT NULL. Или `ADD COLUMN DEFAULT` в PostgreSQL 11+ — дефолт хранится в метаданных без переписи.

**Q: Что такое Expand-Contract pattern для миграций?**
A: Безопасный способ изменить схему без остановки сервиса. Три деплоя:
1. Expand — добавляем новое поле/таблицу (совместимо со старым кодом)
2. Backfill — заполняем данные, оба поля работают параллельно
3. Contract — удаляем старое поле (когда новый код уже везде)
Нельзя за один деплой удалить колонку которую читает старый код.

**Q: В чём разница `CREATE INDEX` vs `CREATE INDEX CONCURRENTLY`?**
A: Обычный CREATE INDEX блокирует таблицу на всё время построения (минуты на большой таблице). CONCURRENTLY строит без блокировки: работает медленнее, требует двух проходов, нельзя в транзакции — зато таблица доступна для чтения и записи. В production — всегда CONCURRENTLY для существующих таблиц.

**Q: Какие есть стратегии деплоя и когда что применять?**
A: Recreate — стоп всё/старт всё, есть даунтайм, зато нет двух версий одновременно (для stateful). Rolling — по одному, zero downtime, но v1 и v2 работают параллельно (нужна обратная совместимость API). Blue-Green — два окружения, мгновенный switch и rollback, двойные ресурсы. Canary — малый % трафика на новую версию, безопасно для рискованных изменений. Feature flags — четвёртый вариант без деплоя.

### Итог уровня 4

Ты умеешь:
- [ ] Настроить CI/CD pipeline с тестами, сборкой, деплоем
- [ ] Использовать GitHub Container Registry или GitLab Registry
- [ ] Делать rolling update без даунтайма
- [ ] Откатить версию через git revert
- [ ] Запустить Trivy и понять вывод CVE (severity, fixed version)
- [ ] Добавить Trivy в CI pipeline с блокировкой на CRITICAL
- [ ] Объяснить Expand-Contract pattern и почему нельзя удалить колонку в один деплой
- [ ] Создать безопасный индекс через CREATE INDEX CONCURRENTLY

**Боль которую ты чувствуешь:** три Docker Compose сервиса поднимаются независимо, нет self-healing — упал контейнер → надо идти вручную перезапускать. При масштабировании на несколько серверов — docker-compose на каждом управляется отдельно, это хаос → Уровень 5: Kubernetes.

---

## Уровень 5 — Kubernetes

### Зачем это нужно

Docker Compose хорош для одной машины. В production проблемы:
- **Нет self-healing:** упал контейнер — нет автоматического перезапуска
- **Нет автомасштабирования:** нагрузка выросла втрое — добавляй руками
- **Нет управления ресурсами:** один контейнер может съесть всю RAM
- **Rolling update — самодельный:** набор bash-скриптов вместо встроенного механизма
- **Несколько серверов — хаос:** docker-compose на каждом управляется отдельно

Kubernetes (K8s) — оркестратор контейнеров. Ты описываешь желаемое состояние, K8s делает всё остальное: запускает, следит, восстанавливает, масштабирует.

### Как это работает

Docker Compose — ты сам управляешь каждым работником: кого нанять, уволить, сколько платить.
Kubernetes — HR-отдел с автоматизацией: сам набирает если кто-то заболел (self-healing), сам масштабирует при наплыве задач (HPA), следит за ресурсами (resource limits).

### Ключевые концепции

```
Cluster
  └── Node (сервер)
        └── Pod (обёртка вокруг контейнера)
              └── Container: backend

Deployment  → "хочу 3 копии этого Pod"
Service     → стабильный DNS внутри кластера
Ingress     → внешний доступ (заменяет nginx upstream)
ConfigMap   → конфигурация (не секреты)
Secret      → пароли, токены (base64)
HPA         → автомасштабирование на основе CPU/RAM
```

**Pod vs Container:** Pod — обёртка. Контейнеры в одном Pod делят сеть и volumes. Обычно 1 контейнер = 1 Pod.

**Deployment vs Pod:** никогда не создавай Pod напрямую. Deployment следит чтобы нужное количество копий работало всегда.

**Service:** Pod-ы эфемерны — IP меняется при каждом пересоздании. Service — стабильный адрес `backend.bulletin-board.svc.cluster.local`.

---

### Анатомия Kubernetes манифестов

#### Deployment

```yaml
apiVersion: apps/v1
kind: Deployment
```
`apiVersion` — версия Kubernetes API. Разные ресурсы используют разные API-группы:
- `apps/v1` — Deployment, StatefulSet, DaemonSet
- `v1` — Pod, Service, ConfigMap, Secret, Namespace
- `batch/v1` — Job, CronJob
- `networking.k8s.io/v1` — Ingress
- `autoscaling/v2` — HPA

Не запоминай — смотри в документации или `kubectl explain <resource>`.

```yaml
metadata:
  name: backend
  namespace: bulletin-board
  labels:
    app: backend
    version: v1.0.0
```
`name` — уникальное имя ресурса внутри namespace. `namespace` — логическое разделение кластера. Разные namespace — разные права доступа, разные сети (почти), удобно для разделения окружений (dev/staging/prod). `labels` — произвольные key-value пары. Используются для выборки ресурсов (`selector`). По соглашению: `app` — имя приложения, `version` — версия.

```yaml
spec:
  replicas: 3
```
Желаемое число Pod-ов. Deployment Controller непрерывно сравнивает желаемое с реальным. Упал один Pod — создаёт новый. Поставил `replicas: 0` — удалит все Pod-ы (deployment останется, данные в конфиге — нет).

```yaml
  selector:
    matchLabels:
      app: backend
```
**Критически важно:** Deployment находит свои Pod-ы по этому selector. Он должен совпадать с `labels` в `template.metadata`. Если selector изменить после создания — ошибка (иммутабельное поле). Это означает "этот Deployment управляет Pod-ами у которых есть label `app: backend`".

```yaml
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
```
Стратегия обновления при `kubectl apply` с новым образом:
- `RollingUpdate` (по умолчанию) — обновляет Pod-ы постепенно
- `Recreate` — сначала удаляет все старые, потом создаёт новые. Даунтайм, но зато нет двух версий одновременно.

`maxSurge: 1` — во время rolling update можно запустить на 1 Pod больше нормы. При replicas=3 во время обновления может быть 4 Pod-а. `maxUnavailable: 0` — ни один Pod не должен быть недоступен. Вместе: сначала запускается новый (+1), после его готовности — удаляется старый. Zero downtime.

```yaml
  template:
    metadata:
      labels:
        app: backend
    spec:
      containers:
        - name: backend
          image: bulletin-board-backend:latest
          imagePullPolicy: IfNotPresent
```
В реальном манифесте образ локальный (`bulletin-board-backend:latest`, собранный прямо в Docker-окружении minikube) — закомментированная альтернатива рядом предлагает переключиться на `ghcr.io/<username>/devops-project/bulletin-board-backend:latest` после того как настроишь CI/CD (Level 4).
`template` — шаблон для создания Pod-ов. Это и есть Pod-спецификация. `containers` — массив контейнеров в Pod-е. Обычно один, иногда несколько (sidecar-паттерн: основной + прокси/логгер/инжектор).

```yaml
          ports:
            - containerPort: 8000
              protocol: TCP
```
`containerPort` — документация как EXPOSE в Dockerfile. Не открывает порт. Реальная маршрутизация — в Service. Но указывать нужно для читаемости и для некоторых инструментов мониторинга.

```yaml
          envFrom:
            - secretRef:
                name: postgres-secret
            - configMapRef:
                name: backend-config
```
В реальных манифестах (`k8s/backend/deployment.yml`) переменные подключены не по одной через `env:`+`valueFrom`, а целиком через `envFrom` — весь `postgres-secret` и весь `backend-config` разом становятся переменными окружения контейнера (внутри — `DATABASE_URL`, `REDIS_URL` и т.д., именно в верхнем регистре, как обычно принято для env-переменных). `env:`+`valueFrom:secretKeyRef`/`configMapKeyRef` — тоже рабочий способ, просто более многословный, когда нужна одна конкретная переменная, а не весь набор:
```yaml
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: postgres-secret
                  key: DATABASE_URL
```
Два способа задать переменную окружения из K8s-ресурсов:
- `secretKeyRef` — из Secret (base64 encoded, не шифрован, но не показывается в `kubectl get`). Для паролей, токенов.
- `configMapKeyRef` — из ConfigMap (plaintext). Для несекретных настроек.

```yaml
          resources:
            requests:
              memory: "64Mi"
              cpu: "50m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```
**requests** — гарантированные ресурсы. Scheduler использует их для размещения Pod на Node. Pod всегда получит как минимум столько. **limits** — максимум.

`100m` — 100 millicores = 0.1 CPU. 1000m = 1 CPU ядро.
`128Mi` — MiB (мебибайт = 2²⁰ байт ≈ 134 МБ).

Что происходит при превышении limits:
- **Memory limit** — процесс убивается (OOMKill). Pod перезапускается.
- **CPU limit** — процесс throttled (замедляется), не убивается.

Без limits — Pod может съесть всю память Node, положив другие Pod-ы. **Всегда указывай limits в production.**

```yaml
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 10
            periodSeconds: 5
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 10
            failureThreshold: 3
```
**readinessProbe** — "готов ли Pod принимать трафик?" Если проверка падает — Pod убирается из Service endpoints. Запросы на него не идут. Используй для: Pod запустился но ещё прогревает кэш/подключается к БД.

**livenessProbe** — "жив ли процесс вообще?" Если падает `failureThreshold` раз подряд — контейнер перезапускается. Используй для: обнаружения deadlock (процесс запущен, порт открыт, но запросы не обрабатываются).

`initialDelaySeconds` у liveness больше чем у readiness — дать приложению время на старт прежде чем начать проверять живость. Если liveness начнёт проверять слишком рано и приложение ещё не готово — бесконечный restart loop.

Три типа проб: `httpGet` (HTTP 200-399 = success), `tcpSocket` (порт открыт = success), `exec` (команда exit 0 = success).

---

#### Service

```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: bulletin-board
spec:
  selector:
    app: backend
  ports:
    - port: 8000
      targetPort: 8000
  type: ClusterIP
```
`selector: app: backend` — Service находит Pod-ы по этому label. Автоматически обновляет список endpoints когда Pod-ы появляются/исчезают. Это и есть service discovery в K8s.

`port: 8000` — порт на котором Service доступен внутри кластера. `targetPort: 8000` — порт на Pod-е куда перенаправить (в нашем случае совпадают, но могли бы отличаться). Другие Pod-ы обращаются к `http://backend.bulletin-board.svc.cluster.local:8000` или просто `http://backend:8000` внутри того же namespace.

**Типы Service:**
- `ClusterIP` (по умолчанию) — доступен только внутри кластера. У нас — `backend`, `postgres`, `redis`.
- `NodePort` — открывает порт на каждой Node кластера (30000-32767). Доступен снаружи по `<node-ip>:<nodeport>`. У нас именно так организован внешний доступ — `nginx` Service слушает `NodePort: 30080`, отдельного Ingress в проекте нет (см. ниже).
- `LoadBalancer` — создаёт облачный балансировщик (AWS ELB, GCP LB). Дорого, для production, нужен облачный провайдер.
- `ExternalName` — DNS-alias на внешний сервис. Без проксирования.

---

#### Ingress

⚠️ **В этом проекте Ingress не используется** — внешний доступ реализован проще, через `nginx` Service с `type: NodePort` (см. выше). Ingress здесь — важная концепция для реальных кластеров и собеседований, но `k8s/` в репозитории не содержит Ingress-манифеста. Если добавишь его сам — получится примерно так:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: bulletin-board
  namespace: bulletin-board
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /
    nginx.ingress.kubernetes.io/proxy-body-size: "10m"
spec:
  ingressClassName: nginx
  rules:
    - host: bulletin-board.example.com
      http:
        paths:
          - path: /api/
            pathType: Prefix
            backend:
              service:
                name: backend
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: nginx-static
                port:
                  number: 80
  tls:
    - hosts:
        - bulletin-board.example.com
      secretName: tls-secret
```
Ingress — правила маршрутизации внешнего HTTP/HTTPS трафика в Service-ы. Сам по себе ничего не делает — нужен **Ingress Controller** (nginx-ingress, traefik, HAProxy).

`annotations` — метаданные для Ingress Controller-а. Разные контроллеры понимают разные annotations. `nginx.ingress.kubernetes.io/proxy-body-size: "10m"` — лимит размера запроса (для загрузки файлов).

`ingressClassName: nginx` — какой Ingress Controller обрабатывает этот Ingress.

`pathType: Prefix` vs `Exact`:
- `Prefix` — `/api/` совпадает с `/api/ads`, `/api/health`, `/api/users/1`
- `Exact` — только точное совпадение

`tls:` — HTTPS. `secretName: tls-secret` — K8s Secret с `tls.crt` и `tls.key`. Cert-Manager может автоматически получать сертификаты от Let's Encrypt и хранить их в таком Secret.

---

#### ConfigMap и Secret

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-config
  namespace: bulletin-board
data:
  REDIS_URL: "redis://redis:6379"
```
ConfigMap — несекретная конфигурация (реальный `backend-config` в этом проекте минимальный — по сути только `REDIS_URL`). `data:` — key-value пары строк. Можно использовать как переменные окружения (через `envFrom`/`configMapKeyRef`) или монтировать как файлы (`configMap` volume). Если изменить ConfigMap — Pod-ы не перезапустятся автоматически (нужно сделать rolling restart).

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: postgres-secret
  namespace: bulletin-board
type: Opaque
data:
  DATABASE_URL: cG9zdGdyZXNxbDovL3...  # base64
```
Secret — для чувствительных данных. `type: Opaque` — произвольные данные (в отличие от `kubernetes.io/tls` или `kubernetes.io/dockerconfigjson`). Значения хранятся в **base64** — это **не шифрование**, это кодирование. Любой кто может читать Secret — видит значения:

```bash
echo "cG9zdGdyZXNxbDovL3..." | base64 -d
# postgresql://postgres:postgres@postgres:5432/bulletin_board
```

В production Secret-ы шифруют через Encryption at Rest в etcd, или хранят в HashiCorp Vault / AWS Secrets Manager и инжектируют через специальные операторы.

Создание Secret без хранения пароля в открытом виде:
```bash
kubectl create secret generic postgres-secret \
  --from-literal=DATABASE_URL="postgresql://postgres:${DB_PASSWORD}@postgres:5432/bulletin_board" \
  -n bulletin-board
```

---

#### HPA (Horizontal Pod Autoscaler)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: backend-hpa
  namespace: bulletin-board
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: backend
  minReplicas: 2
  maxReplicas: 10
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 50
    - type: Resource
      resource:
        name: memory
        target:
          type: Utilization
          averageUtilization: 70
```
`scaleTargetRef` — какой Deployment масштабировать. `minReplicas: 2` — никогда не опускаться ниже 2 (высокая доступность). `maxReplicas: 10` — не масштабировать бесконечно (защита от runaway cost).

`averageUtilization: 50` для CPU — держать среднее потребление CPU на уровне 50% от `requests.cpu`. Почему не 80%? При 80% нет запаса: всплеск нагрузки → 100% CPU → деградация → HPA начинает масштабировать → 2-3 минуты пока новые Pod-ы поднимутся → пользователи уже получили ошибки. При 50% есть буфер.

Для работы HPA нужен **Metrics Server** в кластере. В minikube: `minikube addons enable metrics-server`.

---

### Ключевые команды

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `kubectl get pods` | Список Pod-ов | `kubectl get pods -n bulletin-board` |
| `kubectl describe pod <name>` | Детали Pod — события, статус | `kubectl describe pod backend-xxx` |
| `kubectl logs <pod>` | Логи Pod | `kubectl logs backend-xxx -f` |
| `kubectl exec -it <pod> -- bash` | Зайти внутрь | `kubectl exec -it backend-xxx -- bash` |
| `kubectl apply -f <file>` | Применить манифест | `kubectl apply -f k8s/backend.yaml` |
| `kubectl delete pod <name>` | Удалить Pod (K8s пересоздаст) | `kubectl delete pod backend-xxx` |
| `kubectl scale deployment backend --replicas=5` | Масштабировать | — |
| `kubectl rollout status deployment/backend` | Статус rolling update | — |
| `kubectl rollout undo deployment/backend` | Откат на предыдущую версию | — |

### Практика

**Шаг 1 — Установить minikube и kubectl**

```bash
# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client

# minikube
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
minikube version
```

**Шаг 2 — Запустить кластер**

```bash
minikube start --driver=docker --memory=4096 --cpus=2
minikube status
kubectl get nodes
```

```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   1m    v1.31.x
```

**Шаг 3 — Разобрать манифесты**

```bash
cd level-5-kubernetes
find k8s -type f
# k8s/namespace.yml
# k8s/postgres/{deployment,service,pvc,secret}.yml
# k8s/redis/{deployment,service}.yml
# k8s/backend/{deployment,service,configmap,hpa}.yml
# k8s/nginx/{deployment,service,configmap}.yml
```
Манифесты разложены по подпапкам на сервис, не одним плоским списком файлов, и расширение `.yml`, не `.yaml`. Отдельного `ingress.yml` нет — см. заметку про Ingress выше.

Прочитай `k8s/backend/deployment.yml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
spec:
  replicas: 3              # три копии
  selector:
    matchLabels:
      app: backend
  template:
    spec:
      containers:
      - name: backend
        image: bulletin-board-backend:latest
        resources:
          requests:           # гарантированные ресурсы
            memory: "64Mi"
            cpu: "50m"
          limits:             # максимум
            memory: "256Mi"
            cpu: "500m"
        readinessProbe:       # "готов ли принимать трафик?"
          httpGet:
            path: /api/health
            port: 8000
          initialDelaySeconds: 10
        livenessProbe:        # "жив ли процесс?"
          httpGet:
            path: /api/health
            port: 8000
```

**Шаг 4 — Задеплоить**

```bash
# Собрать образ в контексте minikube (backend всё тот же код, что и на предыдущих уровнях)
eval $(minikube docker-env)
docker build -t bulletin-board-backend:latest ../level-3-caching/backend

# Применить все манифесты (по подпапкам, порядок не важен — k8s сам разберётся с зависимостями)
kubectl apply -f k8s/ --recursive

# Следить за созданием Pod-ов
kubectl get pods -n bulletin-board -w
```

```
NAME                       READY   STATUS    RESTARTS
backend-7d9f8b6c4-abc12    0/1     Pending   0
backend-7d9f8b6c4-abc12    0/1     Running   0
backend-7d9f8b6c4-abc12    1/1     Running   0    ← Pod готов!
```

**Шаг 5 — Self-healing в действии**

```bash
# Смотреть за Pod-ами
kubectl get pods -n bulletin-board -w

# В другом терминале — удалить Pod
kubectl delete pod <имя-одного-pod> -n bulletin-board
```

Видишь: Pod удаляется, Deployment мгновенно создаёт новый. Это и есть self-healing.

**Шаг 6 — Rolling update**

```bash
# Обновить версию образа
kubectl set image deployment/backend backend=bulletin-board-backend:v2 -n bulletin-board

# Смотреть как обновляется (по одному Pod за раз)
kubectl rollout status deployment/backend -n bulletin-board

# Если что-то пошло не так:
kubectl rollout undo deployment/backend -n bulletin-board
```

**Шаг 7 — Horizontal Pod Autoscaler**

```bash
# Применить HPA (масштабировать от 2 до 10 Pod при CPU > 50%)
kubectl apply -f k8s/hpa.yaml

# Проверить
kubectl get hpa -n bulletin-board

# Нагрузочный тест
k6 run load-tests/stress.js

# Наблюдать как K8s добавляет Pod-ы
kubectl get pods -n bulletin-board -w
```

---

### Что сломать намеренно — Уровень 5

**Поломка 1 — CrashLoopBackOff**

В манифесте `backend.yaml` измени command на несуществующий: `command: ["python3", "nonexistent.py"]`. Примени. Смотри:

```bash
kubectl get pods -n bulletin-board
# STATUS: CrashLoopBackOff

kubectl describe pod <name> -n bulletin-board
# Events: Back-off restarting failed container

kubectl logs <name> -n bulletin-board --previous
# Error: can't open file 'nonexistent.py'
```

K8s будет перезапускать с экспоненциальным backoff (10с, 20с, 40с...). Верни манифест и применяй снова.

**Поломка 2 — Resource limits**

Установи `limits.memory: "10Mi"` — слишком мало для Python. Примени. Pod будет получать `OOMKilled`:

```bash
kubectl describe pod <name> -n bulletin-board
# Reason: OOMKilled
# Exit Code: 137
```

**Поломка 3 — Liveness probe убивает Pod**

Измени `livenessProbe.path` на `/api/nonexistent`. Примени. Pod будет регулярно рестартовать потому что probe всегда падает:

```bash
kubectl get pods -n bulletin-board
# RESTARTS: 5

kubectl describe pod <name> -n bulletin-board
# Warning  Unhealthy  Liveness probe failed: HTTP probe failed with statuscode: 404
```

---

> **Как в проде:** в реальных кластерах (EKS, GKE, AKS) используют managed K8s — облако управляет control plane. Узлы добавляются автоматически (Cluster Autoscaler). Ingress-контроллер — обычно nginx-ingress или AWS ALB. Secrets хранят в HashiCorp Vault или AWS Secrets Manager, не в K8s Secret (он просто base64, не зашифрован).

---

### Справочник команд — Уровень 5

| Команда | Описание |
|---------|---------|
| `kubectl get pods -n bulletin-board` | Список Pod-ов |
| `kubectl get pods -n bulletin-board -w` | Следить за изменениями |
| `kubectl describe pod <name> -n bulletin-board` | Детальная информация + события |
| `kubectl logs <pod> -n bulletin-board -f` | Логи в реальном времени |
| `kubectl logs <pod> -n bulletin-board --previous` | Логи упавшего Pod |
| `kubectl exec -it <pod> -n bulletin-board -- bash` | Зайти внутрь |
| `kubectl apply -f k8s/` | Применить все манифесты |
| `kubectl delete pod <name> -n bulletin-board` | Удалить Pod (пересоздастся) |
| `kubectl scale deployment backend --replicas=5 -n bulletin-board` | Ручное масштабирование |
| `kubectl rollout status deployment/backend -n bulletin-board` | Статус деплоя |
| `kubectl rollout undo deployment/backend -n bulletin-board` | Откат |
| `kubectl get hpa -n bulletin-board` | Autoscaler |
| `kubectl top pods -n bulletin-board` | CPU/RAM Pod-ов |
| `minikube dashboard` | Веб-интерфейс |

### На собеседовании спросят — Уровень 5

**Q: В чём разница Rolling Update, Blue-Green и Canary?**
A: Rolling: обновляет Pod-ы по одному, v1 и v2 параллельно, откат = новый деплой (медленно). Blue-Green: два полных окружения, мгновенный switch selector, мгновенный rollback, но двойные ресурсы. Canary: 10-20% трафика на новую версию, градуальное увеличение — минимальный риск для пользователей.

**Q: Как реализовать Blue-Green в Kubernetes?**
A: Два Deployment с labels `slot=blue` и `slot=green`. Service selector — `{slot: blue}`. При деплое создать green, дождаться readiness, `kubectl patch service` → `slot=green`. Rollback = patch обратно.

**Q: Как реализовать Canary через K8s без ingress-controller?**
A: Два Deployment, оба с label `app=backend`. Service выбирает всех по этому label. Пропорция реплик = пропорция трафика: `stable replicas=4, canary replicas=1` → 80/20. Graduate: обновить stable на v2, удалить canary.

### Итог уровня 5

Ты умеешь:
- [ ] Создавать Deployment, Service, ConfigMap, Secret
- [ ] Читать диагностику Pod-ов (logs, describe, exec)
- [ ] Наблюдать self-healing в реальном времени
- [ ] Делать rolling update и откатывать его
- [ ] Настроить HPA для автомасштабирования
- [ ] Разбирать CrashLoopBackOff и OOMKilled
- [ ] Выполнить Blue-Green деплой и мгновенный rollback через selector
- [ ] Выполнить Canary: 20% трафика, наблюдение метрик, graduate или rollback

**Боль которую ты чувствуешь:** наружу торчит NodePort на порту 30080 — нестандартный порт, нет TLS, по порту на каждый будущий сервис. В реальных кластерах вход устроен иначе → Уровень 5.5.

---

## Уровень 5.5 — Ingress и cert-manager

### Зачем это нужно

NodePort — «чёрный ход» для отладки: нестандартный порт, один сервис = один порт, никакой маршрутизации по имени, никакого TLS. Реальный вход в кластер — **Ingress**: единая точка на 80/443, маршрутизация по `Host`/`path`, TLS-терминация в одном месте. **cert-manager** автоматизирует сертификаты — это внутрикластерный аналог того, что Traefik + Let's Encrypt делали на уровне 3.5.

### Как это работает

Ingress-ресурс — только правила («кого куда провожать»); исполняет их ingress-контроллер (у нас ingress-nginx). NodePort — служебные двери с номерами по периметру здания, Ingress — ресепшн у главного входа: все заходят через одну дверь, называют кого ищут (Host), их провожают.

### Практика

Полные шаги — `level-5.5-ingress/README.md`: включение ingress-nginx, перевод nginx-сервиса NodePort → ClusterIP, Ingress с маршрутизацией по Host, установка cert-manager с двумя issuer-ами (selfsigned для minikube, letsencrypt-staging для сервера с публичным доменом), и три поломки с разными симптомами (404 / пустой ADDRESS / 503).

**Боль которую ты чувствуешь:** при инциденте ты слепой. Не видно что происходит внутри кластера: сколько запросов, какое время ответа, где ошибки. Нужен мониторинг → Уровень 6.

---

## Уровень 6 — Observability

### Зачем это нужно

Случился инцидент. Пользователи не могут создать объявление. Ты заходишь на сервер — всё зелёное, контейнеры запущены. Начинаешь смотреть логи вручную — 10 000 строк. Что искать? С какого времени? На каком инстансе?

Это **реактивный подход** — ты видишь проблему только когда она уже есть.

**Проактивный подход:** алерт в Telegram за 5 минут до того как пользователи начнут жаловаться. График который показывает "latency растёт последние 30 минут". Логи которые можно фильтровать, группировать, искать по тексту ошибки.

Без observability ты слепой пилот — летишь без приборов.

### Три кита

```
Metrics (Prometheus + Grafana)
  "Сколько запросов? Время ответа? Процент ошибок?"

Logs (Loki + Promtail + Grafana)
  "Что именно происходило в 14:32:15?"

Traces (OpenTelemetry — строим частично: Correlation ID + изучаем OTel)
  "Как конкретный запрос прошёл через все сервисы?"
```

**Метрики** — числа во времени: RPS=150, latency_p95=120ms, errors=2%. Отвечают на вопрос "что происходит прямо сейчас?"

**Логи** — текстовые события: `2025-01-01 14:32:15 POST /api/ads 201 45ms`. Отвечают на вопрос "что именно произошло?"

**Трейсы** — путь запроса через все сервисы: nginx(2ms) → backend JWT(5ms) → db pool(320ms) → postgres INSERT(315ms). Отвечают на вопрос "где именно тормозит?"

**Почему нужны все три:** метрики говорят "latency выросла", логи показывают "timeout на строке 42", трейсы объясняют "70% времени уходит на ожидание DB connection pool". Без трейсов на 3-сервисном приложении ещё можно жить, в микросервисной архитектуре (10+ сервисов) — нельзя.

**Correlation ID** — практический первый шаг перед полным tracing. Nginx генерирует уникальный ID запроса (`X-Request-ID`), передаёт всем сервисам, они пишут в логи. Итого: можно найти все логи конкретного запроса через `{container=~".*backend.*"} |= "req_id_abc123"`.

**OpenTelemetry (OTel)** — индустриальный стандарт для tracing. Вендор-нейтральный SDK: один раз инструментируешь приложение, данные идут в любой backend (Jaeger, Tempo, Datadog, AWS X-Ray). В Python FastAPI — `opentelemetry-instrument` автоматически трейсит все запросы.

### Как это работает

Prometheus — коллектор метрик с **pull-моделью**: не сервисы шлют метрики, а Prometheus сам ходит к ним каждые 15 секунд. Сервис просто выставляет `/metrics`. Добавил новый сервис — добавь его в конфиг Prometheus, не трогай код сервиса.

Grafana — визуализация. Рисует графики из Prometheus (язык запросов: PromQL) и логи из Loki (язык: LogQL).

---

### Анатомия конфигов мониторинга

#### prometheus.yml

Наш реальный `prometheus.yml` — минимальный:
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'backend'
    static_configs:
      - targets:
          - 'backend_1:8000'
          - 'backend_2:8000'
          - 'backend_3:8000'
    metrics_path: /metrics
```
`scrape_interval` — как часто Prometheus ходит к сервисам за метриками. 15 секунд — стандарт. Чаще (5с) — точнее, но больше нагрузка на Prometheus и сервисы. Реже (60с) — меньше точность для быстрых событий.

`evaluation_interval` — как часто вычислять alerting rules (если они есть — см. ниже, у нас изначально их нет).

`job_name` — имя задачи сбора. Добавляется к каждой метрике как label `job="backend"`. `metrics_path` — по умолчанию `/metrics`, и у нашего бэкенда путь именно такой (не переопределён). `static_configs` — статический список серверов. Альтернатива: `file_sd_configs` (читать из файла), `dns_sd_configs` (DNS SRV записи), `kubernetes_sd_configs` (K8s API, используется на Level 5+).

**Что можно добавить сверху (в нашем файле этого нет, но пригодится для реальных кластеров):**

```yaml
rule_files:
  - "rules/*.yml"
```
Файлы с alerting rules и recording rules. Recording rules — предвычисленные сложные выражения (сохраняются как новая метрика). Нужны для дашбордов которые делают тяжёлые PromQL запросы — вместо вычисления на лету каждый раз.

```yaml
  - job_name: 'cadvisor'
    static_configs:
      - targets: ['cadvisor:8080']
    metric_relabel_configs:
      - source_labels: [__name__]
        regex: 'container_(cpu|memory|network).*'
        action: keep
```
У нас `cadvisor` job есть, но без `metric_relabel_configs`. `metric_relabel_configs` — трансформация метрик ПОСЛЕ сбора. `action: keep` с `regex` — оставлять только метрики подходящие под паттерн. cAdvisor генерирует сотни метрик — большинство не нужны, `keep` фильтрует только нужные, экономит память Prometheus.

```yaml
alerting:
  alertmanagers:
    - static_configs:
        - targets: ['alertmanager:9093']
```
Куда отправлять сработавшие alerts. **На этом уровне Alertmanager ещё не поднят** — он появится в Level 6.5, когда алерты понадобится не просто видеть, а автоматически диагностировать через AI-агента. До этого момента алерты в Prometheus UI (`/alerts`) видны, но никуда не отправляются.

---

#### alerting rule

```yaml
groups:
  - name: bulletin-board-alerts
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: |
          rate(http_requests_total{status_code=~"5.."}[5m])
          /
          rate(http_requests_total[5m])
          > 0.05
        for: 2m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "High error rate on {{ $labels.instance }}"
          description: "Error rate is {{ $value | humanizePercentage }} for last 5 minutes"

      - alert: SlowResponseTime
        expr: histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) > 0.5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "p95 latency > 500ms"
```
`expr` — PromQL-выражение. Alert сработает когда оно возвращает результат (не пустой).
`for: 2m` — выражение должно быть true непрерывно в течение 2 минут. Без `for` — alert флапает при каждом кратковременном всплеске. `labels` — добавляются к alert, используются Alertmanager для маршрутизации. `annotations` — человекочитаемое описание. `$labels.instance` — label из метрики. `$value` — значение выражения. `humanizePercentage` — форматировать как процент.

---

### Практика

**Шаг 1 — Посмотреть что экспортирует бэкенд**

```bash
cd level-6-monitoring
docker compose up --build -d

docker compose exec backend_1 curl -s localhost:8000/metrics | head -30
```
`/metrics` не проксируется через nginx (в `nginx.conf` наружу пробрасывается только `/api/`) и backend не публикует порт на хост — поэтому смотрим изнутри контейнера через `docker compose exec`, а не через `curl http://localhost/...`.

```
# TYPE http_requests_total counter
http_requests_total{handler="/api/ads",method="GET",status_code="200"} 142.0

# TYPE http_request_duration_seconds histogram
http_request_duration_seconds_bucket{le="0.01"} 89.0
http_request_duration_seconds_bucket{le="0.025"} 134.0
```

**Типы метрик:**
- **Counter** — только растёт (requests_total). Для скорости: `rate(counter[5m])`
- **Gauge** — текущее значение (connections, memory_bytes)
- **Histogram** — распределение (latency). Позволяет считать p50, p95, p99

**Шаг 2 — PromQL в Prometheus UI**

Открой `http://localhost:9090`

Попробуй запросы:
```promql
# RPS за последние 5 минут
rate(http_requests_total[5m])

# p95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# Процент ошибок
rate(http_requests_total{status_code=~"5.."}[5m]) /
rate(http_requests_total[5m]) * 100

# CPU по контейнерам (от cAdvisor)
container_cpu_usage_seconds_total{name=~"backend.*"}
```

**Шаг 3 — Grafana дашборд**

Открой `http://localhost:3000` (admin/admin)

Дашборд **Bulletin Board** уже загружен автоматически (provisioning). Найди:
- **RPS** — запросов в секунду
- **Latency p95** — время ответа у 95% запросов
- **Error rate** — процент ошибок
- **Container CPU/RAM** — ресурсы контейнеров

**Шаг 4 — Запустить нагрузку и смотреть графики в реальном времени**

```bash
# В одном терминале
k6 run load-tests/stress.js

# Grafana → Bulletin Board dashboard → auto-refresh 5s
```

Видишь: RPS растёт, latency растёт, CPU у backend-ов растёт.

**Шаг 5 — Loki: поиск по логам**

В Grafana → Explore → выбери источник данных `Loki`:

```logql
# Все логи бэкенда
{container="level-6-monitoring-backend_1-1"}

# Только ошибки
{container=~"backend.*"} |= "ERROR"

# Медленные запросы (дольше 1 секунды)
{container=~"backend.*"} |= "duration" | duration > 1s

# Количество ошибок по времени
count_over_time({container=~"backend.*"} |= "ERROR" [1m])
```

**Шаг 6 — Настроить алерт**

В Grafana → Alerting → New Alert Rule:
- Условие: `rate(http_requests_total{status_code=~"5.."}[5m]) > 0.1`
- Значит: более 10% ошибок за 5 минут
- Действие: отправить в Telegram или email

---

### Что сломать намеренно — Уровень 6

**Поломка 1 — Симуляция memory leak**

Готового эндпоинта для этого в проекте нет — добавь временно в `backend/main.py` (рядом с другими `@app.get`):
```python
_leak: list[bytes] = []

@app.get("/api/debug/leak")
def debug_leak():
    _leak.append(b"x" * 10_000_000)  # +10 МБ в процессе на каждый вызов, никогда не освобождается
    return {"leaked_chunks": len(_leak)}
```
Пересобери backend (`docker compose up --build -d`), потом вызови эндпоинт много раз:
```bash
for i in $(seq 1 100); do
  docker compose exec backend_1 curl -s localhost:8000/api/debug/leak > /dev/null
done
```

Смотри в Grafana: `container_memory_usage_bytes{name="backend_1"}` — медленно растёт. Именно так это выглядит в production — сначала незаметно, через несколько часов OOMKill.

**Поломка 2 — Убить Prometheus**

```bash
docker compose stop prometheus
# Grafana теперь показывает "No data"
docker compose start prometheus
# Через 15 секунд метрики восстанавливаются — Prometheus начинает scrape
```

**Диагностика:** Prometheus → Status → Targets — видно какие сервисы он scraping и когда последний раз.

**Поломка 3 — Потерять логи**

```bash
docker compose stop promtail
# Запусти нагрузку
k6 run load-tests/smoke.js
# Logи за это время не попадут в Loki
docker compose start promtail
# Loki покажет дыру во времени
```

---

> **Как в проде:** RED method (Rate, Errors, Duration) — три метрики которые всегда мониторят для каждого сервиса. SLO (Service Level Objective) — например "99.9% запросов должны отвечать менее чем за 200ms". Нарушение SLO → алерт → инцидент. В больших компаниях Prometheus не хранит данные дольше 2 недель — используют Thanos или Cortex для долгосрочного хранения.

---

### Справочник команд — Уровень 6

| Команда | Описание |
|---------|---------|
| `docker compose exec backend_1 curl -s localhost:8000/metrics` | Метрики бэкенда (не проксируются через nginx) |
| `curl http://localhost:9090` | Prometheus UI |
| `curl http://localhost:3000` | Grafana |
| `rate(http_requests_total[5m])` | PromQL: RPS |
| `histogram_quantile(0.95, rate(..._bucket[5m]))` | PromQL: p95 latency |
| `{container=~"backend.*"} \|= "ERROR"` | LogQL: ошибки в логах |
| `docker compose logs promtail` | Логи агента сбора логов |
| `curl -I http://localhost/api/health` | X-Request-ID в заголовках ответа |

### На собеседовании спросят

**Q: Чем distributed tracing отличается от логирования?**
A: Лог — одно событие от одного сервиса. Trace — полный путь запроса через все сервисы с временными метками каждого шага. При микросервисной архитектуре запрос может пройти через 5-10 сервисов. Лог покажет "этот сервис получил запрос" — но не объяснит где было потрачено 800ms. Trace показывает распределение времени по каждому шагу.

**Q: Что такое span в контексте distributed tracing?**
A: Span — единица работы в рамках trace: одна операция с временем начала и конца. Trace = дерево span-ов. Span имеет: trace_id (все операции одного запроса), span_id (уникальный для этой операции), parent_span_id (кто породил этот span), duration, labels. Пример: POST /api/ads создаёт root span, внутри него дочерние span-ы: auth.verify(5ms), db.insert(315ms), cache.delete(1ms).

**Q: Что такое OpenTelemetry и зачем он нужен?**
A: OTel — вендор-нейтральный стандарт для сбора telemetry (traces, metrics, logs). Раньше каждый вендор (Datadog, Jaeger) требовал свой SDK — переход на другой инструмент = переписывание инструментации. OTel: один SDK, данные идут через OTLP протокол в любой backend. Для Python FastAPI — `opentelemetry-instrument` автоматически трейсит HTTP запросы, SQL, Redis без изменения кода.

**Q: Что такое Correlation ID и как его использовать?**
A: UUID генерируемый на входе в систему (обычно Nginx) и передаваемый всем сервисам через HTTP заголовок (X-Request-ID). Каждый сервис пишет его в логи. Итого: при инциденте по одному ID находишь все логи конкретного запроса через все инстансы. Практически применим без OTel SDK — только nginx.conf + convention в коде.

**Q: Какие метрики обязательно мониторить для любого HTTP-сервиса?**
A: RED method: Rate (RPS — сколько запросов в секунду), Errors (процент ошибок 5xx), Duration (latency p95/p99). Это минимум. Дополнительно: saturation (использование ресурсов — CPU, RAM, connection pool). По этим четырём метрикам можно обнаружить 90% инцидентов.

### Итог уровня 6

Ты умеешь:
- [ ] Читать Prometheus метрики в `/metrics` формате
- [ ] Писать базовые PromQL запросы (rate, histogram_quantile)
- [ ] Читать логи через LogQL в Grafana
- [ ] Настроить алерт по условию
- [ ] Диагностировать memory leak по графику
- [ ] Добавить X-Request-ID через nginx и находить запросы по нему в Loki
- [ ] Объяснить три кита observability и когда нужен каждый
- [ ] Знать что такое OTel и зачем он нужен в микросервисной архитектуре

**Боль которую ты чувствуешь:** алерт сработал — latency выросла. Смотришь логи — 50 000 строк ошибок за последние 5 минут. Чтобы понять что происходит нужно читать логи, сопоставлять с метриками, строить гипотезы. Это занимает 30 минут. А если бы кто-то уже прочитал логи и объяснил что не так? → Уровень 6.5.

---

## Уровень 6.5 — AI-агент диагностики

### Зачем это нужно

Алерт сработал в 3 ночи. Инженер просыпается, идёт смотреть что случилось. Ему нужно: прочитать Grafana, посмотреть последние ошибки, выдвинуть гипотезу, проверить. Это занимает 20-40 минут пока голова не проснулась.

AI-агент делает первый шаг автоматически: при срабатывании алерта собирает метрики, последние ошибки из логов, состояние сервисов — и объясняет что, вероятно, происходит. Инженер получает в Telegram готовое объяснение: "латенция выросла в 4 раза, в логах 95% ошибок — timeout к PostgreSQL, PostgreSQL CPU на 98% — вероятно медленный запрос без индекса или deadlock".

### Как это работает

Агент запускается **на локальной машине, не на VPS** — LLM-вызовы и Telegram-бот не должны раздувать тариф сервера, а до Prometheus/Loki на VPS агент достаёт через приватный туннель (WireGuard, с SSH-туннелем как временным fallback; подробности и настройка — `level-6.5-ai-agent/README.md`, Шаг 4).

Агент — FastAPI-сервис который:
1. Получает webhook от Alertmanager при алерте (POST /webhook)
2. Запрашивает Prometheus API — текущие метрики
3. Запрашивает Loki API — последние ошибки
4. Формирует промпт → отправляет в Claude API
5. Получает диагностику → отправляет в Telegram
6. Опционально: предлагает действия (restart, scale up) с кнопками approve/reject

### Практика

**Шаг 1 — Получить API ключи**

- Claude API key: `console.anthropic.com` → API Keys
- Telegram Bot: `@BotFather` → `/newbot`

**Шаг 2 — Настроить переменные**

```bash
cd level-6.5-ai-agent
cp .env.example .env
nano .env
```

```
CLAUDE_API_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_CHAT_ID=-100123456789
# 10.8.0.1 — адрес VPS внутри туннеля, не docker DNS-имя и не публичный IP
PROMETHEUS_URL=http://10.8.0.1:9090
LOKI_URL=http://10.8.0.1:3100
```

**Шаг 3 — Запустить**

```bash
docker compose up --build -d agent
docker compose logs -f agent
```

**Шаг 4 — Настроить Alertmanager → агент**

Вебхук идёт не напрямую из Grafana, а через Alertmanager (часть экосистемы Prometheus). Добавь `alertmanager` в `level-6-monitoring/docker-compose.yml`, подключи его в `prometheus.yml` (`alerting.alertmanagers`), и настрой receiver с адресом агента — готовый шаблон в `level-6.5-ai-agent/alerts/alertmanager-webhook.yml`:
```yaml
receivers:
  - name: ai-agent
    webhook_configs:
      - url: 'http://<адрес агента>:8080/webhook'
```
Полный пошаговый разбор (включая туннель, если агент не на VPS) — `level-6.5-ai-agent/README.md`, Шаг 4-5.

**Шаг 5 — Симулировать инцидент**

```bash
# Вызвать высокую нагрузку
k6 run --vus 200 --duration 60s load-tests/stress.js
```

Через несколько секунд в Telegram придёт сообщение с диагностикой от Claude.

**Шаг 6 — Изучить код агента**

```bash
cat agent/main.py
```

Ключевые части:
- `collect_context()` (diagnostics.py) — PromQL к Prometheus + LogQL к Loki за одно обращение
- `diagnose()` (llm.py) — формирует промпт и вызывает Claude API
- `send_diagnosis()` (telegram_bot.py) — отправляет диагноз в Telegram с кнопками Approve/Reject
- `execute_action()` (actions.py) — выполняет одобренные действия (restart, scale) с allowlist защищённых контейнеров (`PROTECTED_CONTAINERS`)

---

> **Как в проде:** AI-агенты диагностики используют в PagerDuty, Incident.io. Называется "AI-assisted incident response". Важно: агент предлагает, человек решает. Автоматическое выполнение действий (автореstart, autoscale) — только для хорошо изученных сценариев с низким риском.

---

## Уровень 7 — Helm

### Зачем это нужно

Ты делаешь `kubectl apply -f k8s/` — применяешь 8-10 файлов по одному. Хочешь задеплоить в staging с другими настройками — копируешь файлы, меняешь вручную, ошибаешься. Хочешь откатить на версию от прошлой недели — помнишь ли точно что было в файлах?

**Helm** — пакетный менеджер для Kubernetes. Как apt для Ubuntu или npm для Node.js. Chart — пакет с шаблонами манифестов. `values.yaml` — параметры для разных окружений. Одна команда деплоит весь стек. Rollback — одна команда.

### Как это работает

Helm chart — как шаблон документа в Word: структура одна, но значения (имя, дата, подпись) подставляются из `values.yaml`. Для production — одни значения, для staging — другие, но структура одна.

---

### Анатомия Helm chart

#### Chart.yaml

```yaml
apiVersion: v2
name: bulletin-board
description: Доска объявлений — полный стек с бэкендом, PostgreSQL, Redis и Nginx
type: application
version: 0.1.0
appVersion: "1.0.0"
```
`apiVersion: v2` — версия формата Chart (v2 для Helm 3, v1 для Helm 2 — уже не используется). `name` — имя chart. Используется в метаданных релиза. `version` — версия самого chart (инфраструктурные изменения). `appVersion` — версия приложения (код). Они независимы: можно изменить конфиг nginx в chart (version 0.1.1) не меняя код приложения (appVersion 1.0.0). `type: application` vs `library` — library chart не деплоится сам, только переиспользуется другими.

---

#### values.yaml

Реальный chart в этом проекте — простой и плоский, без Bitnami-style сабчартов и `_helpers.tpl` (об этом паттерне — ниже, для общего понимания):
```yaml
backend:
  image:
    repository: bulletin-board-backend
    tag: latest
    pullPolicy: IfNotPresent
  replicas: 3
  resources:
    requests:
      memory: "64Mi"
      cpu: "50m"
    limits:
      memory: "256Mi"
      cpu: "500m"

postgres:
  image: postgres:16-alpine
  database: bulletin_board
  user: postgres
  password: postgres   # в production замени на Kubernetes Secret из внешнего хранилища
  storage: 1Gi

redis:
  image: redis:7-alpine

nginx:
  image: nginx:alpine
  service:
    type: NodePort
    nodePort: 30080

namespace: bulletin-board

blueGreen:
  enabled: false
  activeSlot: blue   # blue или green — куда направлен трафик
```
`values.yaml` — значения по умолчанию. Переопределяются при `helm install/upgrade`:
- `-f values-prod.yaml` — файл со значениями для production
- `--set backend.replicas=5` — одно значение из командной строки
- `--set-string` — принудительно как строка (для тегов которые выглядят как числа)

Значения вложены иерархически. В шаблоне доступны как `.Values.backend.image.repository`. Обязательный к замене параметр здесь — `postgres.password` (лежит открытым текстом, что README прямо называет антипаттерном для production).

`pullPolicy: IfNotPresent` — скачивать образ только если его нет локально. `Always` — всегда тянуть (для `latest`). `Never` — никогда не скачивать (образ должен быть локально, для offline).

Отдельная секция `blueGreen` не подставляется автоматически в шаблоны — она используется вручную через `--set backend.slot=green` при blue-green деплое (см. практику ниже), а не через условную логику внутри templates.

---

#### templates/backend.yaml (реальный шаблон, без именованных helper'ов)

Один файл описывает сразу ConfigMap + Deployment + Service подряд через `---` — это нормально для Helm, шаблон не обязан соответствовать 1 файл = 1 ресурс:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: {{ .Values.namespace }}
  annotations:
    helm.sh/chart: "{{ .Chart.Name }}-{{ .Chart.Version }}"
spec:
  replicas: {{ .Values.backend.replicas }}
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1   # максимум 1 Pod может быть недоступен во время обновления
      maxSurge: 1         # можно создать 1 дополнительный Pod сверх replicas
  template:
    spec:
      containers:
        - name: backend
          image: {{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}
          imagePullPolicy: {{ .Values.backend.image.pullPolicy }}
          envFrom:
            - secretRef:
                name: postgres-secret
            - configMapRef:
                name: backend-config
          resources:
            requests:
              memory: {{ .Values.backend.resources.requests.memory }}
              cpu: {{ .Values.backend.resources.requests.cpu }}
```
`{{ }}` — блоки шаблонизатора Go (Go template), напрямую подставляют значения из `.Values` — в этом чарте нет именованных helper-шаблонов (`_helpers.tpl` с `include`), в отличие от многих публичных чартов. Для проекта такого размера это осознанное упрощение: меньше уровней косвенности, весь шаблон читается сверху вниз без прыжков в другой файл.

`strategy.type: RollingUpdate` + `maxUnavailable`/`maxSurge` — управляют тем, как именно происходит обновление Pod'ов при `helm upgrade`: не больше 1 недоступного и не больше 1 лишнего одновременно.

`envFrom` + `secretRef`/`configMapRef` — переменные окружения приходят из `postgres-secret` и `backend-config` целиком, а не по одной через `valueFrom` (тот способ тоже валиден, просто многословнее — см. Level 5).

**Именованные шаблоны (`_helpers.tpl`) — для справки, в этом чарте их нет:** в больших публичных чартах вместо `name: backend` часто пишут `name: {{ include "bulletin-board.fullname" . }}`, где `_helpers.tpl` содержит:
```
{{- define "bulletin-board.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
```
Это нужно когда один и тот же chart ставят под разными именами релизов в один namespace несколько раз — имена ресурсов не должны сталкиваться. Для нашего учебного проекта это избыточно, но полезно знать паттерн для реальных production-чартов.

---

### Ключевые команды

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `helm install` | Установить chart | `helm install bulletin-board ./bulletin-board -f values-prod.yaml` |
| `helm upgrade` | Обновить релиз | `helm upgrade bulletin-board ./bulletin-board --set backend.image.tag=v1.2.3` |
| `helm rollback` | Откатить | `helm rollback bulletin-board 1` |
| `helm list` | Список релизов | `helm list -n bulletin-board` |
| `helm history` | История релизов | `helm history bulletin-board` |
| `helm template` | Показать сгенерированные манифесты | `helm template bulletin-board ./bulletin-board` |

### Практика

**Шаг 1 — Изучить структуру chart**

```bash
cd level-7-helm
ls bulletin-board/
# Chart.yaml    — метаданные (имя, версия, описание)
# values.yaml   — значения по умолчанию
# templates/    — манифесты с шаблонами: namespace, postgres, redis, backend, nginx
```

```bash
cat bulletin-board/templates/backend.yaml
```

Заметь синтаксис шаблонизатора:
```yaml
replicas: {{ .Values.backend.replicas }}
image: {{ .Values.backend.image.repository }}:{{ .Values.backend.image.tag }}
```

**Шаг 2 — Посмотреть что сгенерируется**

```bash
helm template bulletin-board ./bulletin-board
helm template bulletin-board ./bulletin-board -f values-prod.yaml
```

**Шаг 3 — Установить**

```bash
helm install bulletin-board ./bulletin-board \
  --namespace bulletin-board \
  --create-namespace

helm list -n bulletin-board
kubectl get pods -n bulletin-board
```

**Шаг 4 — Обновить версию**

```bash
helm upgrade bulletin-board ./bulletin-board \
  --set backend.image.tag=v1.2.3

helm history bulletin-board
```

**Шаг 5 — Blue-Green деплой**

В этом чарте blue-green — не два отдельных Helm-релиза, а один релиз с переключением slot'а через `--set` и точечным патчем Service (полный разбор — `level-7-helm/README.md`, Шаг 7):

```bash
# Blue уже развёрнут по умолчанию — проверяем
kubectl get pods -n bulletin-board -l slot=blue

# Создаём green Deployment новым релизом того же чарта с другим слотом
helm upgrade bulletin-board ./bulletin-board \
  --set backend.slot=green \
  --set backend.image.tag=v1.1.0

kubectl rollout status deployment/backend-green -n bulletin-board

# Переключаем трафик на green (меняем Service selector)
kubectl patch service backend -n bulletin-board \
  -p '{"spec":{"selector":{"slot":"green"}}}'

# Если всё хорошо — удаляем blue
kubectl delete deployment backend-blue -n bulletin-board

# Если что-то пошло не так — откат за секунду, обратный patch
kubectl patch service backend -n bulletin-board \
  -p '{"spec":{"selector":{"slot":"blue"}}}'
```

**Преимущество blue-green перед rolling update:** переключение мгновенное (один patch), старая версия работает параллельно и доступна для мгновенного отката.

**Шаг 6 — Откат**

```bash
helm rollback bulletin 1 -n bulletin-board
# "1" — номер ревизии. Смотри в helm history.
```

---

> **Как в проде:** Helm используют везде где есть K8s. Chart хранится в Git рядом с кодом. В CI/CD: `helm upgrade --install --atomic` — если деплой не прошёл healthcheck за timeout, автоматически откатывается. Официальные helm charts есть для большинства open-source инструментов: `helm install prometheus prometheus-community/kube-prometheus-stack`.

---

### Итог уровня 7

Ты умеешь:
- [ ] Создать Helm chart с параметризованными манифестами
- [ ] Деплоить с разными values для разных окружений
- [ ] Делать blue-green деплой
- [ ] Откатить на предыдущую ревизию

**Боль которую ты чувствуешь:** кто-то вошёл на сервер и вручную изменил ConfigMap — теперь реальное состояние кластера отличается от того что в Git. Обнаруживаешь это случайно через неделю. Нужен инструмент который следит за соответствием → Уровень 8.

---

## Уровень 8 — GitOps / ArgoCD

### Зачем это нужно

В K8s можно руками изменить любой ресурс: `kubectl edit deployment backend`. Это удобно при диагностике — и опасно в production. Через неделю никто не помнит что было изменено. Git и реальный кластер расходятся. Это называется **configuration drift**.

**GitOps** — принцип: Git — единственный источник правды. Любое изменение кластера идёт через Git (PR → review → merge → деплой). Прямые `kubectl edit` в production запрещены.

**ArgoCD** — инструмент который следит за Git репозиторием и автоматически синхронизирует кластер. Если кто-то вручную изменил ресурс — ArgoCD это обнаружит (drift) и предложит синхронизировать.

### Как это работает

ArgoCD — охранник который сравнивает чертёж здания (Git) с реальным зданием (K8s). Если кто-то без разрешения пристроил комнату (изменил ресурс в кластере) — охранник это видит и сигнализирует.

---

### Анатомия ArgoCD Application

Ниже — расширенный пример со всеми частыми опциями (`finalizers`, `retry`, `ignoreDifferences` и т.д.), для понимания что вообще бывает у `Application`. Реальный манифест этого проекта проще — он показан отдельно в разделе "Практика" ниже.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: bulletin-board
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io
spec:
  project: default

  source:
    repoURL: https://github.com/user/devops-project
    targetRevision: main
    path: level-5-kubernetes/k8s

  destination:
    server: https://kubernetes.default.svc
    namespace: bulletin-board

  syncPolicy:
    automated:
      prune: true
      selfHeal: true
      allowEmpty: false
    syncOptions:
      - CreateNamespace=true
      - PrunePropagationPolicy=foreground
      - RespectIgnoreDifferences=true
    retry:
      limit: 3
      backoff:
        duration: 5s
        factor: 2
        maxDuration: 3m

  ignoreDifferences:
    - group: apps
      kind: Deployment
      jsonPointers:
        - /spec/replicas
```
`namespace: argocd` в metadata — Application-ресурс всегда живёт в namespace `argocd`, независимо от того куда деплоишь.

`finalizers: resources-finalizer.argocd.argoproj.io` — при удалении Application ArgoCD также удалит все K8s-ресурсы которые он создал (каскадное удаление). Без finalizer — удалишь Application, ресурсы останутся "бесхозными".

`project: default` — ArgoCD Project (не K8s namespace) — набор правил доступа: какие репозитории разрешены, какие кластеры/namespace, кто может деплоить. `default` — без ограничений.

`source.targetRevision: main` — следить за веткой `main`. Можно указать тег (`v1.2.3`) или конкретный commit SHA для immutable деплоев.

`source.path: level-5-kubernetes/k8s` — поддиректория в репозитории с манифестами. Один репо может содержать несколько Application-ов для разных сервисов/окружений.

`destination.server: https://kubernetes.default.svc` — деплоить в тот же кластер где живёт ArgoCD. Для внешних кластеров — внешний URL API.

`syncPolicy.automated.prune: true` — удалять K8s-ресурсы которые есть в кластере но исчезли из Git. Без `prune` — устаревшие ресурсы накапливаются. С `prune` — Git — единственная правда.

`syncPolicy.automated.selfHeal: true` — если кто-то вручную изменил ресурс в кластере (kubectl edit, patch, scale) — ArgoCD заметит drift и вернёт к состоянию из Git автоматически.

`ignoreDifferences` — поля которые ArgoCD не считает drift. `/spec/replicas` в Deployment — потому что HPA динамически меняет replicas. Без ignore ArgoCD будет постоянно "исправлять" replicas на значение из Git, мешая автомасштабированию.

`retry` — при неудачной синхронизации повторить с экспоненциальной задержкой: 5с, 10с, 20с (factor=2), но не более 3 минут.

---

### Практика

**Шаг 1 — Установить ArgoCD**

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

# Дождаться пока все Pod-ы поднимутся
kubectl get pods -n argocd -w

# Получить пароль
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

**Шаг 2 — Открыть UI**

```bash
kubectl port-forward svc/argocd-server -n argocd 8080:443
```

Открой `https://localhost:8080` — admin / <пароль из шага 1>.

**Шаг 3 — Создать приложение**

```bash
cd level-8-gitops
# Посмотреть Application manifest (реальный файл этого проекта)
cat apps/bulletin-board-app.yml
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: bulletin-board
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/YOUR_USERNAME/devops-project.git
    targetRevision: main
    path: level-5-kubernetes/k8s
  destination:
    server: https://kubernetes.default.svc
    namespace: bulletin-board
  syncPolicy:
    automated:
      prune: true      # удалять ресурсы которых нет в Git
      selfHeal: true   # восстанавливать изменённые вручную ресурсы
    syncOptions:
      - CreateNamespace=true
```

```bash
kubectl apply -f apps/bulletin-board-app.yml
```

**Шаг 4 — Наблюдать автоматическую синхронизацию**

Измени `replicas: 3` на `replicas: 5` в `level-5-kubernetes/k8s/backend/deployment.yml`, закоммить и запушь в Git:

```bash
git add level-5-kubernetes/k8s/
git commit -m "scale backend to 5 replicas"
git push origin main
```

ArgoCD обнаружит изменение в Git через 3 минуты (или сразу при webhook) и применит его к кластеру.

**Шаг 5 — Наблюдать drift detection**

```bash
# Вручную измени кластер (так нельзя в production!)
kubectl scale deployment backend --replicas=1 -n bulletin-board

# Через несколько секунд ArgoCD увидит drift
# В UI: Status = OutOfSync
# При selfHeal: автоматически вернёт 5 реплик
```

---

> **Как в проде:** все изменения инфраструктуры идут через PR. Reviewer проверяет `kubectl diff` — что изменится в кластере. После мержа ArgoCD применяет автоматически. В Slack/Telegram уведомление: "ArgoCD: bulletin-board synced, 5 resources updated". Прямые команды `kubectl edit/patch/scale` в production — нарушение процесса.

**Боль которую ты чувствуешь:** ArgoCD деплоит всё что лежит в Git — включая `secret.yml` с паролем открытым текстом. Git — источник правды, но секреты в Git класть нельзя. Противоречие → Уровень 8.5.

---

## Уровень 8.5 — Секреты в GitOps

### Зачем это нужно

GitOps требует «всё состояние — в Git», безопасность требует «секретов в Git не бывает». Наш `postgres-secret` лежит в репозитории открытым текстом (`stringData`) — для локального minikube это учебный плейсхолдер, для реального проекта — утечка. И помни: base64 в поле `data` — это **кодировка, а не шифрование**, декодируется одной командой.

**Sealed Secrets** снимает противоречие: в Git хранится SealedSecret — секрет, зашифрованный публичным ключом кластера. Расшифровать его может только контроллер внутри кластера (приватный ключ не покидает кластер). Такой файл можно коммитить даже в публичный репозиторий.

### Как это работает

Почтовый ящик с щелью: бросить письмо (зашифровать `kubeseal`-ом) может кто угодно, достать (расшифровать) — только владелец ключа от дверцы (контроллер в кластере). Git — фотография ящика: письма видны, содержимое — нет.

### Практика

Полные шаги — `level-8.5-secrets/README.md`: установка контроллера и kubeseal, запечатывание `postgres-secret`, полный GitOps-цикл через ArgoCD, три сценария «сломай намеренно» (чужой namespace, удалённый контроллер, потерянный приватный ключ).

Обзорно там же: **SOPS + age** (шифрование любых файлов в Git) и **External Secrets Operator** (секреты во внешнем хранилище — Vault, cloud Secret Manager; в Git только ссылка).

**Боль которую ты чувствуешь:** кластер и приложение воспроизводимы из Git, но сама инфраструктура (VM, сети, диски) создана руками и невоспроизводима → Уровень 9.

---

## Уровень 9 — Terraform

### Зачем это нужно

Ты создал сервер в AWS Console — кликами. Потом ещё один. Потом security group, load balancer, RDS. Через месяц надо создать такое же окружение для staging. Ты помнишь какие настройки выбирал? Нет. Начинаешь заново — получается немного другое.

**Terraform** — Infrastructure as Code. Описываешь инфраструктуру в `.tf` файлах. Terraform сам создаёт/обновляет/удаляет ресурсы. Идемпотентно: применяй сколько угодно раз — результат одинаковый. Версионируется в Git как код.

### Как это работает

Terraform — архитектурный план здания. Ты рисуешь план (`.tf` файлы), а строители (провайдеры: AWS, GCP, DigitalOcean) строят по нему. Если нужно второе такое же здание — применяешь тот же план.

---

### Анатомия Terraform файлов

#### main.tf (блок terraform)

В этом проекте Terraform управляет **локальными Docker-контейнерами** (`kreuzwerker/docker` provider), не облаком — так можно попрактиковать state/plan/apply без счёта от AWS/DigitalOcean. Реальный файл — `level-9-terraform/environments/dev/main.tf`:

```hcl
terraform {
  required_version = ">= 1.9"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }

  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "docker" {}
```
`required_version` — минимальная версия Terraform CLI. Защита от запуска старой версией с новым синтаксисом.

`required_providers` — провайдеры которые нужно скачать. `terraform init` скачивает их в `.terraform/`. `source` — реестр провайдера (`registry.terraform.io/kreuzwerker/docker`). `version = "~> 3.0"` — **pessimistic constraint operator**: принимает 3.x, но не 4.0. Никогда не убирай версионирование провайдеров — их breaking changes сломают твой код.

`backend "local"` — state хранится обычным файлом `terraform.tfstate` рядом с кодом. Это осознанное учебное упрощение: локальный state нельзя безопасно использовать в команде (нет locking — двое запустят `apply` одновременно, state повредится). **В реальном облачном проекте** вместо этого пишут `backend "s3" { bucket = "my-terraform-state"; key = "bulletin-board/prod/terraform.tfstate"; dynamodb_table = "terraform-state-lock"; encrypt = true }` — S3 хранит файл, DynamoDB-таблица даёт distributed locking, `encrypt` шифрует его (state содержит пароли в открытом виде!).

---

#### variables.tf

Реальные переменные этого проекта:
```hcl
variable "env" {
  description = "Название окружения (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "db_password" {
  description = "Пароль PostgreSQL. В prod передавать через TF_VAR_db_password, не хардкодить!"
  type        = string
  sensitive   = true  # не выводить в terraform plan/apply
  default     = "postgres-dev-only"
}

variable "secret_key" {
  description = "JWT secret key. В prod — из secrets manager."
  type        = string
  sensitive   = true
  default     = "dev-secret-key-change-in-prod"
}

variable "nginx_port" {
  description = "Внешний порт Nginx"
  type        = number
  default     = 8088
}
```
`type` — string, number, bool, list(string), map(string), object({...}). Строгая типизация предотвращает ошибки. `sensitive = true` — значение скрывается в выводах. Всегда помечай пароли и токены — заметь, что даже с `sensitive` у переменной есть `default` со значением для dev-окружения, а не обязательная передача каждый раз.

**Чего нет в реальном файле, но полезно знать:** блок `validation` для проверки допустимых значений ДО любых вызовов провайдера:
```hcl
variable "env" {
  # ...
  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be 'dev', 'staging' or 'prod'."
  }
}
```
Это значительно лучше, чем получить непонятную ошибку от провайдера уже во время apply.

---

#### main.tf (ресурсы)

Реальный набор ресурсов — сеть, postgres, backend (собирается из исходников), nginx:

```hcl
resource "docker_network" "app" {
  name   = "${var.env}-bulletin-board"
  driver = "bridge"
}

resource "docker_image" "postgres" {
  name = "postgres:16-alpine"
}

resource "docker_volume" "postgres_data" {
  name = "${var.env}-postgres-data"
}

resource "docker_container" "postgres" {
  name  = "${var.env}-postgres"
  image = docker_image.postgres.image_id

  env = [
    "POSTGRES_DB=${var.db_name}",
    "POSTGRES_USER=${var.db_user}",
    "POSTGRES_PASSWORD=${var.db_password}",
  ]

  networks_advanced {
    name = docker_network.app.name
  }

  volumes {
    volume_name    = docker_volume.postgres_data.name
    container_path = "/var/lib/postgresql/data"
  }
}
```
`resource "TYPE" "LOCAL_NAME"` — TYPE — тип ресурса провайдера, LOCAL_NAME — имя внутри Terraform (не имя в облаке). Обращение: `docker_container.postgres.id`.

`image = docker_image.postgres.image_id` и `volume_name = docker_volume.postgres_data.name` — это и есть **implicit dependency**: Terraform видит, что `docker_container.postgres` ссылается на атрибуты `docker_image.postgres` и `docker_volume.postgres_data`, и создаёт их ПЕРВЫМИ, в правильном порядке. Не надо объявлять порядок явно.

```hcl
resource "docker_image" "backend" {
  name = "bulletin-board-backend:${var.backend_version}"
  build {
    context    = "${path.root}/../../level-1-monolith/backend"
    dockerfile = "Dockerfile"
  }
  triggers = {
    version = var.backend_version   # пересобрать образ при изменении версии
  }
}

resource "docker_container" "backend" {
  name  = "${var.env}-backend"
  image = docker_image.backend.image_id

  env = [
    "DATABASE_URL=postgresql://${var.db_user}:${var.db_password}@${var.env}-postgres:5432/${var.db_name}",
    "SECRET_KEY=${var.secret_key}",
  ]

  networks_advanced {
    name = docker_network.app.name
  }

  depends_on = [docker_container.postgres]
}
```
`build { context, dockerfile }` — Terraform умеет не только запускать готовые образы, но и собирать их из Dockerfile, как `docker build`. `triggers` — принудительно пересобрать ресурс, когда меняется значение (иначе Terraform не заметит, что нужно пересобрать образ при той же команде `build`).

`depends_on = [docker_container.postgres]` — **явная зависимость**: используется, когда implicit (через ссылку на атрибут) не подходит — backend не читает никакой атрибут postgres напрямую в конфиге, но должен быть создан после него.

---

#### outputs.tf

```hcl
output "app_url" {
  description = "URL приложения"
  value       = "http://localhost:${var.nginx_port}"
}

output "postgres_container_id" {
  description = "ID PostgreSQL контейнера"
  value       = docker_container.postgres.id
}

output "network_name" {
  description = "Имя Docker-сети"
  value       = docker_network.app.name
}
```
Outputs — значения которые Terraform выводит после `apply`. Используются: для отображения пользователю ("вот URL приложения"), как входные данные для другого Terraform модуля, в CI/CD для передачи значения следующему шагу. **В облачном проекте** тем же способом выводят публичный IP сервера и, например, готовую SSH-команду для подключения (`value = "ssh ubuntu@${...ip_address}"`), а чувствительные outputs (пароли, токены) помечают `sensitive = true`, чтобы их не увидеть в обычном выводе `terraform output`.

---

#### Что такое terraform.tfstate

```json
{
  "version": 4,
  "resources": [
    {
      "type": "docker_container",
      "name": "postgres",
      "instances": [
        {
          "attributes": {
            "id": "a1b2c3d4e5f6",
            "name": "dev-postgres",
            "image": "sha256:abcdef..."
          }
        }
      ]
    }
  ]
}
```
State — карта соответствия Terraform-ресурсов и реальных облачных объектов. При `terraform plan` Terraform:
1. Читает `.tf` файлы (желаемое состояние)
2. Читает state (последнее известное состояние)
3. Запрашивает API провайдера (реальное текущее состояние)
4. Вычисляет diff: что создать/изменить/удалить

**Никогда не редактируй state вручную.** Если нужно — `terraform state mv`, `terraform state rm`, `terraform import`.

---

### Ключевые команды

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `terraform init` | Скачать провайдеры | `terraform init` |
| `terraform plan` | Показать что изменится | `terraform plan -out=tfplan` |
| `terraform apply` | Применить изменения | `terraform apply tfplan` |
| `terraform destroy` | Удалить всю инфраструктуру | `terraform destroy` |
| `terraform state list` | Список ресурсов в state | — |
| `terraform output` | Вывести outputs | `terraform output server_ip` |

### Практика

**Шаг 1 — Изучить структуру**

```bash
cd level-9-terraform/environments/dev
ls
# main.tf            — основные ресурсы (docker_network, docker_container и т.д.)
# variables.tf       — переменные
# outputs.tf         — выходные значения
# terraform.tfvars   — значения переменных для dev-окружения
```

```bash
cat main.tf
```

**Шаг 2 — Инициализация**

```bash
terraform init
# Скачает provider kreuzwerker/docker в .terraform/
```

**Шаг 3 — План**

```bash
terraform plan
```

Увидишь что будет создано (сеть, volume, 3 образа, 3 контейнера):
```
+ docker_network.app
+ docker_volume.postgres_data
+ docker_image.postgres
+ docker_container.postgres
+ docker_image.backend
+ docker_container.backend
+ docker_image.nginx
+ docker_container.nginx

Plan: 8 to add, 0 to change, 0 to destroy.
```

**Шаг 4 — Применить**

```bash
terraform apply
# Введи "yes"

terraform output
# app_url = "http://localhost:8088"
```

```bash
# Убедиться что реально поднялось:
docker ps | grep dev-
curl http://localhost:8088
```

**Шаг 5 — Понять state**

```bash
cat terraform.tfstate   # не редактируй руками!
terraform state list
```

State — память Terraform о том что уже создано. Если state потерян — Terraform не знает о существующих ресурсах → опасность дублирования (попробует создать всё заново, а старые контейнеры останутся висеть отдельно).

`backend "local"` в этом проекте хранит state прямо в файле рядом с кодом — годится для обучения, но не для команды (см. заметку про `backend "s3"` выше).

**Шаг 6 — Изменить инфраструктуру**

Измени `nginx_port = 8088` на `nginx_port = 8090` в `terraform.tfvars`. Запусти `terraform plan` — увидишь, что `docker_container.nginx` будет пересоздан (смена порта требует пересоздания контейнера, не просто патч на лету). `terraform apply`, потом `curl http://localhost:8090`.

---

### Что сломать намеренно — Уровень 9

**Поломка 1 — Потерять state**

```bash
mv terraform.tfstate terraform.tfstate.backup
terraform plan
# Terraform думает что ничего не создано и хочет создать всё заново!
# В облаке это означает дублирование ресурсов и лишние деньги;
# здесь — вторую копию контейнеров с теми же именами, apply упадёт на конфликте имён

mv terraform.tfstate.backup terraform.tfstate
```

**Поломка 2 — Изменить ресурс вручную мимо Terraform**

```bash
# Останови и запусти nginx-контейнер с другим портом напрямую через Docker, в обход Terraform:
docker stop dev-nginx
docker rm dev-nginx
docker run -d --name dev-nginx --network dev-bulletin-board -p 9999:80 nginx:alpine
```
Запусти `terraform plan`. Увидишь drift — Terraform обнаружит, что реальный контейнер не соответствует тому, что описано в `.tf` файлах, и предложит пересоздать его в исходном виде (порт из `terraform.tfvars`, а не 9999). Если применить — Terraform вернёт всё к состоянию из кода, ручное изменение будет потеряно. Именно так же ведёт себя `digitalocean_droplet` или любой другой облачный ресурс, изменённый в консоли мимо Terraform.

---

> **Как в проде:** Terraform state хранится в S3 + DynamoDB (для locking — чтобы двое не применяли одновременно). Запуск через CI/CD: `plan` в PR (видно что изменится), `apply` после мержа. `terraform destroy` в production требует дополнительного подтверждения — это удалит ВСЁ.

---

### Справочник команд — Уровень 9

| Команда | Описание |
|---------|---------|
| `terraform init` | Инициализация: скачать провайдеры |
| `terraform plan` | Что изменится? (dry run) |
| `terraform apply` | Применить изменения |
| `terraform destroy` | Удалить всё (осторожно!) |
| `terraform state list` | Список ресурсов в state |
| `terraform state show <resource>` | Детали ресурса в state |
| `terraform state rm <resource>` | Удалить ресурс из state (без уничтожения) |
| `terraform import <type>.<name> <id>` | Импортировать существующий ресурс |
| `terraform init -migrate-state` | Переехать на новый backend |
| `terraform force-unlock <ID>` | Снять зависший lock |
| `terraform validate` | Проверить синтаксис .tf файлов |
| `terraform fmt` | Автоформатирование кода |

### На собеседовании спросят

**Q: Что такое Terraform State и зачем он нужен?**
A: JSON-файл где Terraform хранит информацию о созданных ресурсах и их реальных ID. Без state Terraform не знает что уже создал и будет пытаться создать дубликаты. В команде — хранится в remote backend (S3, GCS) с locking чтобы не было конфликтов при параллельном apply.

**Q: Зачем нужен remote state и как работает state locking?**
A: Remote state решает проблему нескольких разработчиков: у каждого своя копия → расходятся → конфликт. Remote state: одна копия в S3, все работают с ней. State locking: при старте apply записывается lock в DynamoDB, другой apply получает ошибку "state locked by <user>". Без locking два параллельных apply повредят state.

**Q: Чем Terraform отличается от Ansible?**
A: Terraform — declarative provisioning инфраструктуры (создание VM, сетей, баз). Ansible — imperative конфигурирование серверов (установка пакетов, настройка сервисов). Используются вместе: Terraform создаёт VM, Ansible её настраивает. Terraform знает о жизненном цикле ресурсов (create/update/destroy), Ansible — нет.

**Q: Что произойдёт если terraform.tfstate попадёт в публичный Git?**
A: Немедленная компрометация. State содержит все атрибуты ресурсов в открытом виде: пароли БД, API-ключи, токены, IP-адреса. Нужно немедленно ротировать все credentials. Профилактика: `.gitignore` для `*.tfstate`, S3 bucket с `encrypt=true` и закрытым доступом.

**Q: Что такое terraform import?**
A: Команда для добавления существующего ресурса (созданного вне Terraform) в state. `terraform import docker_container.postgres dev-postgres` — Terraform узнаёт о существующем контейнере и начинает им управлять. Важно: код (`.tf` файл) нужно написать вручную, import только обновляет state.

### Итог уровня 9

Ты умеешь:
- [ ] Написать Terraform конфигурацию (provider, resource, variable, output)
- [ ] Читать `terraform plan` и понимать `+`, `~`, `-` изменения
- [ ] Объяснить что такое state и почему он важен
- [ ] Настроить remote state backend с locking (MinIO локально или S3 в prod)
- [ ] Мигрировать local state в remote через `terraform init -migrate-state`
- [ ] Импортировать существующий ресурс через `terraform import`
- [ ] Убедиться что `*.tfstate` не в Git

**Боль которую ты чувствуешь:** Terraform создал инфраструктуру, но настройка каждого сервера — ещё несколько часов ручной работы по SSH. → Уровень 10: Ansible.

---

## Уровень 10 — Ansible

### Зачем это нужно

Terraform создал 10 серверов. Теперь на каждый надо: установить Docker, настроить firewall, создать пользователей, скопировать SSH ключи, задеплоить приложение. Через SSH на каждый по очереди — это несколько часов ручной работы. И при малейшем изменении — снова по кругу.

**Ansible** — автоматизация настройки серверов (Configuration Management). Описываешь что должно быть на сервере в YAML-плейбуке, Ansible применяет на все серверы параллельно через SSH. Идемпотентно: запусти дважды — результат тот же.

### Как это работает

Ansible — шеф-повар который готовит по одному рецепту (плейбуку) сразу на 100 кухнях (серверах) параллельно. Рецепт один, результат одинаковый везде.

В отличие от Terraform (управление инфраструктурой), Ansible управляет **тем что внутри сервера**: пакеты, файлы, сервисы, пользователи.

---

### Анатомия Ansible файлов

#### inventory/hosts.ini (инвентарь)

Реальный инвентарь этого проекта — не YAML, а классический INI-формат:
```ini
[local]
localhost ansible_connection=local

[webservers]
# devops-vm-1 ansible_host=192.168.1.100 ansible_user=ubuntu
# devops-vm-2 ansible_host=192.168.1.101 ansible_user=ubuntu

[all:vars]
ansible_python_interpreter=/usr/bin/python3
```
`[local]` — группа с одним хостом `localhost` и `ansible_connection=local`: Ansible выполняет задачи напрямую, без SSH вообще. `[webservers]` — группа для реальных удалённых серверов, по умолчанию закомментирована (раскомментируй и впиши IP для multi-server сценария). `[all:vars]` — переменные для всех групп сразу.

Настройки самого Ansible (не хостов) — в `ansible.cfg` рядом:
```ini
[defaults]
inventory         = inventory/hosts.ini
remote_user       = ubuntu
private_key_file  = ~/.ssh/id_rsa
host_key_checking = False   # для учебной среды; в production — включить
stdout_callback   = yaml    # читаемый вывод вместо json-простыни
```

INI-формат проще YAML-инвентаря для небольшого числа хостов, но менее гибкий для сложной иерархии групп. YAML-инвентарь (с `children`, вложенными группами и `ansible_host`/`ansible_port` на каждый хост) — тоже валидный формат Ansible, просто не тот, что выбран в этом проекте:
```yaml
all:
  children:
    web:
      hosts:
        web1:
          ansible_host: 10.0.0.1
      vars:
        ansible_user: ubuntu
```

**Приоритет переменных** (от низшего к высшему): `all:vars` < `group:vars` < `host:vars` < переменные в playbook < `--extra-vars` в командной строке. Если одна переменная определена на нескольких уровнях — побеждает более специфичная.

---

#### playbooks/site.yml (главный плейбук, реальный)

```yaml
- name: Configure all servers
  hosts: all
  become: true
  gather_facts: true

  vars:
    kubectl_version: "v1.31.0"
    github_username: "{{ lookup('env', 'GITHUB_USERNAME') | default('change-me') }}"

  roles:
    - role: common
      tags: [common, base]
    - role: docker
      tags: [docker]
    - role: tools
      tags: [tools, k6, kubectl, helm]
    - role: app
      tags: [app, deploy]
      when: deploy_app | default(false) | bool
```
`hosts: all` — применять ко всем хостам инвентаря (в этом проекте по умолчанию это просто `localhost`). `all` — ко всем группам. `web1` — к конкретному хосту. `web:!web1` — ко всем в web кроме web1.

`become: true` — выполнять задачи от имени другого пользователя (по умолчанию root через sudo).

`gather_facts: true` — перед выполнением задач Ansible собирает факты о хосте: OS, версия, IP-адреса, память, CPU. Доступны как `ansible_distribution`, `ansible_memtotal_mb`, `ansible_default_ipv4.address` (это то, чем пользуется `check.yml`, см. Практику ниже).

**Роли выполняются строго по порядку списка**: `common` → `docker` → `tools` → `app`. `tags` позволяет запускать выборочно: `ansible-playbook site.yml --tags docker`. `when: deploy_app | default(false) | bool` — роль `app` пропускается по умолчанию (значение `deploy_app` не задано → `false`); её включают явно флагом `-e deploy_app=true`, чтобы не деплоить приложение при каждой обычной настройке сервера.

**Чего в этом плейбуке нет, но бывает полезно в других сценариях:** `serial: 1` — выполнять по одному серверу за раз вместо параллельно (полезно для rolling deploy на много хостов сразу); `vars_files: [secrets.yml]` — подключить отдельный файл с переменными (в этом проекте секреты идут через `inventory/group_vars/all/vault.yml`, см. Ansible Vault ниже).

```yaml
# roles/docker/tasks/main.yml (фрагмент)
- name: Add Docker repository
  apt_repository:
    repo: "deb [arch=amd64] https://download.docker.com/linux/ubuntu {{ ansible_distribution_release }} stable"
    state: present

- name: Install Docker Engine
  apt:
    name:
      - docker-ce
      - docker-ce-cli
      - containerd.io
      - docker-compose-plugin
    update_cache: true
    state: present
  notify: Restart Docker
```
`state: present` — установить если не установлено. `state: latest` — установить и обновить до последней версии. `state: absent` — удалить (роль `docker` начинает именно с этого — удаляет старые пакеты `docker.io`/`docker-engine` перед установкой правильной версии из официального репозитория Docker, а не из apt Ubuntu). `update_cache: true` — `apt-get update` перед установкой.

`tags: [docker]` на уровне роли — можно запускать только эту роль: `ansible-playbook site.yml --tags docker`, или пропускать: `--skip-tags docker`.

`notify: Restart Docker` — триггер для handler. Если задача изменила что-то (`changed`, например пакет реально установился/обновился) — в конце роли будет вызван handler "Restart Docker". Если изменений нет — handler не вызывается.

```yaml
# roles/app/tasks/main.yml (фрагмент)
- name: Clone / update repository
  git:
    repo: "{{ app_repo }}"
    dest: "{{ app_dir }}"
    version: main
    update: true       # если уже клонирован — git pull

- name: Start application with docker compose
  community.docker.docker_compose_v2:
    project_src: "{{ app_dir }}/{{ app_level }}"
    build: always
    state: present
```
`git` модуль — клонирует репозиторий при первом запуске, при повторных — обновляет (`git pull`), идемпотентно. `community.docker.docker_compose_v2` — модуль-обёртка над `docker compose`, управляет стеком декларативно так же, как обычные модули управляют пакетами или файлами; `app_level` — переменная, определяющая, какой уровень проекта (`level-1-monolith`, `level-2-scaling`...) реально задеплоить на этот раз.

Handlers — специальные задачи, вызываемые через `notify`. Выполняются в конце плейбука (после всех tasks роли), один раз, в порядке объявления, даже если несколько задач вызвали один и тот же handler.

---

#### Анатомия роли (Role)

```
roles/
  docker/
    tasks/
      main.yml        ← точка входа, может include другие файлы
    handlers/
      main.yml        ← handlers роли
    templates/
      daemon.json.j2  ← Jinja2 шаблоны
    files/
      logrotate.conf  ← статические файлы (для copy)
    vars/
      main.yml        ← переменные роли (высокий приоритет)
    defaults/
      main.yml        ← переменные по умолчанию (низкий приоритет)
    meta/
      main.yml        ← зависимости от других ролей
```
Роль — способ организовать связанные задачи в переиспользуемый модуль. `tasks/main.yml` — обязательный файл, Ansible ищет его автоматически. Остальные папки — опциональны.

`vars/main.yml` vs `defaults/main.yml`: переменные в `vars` переопределяют переменные группы/хоста из inventory. Переменные в `defaults` — самый низкий приоритет, легко переопределяются. Правило: "значения которые пользователь роли захочет менять" → `defaults`. "Внутренние константы роли" → `vars`.

Использование ролей в плейбуке:
```yaml
  roles:
    - role: docker
    - role: backend
      vars:
        app_version: "{{ image_tag }}"
```

---

#### Ansible Vault

```bash
# Создать сразу зашифрованный файл с секретами:
ansible-vault create inventory/group_vars/all/vault.yml
# Vault попросит придумать пароль — далее в файл (открывается в редакторе) пишем:
# vault_postgres_password: "SuperSecretPass123"
# vault_jwt_secret: "my-production-secret-key"

# Посмотреть — это cipher text, не YAML:
cat inventory/group_vars/all/vault.yml
# $ANSIBLE_VAULT;1.1;AES256
# 62613263613161303830323...

# Редактировать существующий зашифрованный файл
ansible-vault edit inventory/group_vars/all/vault.yml

# Посмотреть расшифрованное содержимое без редактирования
ansible-vault view inventory/group_vars/all/vault.yml

# Запустить плейбук с расшифровкой на лету
ansible-playbook playbooks/site.yml --ask-vault-pass
# или через файл с паролем (для CI/CD):
echo "my-vault-password" > ~/.vault_pass
chmod 600 ~/.vault_pass
ansible-playbook playbooks/site.yml --vault-password-file ~/.vault_pass
```

`group_vars/all/` — специальное имя папки, Ansible автоматически подхватывает переменные оттуда для группы `all` (то есть для всех хостов), не нужно ничего дополнительно подключать через `vars_files`. Префикс `vault_` в именах переменных — просто соглашение (не обязанность), чтобы визуально отличать секреты в коде задач.

**В CI/CD** vault-пароль хранится в секретах (GitHub Actions → Settings → Secrets), а не в репозитории.

---

### Ключевые команды

| Команда | Что делает | Пример |
|---------|-----------|--------|
| `ansible all -m ping` | Проверить связь с серверами | `ansible web -m ping` |
| `ansible-playbook <file>` | Запустить плейбук | `ansible-playbook deploy.yml` |
| `ansible-playbook --check` | Dry run (что изменится) | `ansible-playbook deploy.yml --check` |
| `ansible-playbook --diff` | Показать diff файлов | `ansible-playbook deploy.yml --diff` |
| `ansible-vault create` | Создать зашифрованный файл с секретами | `ansible-vault create inventory/group_vars/all/vault.yml` |

### Практика

**Шаг 1 — Inventory: список серверов**

```bash
cd level-10-ansible
cat inventory/hosts.ini
```
По умолчанию там только `[local] localhost ansible_connection=local` — работаем с самим собой, `[webservers]` закомментирован (см. Анатомию выше).

**Шаг 2 — Проверить связь**

```bash
ansible all -m ping
```

```
localhost | SUCCESS => {"ping": "pong"}
```

**Шаг 3 — Изучить главный плейбук**

```bash
cat playbooks/site.yml
```
Он ссылается на 4 роли по порядку: `common` (базовые пакеты, таймзона, deploy-пользователь) → `docker` (установка Docker Engine из официального репозитория) → `tools` (k6, kubectl, helm) → `app` (git clone + `docker compose up`, только если `deploy_app=true`).

```bash
cat playbooks/roles/common/tasks/main.yml
cat playbooks/roles/docker/tasks/main.yml
```

**Шаг 4 — Аудит состояния сервера (ещё ничего не меняя)**

```bash
ansible-playbook playbooks/check.yml
```
Покажет ОС, память, диск и статус Docker через `ansible_distribution`/`ansible_memtotal_mb`/`ansible_mounts` — те самые факты, которые Ansible собрал через `gather_facts: true`.

**Шаг 5 — Dry run основного плейбука**

```bash
ansible-playbook playbooks/site.yml --check --diff --tags common,docker
```
Покажет что изменится — без реальных изменений. Тегами `common,docker` ограничиваем прогон только базовой настройкой, не трогая `tools`/`app`.

**Шаг 6 — Применить**

```bash
ansible-playbook playbooks/site.yml --tags common,docker
```

Чтобы сразу задеплоить и приложение (роль `app` пропускается по умолчанию):
```bash
ansible-playbook playbooks/deploy.yml -e "app_level=level-2-scaling"
```

**Шаг 7 — Ansible Vault для секретов**

```bash
ansible-vault create inventory/group_vars/all/vault.yml
# внутри: vault_postgres_password: "...", vault_jwt_secret: "..."

ansible-playbook playbooks/site.yml --ask-vault-pass
```

**Шаг 8 — Роли: организация плейбуков**

```bash
ls playbooks/roles/
# common/   — apt update, базовые пакеты, таймзона, deploy-пользователь
# docker/   — Docker Engine из официального репозитория (не из apt Ubuntu — там старая версия)
# tools/    — k6, kubectl, helm
# app/      — git clone/pull + docker compose up
```

Роли — модульный способ организации задач. Можно переиспользовать: роль `docker` в этом виде подойдёт для любого проекта, не только для доски объявлений.

---

### Что сломать намеренно — Уровень 10

**Поломка 1 — Сломанный таск**

Добавь таск с несуществующим модулем:
```yaml
- name: This will fail
  nonexistent_module:
    param: value
```

Запусти. Ansible упадёт на этом таске. Остальные серверы/таски не затронуты.

**Поломка 2 — Идемпотентность**

Запусти плейбук дважды. Второй раз все таски должны показать `ok` или `changed: 0` — ничего лишнего не произошло. Это фундаментальное свойство Ansible.

---

> **Как в проде:** Ansible запускается в CI/CD после Terraform: сначала создаём инфраструктуру (Terraform), потом настраиваем серверы (Ansible). AWX / Ansible Tower — веб-интерфейс для запуска плейбуков с логами, расписанием, RBAC. Galaxy — репозиторий ролей как Docker Hub: готовые роли для nginx, postgres, redis.

---

## Карта прогрессии боли

```
                    Боль                          Решение
──────────────────────────────────────────────────────────────────────
Уровень 1   "На моей машине работает"          Docker + Docker Compose
            Один бэкенд задыхается             → Уровень 2

Уровень 2   PostgreSQL — новое узкое место     Redis кэширование
            Scale-out обнажает stateful        → Уровень 3
            архитектурные проблемы

Уровень 3   HTTP не защищён                   Traefik + Let's Encrypt
            Деплой роняет сервис               → Уровень 4

Уровень 4   Docker Compose не перезапускает   Kubernetes
            упавшие контейнеры                → Уровень 5
            Несколько серверов — хаос

Уровень 5   Наружу торчит NodePort:30080 —    Ingress + cert-manager
            нестандартный порт, нет TLS       → Уровень 5.5

Уровень 5.5 При инциденте — слепота           Prometheus + Grafana + Loki
            Нет метрик, нет структурных логов → Уровень 6

Уровень 6   Алерты требуют ручной             AI-агент диагностики
            интерпретации 3 ночи              → Уровень 6.5

Уровень 6.5 kubectl apply 8 файлов,           Helm
            нет версионирования деплоев       → Уровень 7

Уровень 7   Configuration drift:              ArgoCD GitOps
            кластер ≠ Git                     → Уровень 8

Уровень 8   ArgoCD деплоит всё из Git,        Sealed Secrets
            но секрет в Git = утечка          → Уровень 8.5

Уровень 8.5 Инфраструктура создаётся          Terraform
            руками, не воспроизводимо         → Уровень 9

Уровень 9   Настройка 10+ серверов —          Ansible
            вручную, медленно, неповторяемо   → Конец
──────────────────────────────────────────────────────────────────────
```

---

## Быстрый справочник по всем уровням

| Уровень | Команда запуска | Основной инструмент |
|---------|----------------|---------------------|
| 1 | `docker compose up --build -d` | Docker Compose |
| 2 | `docker compose up --build -d` | Nginx upstream |
| 3 | `docker compose up --build -d` | Redis |
| 3.5 | `docker compose up -d` | Traefik |
| 4a | `git push` → CI/CD | GitHub Actions |
| 4b | `git push` → GitLab CI | GitLab CE |
| 5 | `kubectl apply -f k8s/` | kubectl + minikube |
| 5.5 | `minikube addons enable ingress` + `kubectl apply -f k8s/` | ingress-nginx + cert-manager |
| 6 | `docker compose up -d` | Prometheus + Grafana |
| 6.5 | `docker compose up -d agent` (локально, не на VPS) | Claude API |
| 7 | `helm install bulletin-board ./bulletin-board -f values-local.yaml` | Helm |
| 8 | `kubectl apply -f argocd/` | ArgoCD |
| 8.5 | `bash install-sealed-secrets.sh` + `kubeseal` | Sealed Secrets |
| 9 | `terraform apply` | Terraform |
| 10 | `ansible-playbook playbooks/site.yml` | Ansible |

---

*Каждый следующий уровень — не просто новый инструмент. Это решение реальной боли которую ты почувствовал на предыдущем.*
