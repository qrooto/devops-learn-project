# Уровень 4 — CI/CD с GitHub Actions

> **Это [руки]** — опциональная ветка 4a (GitHub Actions): команды, эксперименты, поломки. Теория CI/CD и анатомия `deploy.yml` — в `CURRICULUM.md` → «Уровень 4». Легенда `[голова]`/`[руки]` — в START_HERE.md.

## Зачем начинать отсюда?

До этого деплой выглядел так: зашёл на сервер по SSH, написал `docker compose pull && docker compose up`. Это называется **ручной деплой** и у него есть системные проблемы:

- Нет автоматических тестов — можно задеплоить код с очевидной ошибкой
- Деплой роняет сервис на несколько секунд (все контейнеры стоп → все контейнеры старт)
- Нет истории: кто деплоил, когда, какой код
- При ошибке надо вручную откатываться

**CI/CD** (Continuous Integration / Continuous Delivery) — автоматизация от `git push` до работающего приложения на сервере.

## Аналогия

Ручной деплой — как проверять самолёт перед вылетом по памяти. CI/CD — как автоматический чеклист: каждый пункт обязателен, если что-то не так — самолёт не взлетит.

## Архитектура pipeline

```
git push
    │
    └── GitHub Actions запускает runner (Ubuntu container)
            │
            ├── job: test
            │     └── pytest tests/ → если упал: СТОП, дальше не идём
            │
            ├── job: build  (только если test прошёл)
            │     └── docker build → docker push → ghcr.io/username/bulletin-board:sha
            │
            └── job: deploy  (только если build прошёл)
                  └── SSH на сервер → rolling update:
                        stop backend_1 → start backend_1 (новый образ)
                        stop backend_2 → start backend_2
                        stop backend_3 → start backend_3
                        ← backend_2 и _3 продолжают работать пока _1 рестартует
```

**Rolling update** — обновление по одному контейнеру. Пока backend_1 перезапускается, backend_2 и backend_3 продолжают обрабатывать запросы. Пользователь не замечает деплоя.

**ghcr.io** (GitHub Container Registry) — хранилище Docker образов, встроенное в GitHub. Бесплатно для публичных репозиториев. Теги образов — это git commit SHA, поэтому можно точно знать что задеплоено.

---

## Шаг 1 — Разобрать pipeline файл

```bash
cat level-4-cicd/.github/workflows/deploy.yml
```

**Ключевые части:**
```yaml
on:
  push:
    branches: [main]          # запускается только при push в main

jobs:
  test:
    runs-on: ubuntu-latest    # GitHub предоставляет runner
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt && pytest

  build:
    needs: test               # ← запустится ТОЛЬКО если test прошёл
    steps:
      - run: docker build -t ghcr.io/${{ github.actor }}/bulletin-board:${{ github.sha }} .
      - run: docker push ...

  deploy:
    needs: build              # ← запустится только если build прошёл
    steps:
      - run: ssh server "docker pull ... && restart containers"
```

**Задание:** Найди в файле где передаётся `SSH_PRIVATE_KEY`. Почему он берётся из `secrets.SSH_PRIVATE_KEY`, а не прямо написан в yaml?

---

## Шаг 2 — Подготовить SSH-ключ для деплоя

На **виртуальной машине** создай отдельный ключ специально для GitHub Actions:

```bash
# Генерируем ключ без пассфразы (для автоматизации)
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/deploy_key -N ""

# Добавляем публичный ключ в authorized_keys
cat ~/.ssh/deploy_key.pub >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys

# Выводим приватный ключ — он нужен для GitHub Secret
cat ~/.ssh/deploy_key
```

**Почему отдельный ключ, а не основной?**
Принцип минимальных привилегий. Если GitHub Actions скомпрометирован — ты отзываешь только deploy_key, не теряя доступ со своей машины.

---

## Шаг 3 — Настроить GitHub Secrets

GitHub → твой репозиторий → **Settings → Secrets and variables → Actions → New repository secret**

| Имя | Значение | Зачем |
|-----|----------|-------|
| `SERVER_HOST` | IP-адрес VM | куда деплоить |
| `SERVER_USER` | `ubuntu` (или твой user) | от чьего имени SSH |
| `SERVER_SSH_KEY` | содержимое `~/.ssh/deploy_key` | аутентификация |

**Почему Secrets, а не обычные Variables?**
Secrets зашифрованы. В логах pipeline они заменяются на `***`. Даже если логи публичны — ключ не виден.

Проверь что файл deploy.yml ссылается на эти секреты:
```yaml
${{ secrets.SERVER_HOST }}
${{ secrets.SERVER_USER }}
${{ secrets.SERVER_SSH_KEY }}
```

---

## Шаг 4 — Первый деплой

```bash
# Убедись что ты в корне репозитория
git add level-4-cicd/
git commit -m "level-4: add ci/cd pipeline"
git push origin main
```

Зайди в GitHub → **Actions**. Ты увидишь запущенный workflow. Кликни на него — видишь три job в реальном времени.

**Что смотреть:**
- Зелёная птица на каждом job → всё OK
- Красный X → смотри логи, там будет ошибка

Дождись завершения всех трёх. Потом:
```bash
curl http://ВАШ-IP/api/health
# {"status": "ok"}
```

---

## Шаг 4.5 — Сканирование образов на уязвимости (Trivy)

Тесты проверяют что **наш код** работает правильно. Но Docker-образ — это ещё и базовый образ (`python:3.12-slim`), системные библиотеки (openssl, libz, glibc), Python-пакеты (requests, sqlalchemy). В любом из них могут быть **известные уязвимости** (CVE).

Без сканирования ты можешь деплоить образ с дырой уровня CRITICAL и не знать об этом неделями.

**Trivy** — open-source сканер от Aqua Security. Проверяет: базовый образ, системные пакеты, Python/Node/Go зависимости, конфиги (Dockerfile, Kubernetes YAML). Самый популярный инструмент в этой нише.

### Что такое CVE

CVE (Common Vulnerabilities and Exposures) — база данных известных уязвимостей с ID и оценкой серьёзности (CVSS 0-10):

| Уровень | CVSS | Что значит |
|---------|------|-----------|
| CRITICAL | 9.0-10.0 | Можно эксплуатировать удалённо без авторизации |
| HIGH | 7.0-8.9 | Серьёзная, требует внимания |
| MEDIUM | 4.0-6.9 | Можно мониторить, патчить при возможности |
| LOW | 0.1-3.9 | Информационные |

### Практика

**Шаг 1 — Установить Trivy локально**

```bash
# Ubuntu/Debian:
sudo apt-get install -y wget apt-transport-https gnupg
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key \
  | sudo gpg --dearmor -o /usr/share/keyrings/trivy.gpg
echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" \
  | sudo tee /etc/apt/sources.list.d/trivy.list
sudo apt-get update && sudo apt-get install -y trivy

trivy --version
```

**Шаг 2 — Просканировать образ**

```bash
# Сначала собираем образ:
docker build -t bulletin-backend:local ./level-3-caching/backend/

# Полный скан:
trivy image bulletin-backend:local
```

**Что увидишь:**
```
bulletin-backend:local (debian 12.x)
=====================================
Total: 18 (HIGH: 2, MEDIUM: 10, LOW: 6)

┌──────────────────────┬────────────────┬──────────┬────────────────────┬
│ Library              │ Vulnerability  │ Severity │ Installed Version  │
├──────────────────────┼────────────────┼──────────┼────────────────────┤
│ libssl3              │ CVE-2024-5535  │ HIGH     │ 3.0.11-1~deb12u2   │
│ python3.12-minimal   │ CVE-2024-6923  │ HIGH     │ 3.12.2-1           │
│ libc-bin             │ CVE-2024-2961  │ MEDIUM   │ 2.36-9+deb12u4     │
└──────────────────────┴────────────────┴──────────┴────────────────────┘
```

**Шаг 3 — Только HIGH и CRITICAL с exit code**

```bash
# В CI нас волнуют только серьёзные:
trivy image --severity HIGH,CRITICAL bulletin-backend:local

# Выйти с кодом 1 если найдены CRITICAL:
trivy image \
  --severity CRITICAL \
  --exit-code 1 \
  --ignore-unfixed \
  bulletin-backend:local

echo "Exit code: $?"
# 0 = нет CRITICAL  → деплой продолжается
# 1 = есть CRITICAL → CI упадёт, деплоя не будет
```

`--ignore-unfixed` важен: большинство уязвимостей не имеют исправления (апстрим ещё не выпустил патч). Блокировать деплой из-за них неразумно.

**Шаг 4 — Добавить в GitHub Actions workflow**

Открой `.github/workflows/deploy.yml` — уже добавлен job `scan` между `build` и `deploy`:

```bash
cat level-4-cicd/.github/workflows/deploy.yml | grep -A 20 "scan:"
```

**Шаг 5 — Уменьшить количество уязвимостей**

Самый простой способ — обновить базовый образ и системные пакеты:

```dockerfile
# В Dockerfile добавить после RUN pip install:
RUN apt-get update && apt-get upgrade -y \
  && apt-get clean \
  && rm -rf /var/lib/apt/lists/*
```

```bash
# Пересобрать и сравнить:
docker build -t bulletin-backend:patched ./level-3-caching/backend/
trivy image --severity HIGH,CRITICAL bulletin-backend:patched

# Количество HIGH уменьшится — системные пакеты обновились
```

Другой подход: переключиться на образ с актуальными патчами:
```dockerfile
FROM python:3.12-slim-bookworm  # Debian Bookworm с последними патчами
```

**Что важно понять:** полностью убрать все уязвимости невозможно — базовый образ обновляется постепенно. Цель — отсутствие CRITICAL и мониторинг HIGH.

---

## Шаг 5 — Сломать намеренно (CI должен остановить деплой)

Это главный урок уровня: CI — это страховка.

```bash
# Добавь синтаксическую ошибку в бэкенд:
echo "BROKEN = )(" >> level-4-cicd/tests/test_api.py

git add .
git commit -m "broken: testing that ci catches errors"
git push origin main
```

**Что должно произойти:**
1. Job `test` запустился → pytest упал на синтаксической ошибке
2. Job `build` — **не запустился** (есть `needs: test`)
3. Job `deploy` — **не запустился**
4. На сервере работает **старый код** — деплоя не было

В Actions ты увидишь красный pipeline с пометкой на `test`. `build` и `deploy` серые — не запускались.

```bash
# Откатываем:
git revert HEAD
git push origin main
```

Новый pipeline прошёл зелёным — старый код снова в строю.

---

## Шаг 6 — Наблюдать rolling update под нагрузкой

**Терминал 1** — мониторинг контейнеров на сервере:
```bash
watch -n 1 'docker ps --format "table {{.Names}}\t{{.Status}}"'
```

**Терминал 2** — нагрузочный тест:
```bash
k6 run level-2-scaling/load-tests/balancer-test.js
```

**Терминал 3** — запусти деплой:
```bash
git commit --allow-empty -m "trigger: rolling update demo"
git push origin main
```

**Что наблюдать:**
- В Терминале 1: backend_1 останавливается → запускается снова, потом backend_2, потом backend_3
- В Терминале 2: ошибок почти нет, p95 латентность чуть подскакивает на секунду когда инстансов временно 2

Это нулевой даунтайм (zero-downtime deploy).

---

## Шаг 6.5 — Стратегии деплоя: от Recreate до Canary

Ты только что видел rolling update в действии — но это одна из четырёх стратегий. Выбор влияет на даунтайм, риск, скорость отката, потребление ресурсов. Зная все четыре — выбираешь правильную под конкретную ситуацию.

### Сравнение стратегий

| Стратегия | Даунтайм | Откат | Ресурсы | Когда применять |
|-----------|---------|-------|---------|----------------|
| **Recreate** | Да | Мгновенно | ×1 | Stateful сервисы, dev/test окружения |
| **Rolling** | Нет | Медленно (ещё один деплой) | ~×1.3 | Стандартный stateless API |
| **Blue-Green** | Нет | Мгновенно (switch back) | ×2 | Когда критичен быстрый rollback |
| **Canary** | Нет | Мгновенно (убрать canary) | ~×1.2 | Высокорискованные изменения |

---

### Стратегия 1 — Recreate

Останавливаем всё → запускаем всё.

```
v1: [b1] [b2] [b3]
       ↓ down
    [  ] [  ] [  ]   ← ДАУНТАЙМ: пользователи видят 502
       ↓ up
v2: [b1] [b2] [b3]
```

Плюс: простота. Нет риска что v1 и v2 видят разную схему БД.
Минус: явный даунтайм — сколько бы быстро контейнеры ни поднимались.

Когда уместно: batch job-ы, базы данных, dev-окружения, сервисы с допустимым коротким даунтаймом.

---

### Стратегия 2 — Rolling Update

Обновляем по одному контейнеру, остальные обслуживают трафик.

```
v1: [b1] [b2] [b3]
       ↓ обновить b1
    [v2:b1] [v1:b2] [v1:b3]   ← две версии одновременно!
       ↓ обновить b2
    [v2:b1] [v2:b2] [v1:b3]
       ↓ обновить b3
v2: [b1] [b2] [b3]
```

**Критичное следствие:** в момент деплоя рядом работают v1 и v2. Один пользователь может получить ответ от v1, следующий — от v2. Если в v2 изменился формат API — это сломает клиентов. Поэтому при rolling update **изменения API должны быть обратно совместимы**.

Откат = новый rolling update со старым образом (занимает столько же времени).

---

### Стратегия 3 — Blue-Green

Два полных окружения: Blue (текущий) и Green (новый). Трафик переключается целиком и мгновенно.

```
Load Balancer → [v1: b1] [v1: b2] [v1: b3]  (Blue — активный)
                [v2: b1] [v2: b2] [v2: b3]  (Green — прогревается)

  switch router
  
Load Balancer → [v2: b1] [v2: b2] [v2: b3]  (Green — активный)
                [v1: b1] [v1: b2] [v1: b3]  (Blue — standby, откат за секунды)
```

Rollback = переключить router обратно. Это одна команда.

Недостаток: нужны двойные ресурсы. И вопрос с миграциями БД: если v2 изменил схему — v1 может не работать с ней.

На Kubernetes реализуется через два Deployment + переключение selector у Service. Практика — на Уровне 5.

---

### Стратегия 4 — Canary

Выкатываем новую версию на малый процент трафика. Мониторим метрики. Постепенно увеличиваем.

```
[v1:b1] [v1:b2] [v1:b3] [v1:b4]  ← 80%, stable
[v2:canary]                        ← 20%, canary

  → метрики ok → graduate
[v1:b1] [v1:b2]                    ← 50%
[v2:b1] [v2:b2]                    ← 50%

  → метрики ok → финиш
[v2:b1] [v2:b2] [v2:b3] [v2:b4]  ← 100%
```

Rollback = удалить canary. Страдает малая часть пользователей, не все.

Canary — от "канарейка в угольной шахте": шахтёры брали канарейку чтобы понять безопасен ли воздух, прежде чем самим идти. Если канарейке плохо — возвращаются. Риск на канарейке, не на всех.

На Kubernetes реализуется через два Deployment + common Service. Практика — на Уровне 5.

---

### Бонус — Feature Flags (деплой без деплоя)

Пятая стратегия — скрыть фичу за флагом (`ENABLE_NEW_FEATURE=false`). Деплоишь код — фича выключена. Включаешь флаг когда готов — без деплоя, мгновенно, откатываешь одной переменной.

Инструменты: LaunchDarkly, Unleash (open-source), или простой Redis-ключ. На курсе не практикуем, но это зрелый подход в крупных компаниях.

---

### Практика — почувствовать разницу на себе

**Эксперимент: поменяй Rolling на Recreate**

В файле деплоя (или вручную на сервере) замени rolling update:

```bash
# БЫЛО (rolling):
for instance in backend_1 backend_2 backend_3; do
  docker compose pull $instance
  docker compose up -d --no-deps $instance
  sleep 5
done

# СТАЛО (recreate):
docker compose down
docker compose up -d
```

Запусти нагрузочный тест и затригери деплой одновременно:

```bash
# Терминал 1: нагрузка
k6 run level-2-scaling/load-tests/balancer-test.js

# Терминал 2: симулировать деплой
ssh your-server "cd ~/devops-project/level-3-caching && docker compose down && sleep 3 && docker compose up -d"
```

**Что увидишь в k6:**
```
✗ http_req_failed ......: 100.00% ← все запросы падают ~10-30 секунд
✓ http_req_failed ......: 0.00%   ← после восстановления
```

Запиши время даунтайма — от `Stopping` первого контейнера до `Started` последнего. Потом сравни с rolling update: в rolling `http_req_failed` почти не появляется.

**Верни rolling update** после эксперимента.

---

### На собеседовании про deployment strategies

**Q: Когда Blue-Green лучше Rolling?**
A: Когда важен быстрый rollback за секунды (не за минуты). Blue-Green: переключить selector — один запрос. Rolling rollback = новый деплой той же длины. Платишь двойными ресурсами.

**Q: Почему при Rolling update важна обратная совместимость API?**
A: В момент деплоя параллельно работают v1 и v2. Запрос может попасть на любой. Если v2 переименовал поле `title` в `name` — клиент с кешем от v1 не разберёт ответ от v2. Решение: Expand-Contract — сначала поддержать оба поля, потом убрать старое.

**Q: Что такое canary deployment и зачем он нужен?**
A: Выкатить новую версию на малый процент (5-20%) трафика, мониторить метрики, постепенно увеличивать. Если что-то не так — rollback затрагивает меньшинство пользователей. Особенно ценно для изменений с неизвестным риском: новый алгоритм, переписанный модуль, изменение производительности под нагрузкой.

---

## Шаг 7 — Версионирование образов

Каждый деплой создаёт образ с тегом = git commit SHA:

```bash
# На ghcr.io ты увидишь образы с тегами:
# ghcr.io/username/bulletin-board:a1b2c3d   ← конкретный коммит
# ghcr.io/username/bulletin-board:latest    ← последний

# Откатить на конкретную версию:
ssh server "docker pull ghcr.io/username/bulletin-board:a1b2c3d && docker compose up -d"
```

**Почему SHA, а не `latest`?**
`latest` — это просто тег, он перезаписывается при каждом деплое. Если деплой сломался и нужно откатиться — ты знаешь точно **какой коммит** работает.

---

## Шаг 8 — Тесты (что тестируем)

```bash
cat level-4-cicd/tests/test_api.py
```

Тесты покрывают:
- Регистрация и логин → получение JWT токена
- Создание объявления с токеном → 201
- Попытка создать без токена → 401
- Удаление своего объявления → 204
- Попытка удалить чужое → 403

**Зачем моки?**
Тесты в CI не должны зависеть от внешних сервисов (PostgreSQL, Redis). Моки заменяют их быстрыми in-memory реализациями. Тесты запускаются за секунды, а не минуты.

---

## Шаг 8.5 — Zero-downtime миграции базы данных

CI/CD автоматизирует деплой кода. Но есть часть деплоя которую часто делают неправильно: **миграции схемы базы данных**.

Вот типичная ситуация: добавляешь обязательное поле `image_url` к таблице `ads`. Пишешь миграцию:

```python
# Alembic migration
op.add_column('ads', sa.Column('image_url', sa.String(500), nullable=False, server_default=''))
```

На базе с 50 строками — мгновенно. На базе с **10 миллионами строк** — PostgreSQL заблокирует таблицу `ads` на несколько минут пока переписывает каждую строку. Всё это время `GET /api/ads` возвращает 500. Сервис лежит.

Это называется **blocking migration** — и это одна из самых частых причин инцидентов при деплое.

### Как это работает

PostgreSQL использует блокировки при изменении схемы таблицы:

```
ALTER TABLE ads ADD COLUMN image_url VARCHAR NOT NULL DEFAULT ''
    ↓
ACCESS EXCLUSIVE LOCK на таблицу ads
    ↓
PostgreSQL переписывает каждую строку (в PG10 и ниже)
    ↓
Все SELECT и INSERT ждут
    ↓
Таблица разблокируется
```

В PostgreSQL 11+ `ADD COLUMN NOT NULL DEFAULT constant` оптимизировали — стало мгновенным. Но другие операции до сих пор блокируют:

| Операция | Блокирует? | Безопасная альтернатива |
|----------|-----------|------------------------|
| `ADD COLUMN NULL` | Нет | — |
| `ADD COLUMN NOT NULL DEFAULT` | Нет (PG11+) / Да (PG10-) | Expand-Contract |
| `CREATE INDEX` | Да | `CREATE INDEX CONCURRENTLY` |
| `ALTER COLUMN TYPE` | Да | Expand-Contract |
| `ADD CONSTRAINT CHECK` | Да | `ADD CONSTRAINT NOT VALID` → `VALIDATE` |
| `DROP COLUMN` | Нет | — |

### Паттерн: Expand → Backfill → Contract

Любую опасную миграцию разбивают на несколько безопасных шагов — каждый деплоится отдельно:

```
Деплой 1 (Expand):
  ADD COLUMN image_url VARCHAR NULL     ← без NOT NULL, без DEFAULT, мгновенно

Деплой 1 (Backfill — можно в том же деплое или отдельный job):
  UPDATE ads SET image_url = '' WHERE image_url IS NULL  ← батчами, не блокируем

Деплой 2 (Contract):
  ALTER COLUMN image_url SET NOT NULL  ← уже безопасно: null строк нет
```

Аналогия: не перекрываешь единственную дорогу пока строишь новую. Сначала строишь рядом → открываешь → закрываешь старую.

### Практика

**Шаг 1 — Увидеть блокировку**

```bash
cd level-4-cicd
docker compose up -d

# Терминал 1: следим за блокировками во время миграции
watch -n 0.5 'docker compose exec postgres psql -U postgres -d bulletin_board -t -c "
SELECT pid, state, wait_event_type, wait_event, left(query, 60)
FROM pg_stat_activity WHERE state != '"'"'idle'"'"' ORDER BY query_start;"'

# Терминал 2: запускаем опасную миграцию
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  ALTER TABLE ads ADD COLUMN image_url VARCHAR(500) NOT NULL DEFAULT '';
"
```

На маленькой базе не почувствуешь разницы. Смысл — понять **механизм**: блокировка существует, на большой базе она длится минуты.

**Шаг 2 — Безопасная миграция по шагам**

```bash
# ШАГ 1 (Expand): добавляем nullable — мгновенно, без блокировки
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  ALTER TABLE ads ADD COLUMN image_url_v2 VARCHAR(500) NULL;
"
# На 10M строк — <1ms

# ШАГ 2 (Backfill): заполняем данные батчами
# В production делают по 1000 строк с паузами чтобы не перегружать репликацию
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  UPDATE ads SET image_url_v2 = '' WHERE image_url_v2 IS NULL;
"

# Проверяем что нет NULL:
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  SELECT count(*) FROM ads WHERE image_url_v2 IS NULL;
"
# count: 0  ← можно переходить к Contract

# ШАГ 3 (Contract): теперь безопасно установить NOT NULL
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  ALTER TABLE ads ALTER COLUMN image_url_v2 SET NOT NULL;
"
# На 10M строк — <1ms (не переписывает строки, только меняет метаданные)

# Проверяем результат:
docker compose exec postgres psql -U postgres -d bulletin_board -c "\d ads"
```

**Шаг 3 — Безопасное создание индексов**

Создание индекса — ещё одна опасная операция. Обычный `CREATE INDEX` блокирует таблицу на время сборки. `CREATE INDEX CONCURRENTLY` — строит индекс без блокировки, таблица доступна для чтения и записи:

```bash
# ОПАСНО — блокирует таблицу:
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  CREATE INDEX idx_ads_price ON ads(price);
"

# БЕЗОПАСНО — без блокировки:
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  CREATE INDEX CONCURRENTLY idx_ads_price_safe ON ads(price);
"

# В Alembic:
# op.create_index('idx_ads_price', 'ads', ['price'], postgresql_concurrently=True)
```

Минус `CONCURRENTLY`: нельзя запускать внутри транзакции. В Alembic нужно:
```python
with op.get_context().autocommit_block():
    op.create_index('idx_ads_price', 'ads', ['price'], postgresql_concurrently=True)
```

**Шаг 4 — Добавить в Alembic**

В реальных проектах Expand-Contract — это три отдельные миграции с осознанным деплоем:

```python
# migrations/002_add_image_url_expand.py — деплой 1
def upgrade():
    # Только nullable: мгновенно, безопасно
    op.add_column('ads', sa.Column('image_url', sa.String(500), nullable=True))

def downgrade():
    op.drop_column('ads', 'image_url')
```

```python
# migrations/003_backfill_image_url.py — деплой 1 (или data migration job)
def upgrade():
    # Заполняем DEFAULT для существующих строк
    op.execute("UPDATE ads SET image_url = '' WHERE image_url IS NULL")

def downgrade():
    pass  # данные нельзя "откатить"
```

```python
# migrations/004_add_image_url_not_null.py — деплой 2 (после backfill)
def upgrade():
    # Теперь безопасно — нет NULL строк
    op.alter_column('ads', 'image_url', nullable=False)

def downgrade():
    op.alter_column('ads', 'image_url', nullable=True)
```

**Ключевые вопросы перед каждой миграцией:**
1. Блокирует ли эта операция таблицу?
2. Сколько строк затронет? (10M строк = проблема)
3. Можно ли разбить на безопасные шаги?
4. Есть ли бэкап перед деплоем?

---

## Типичные ошибки

**"SSH: Permission denied"** → Проверь что `~/.ssh/deploy_key.pub` добавлен в `~/.ssh/authorized_keys` на сервере. Права: `chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys`.

**"Workflow не запускается"** → Проверь ветку. Workflow настроен на `push: branches: [main]`. Если ты пушишь в другую ветку — он не запустится (или запустится без deploy).

**"ghcr.io push: denied"** → Нужен PAT (Personal Access Token) с правом `write:packages`. GitHub → Settings → Developer settings → PAT. Добавь как Secret `GHCR_TOKEN`.

**Rolling update — появляются ошибки 502** → Nginx пытается слать на контейнер который уже остановлен. Добавь `proxy_connect_timeout 2s; proxy_next_upstream error timeout;` в nginx.conf — он автоматически переключится на рабочий инстанс.

---

## На собеседовании спросят

**Q: Что такое CI/CD и в чём разница между CI и CD?**
A: CI (Continuous Integration) — автоматический запуск тестов и сборки при каждом коммите. CD (Continuous Delivery) — автоматический деплой на сервер после прохождения CI. Цель: сократить цикл обратной связи от "написал код" до "код работает в prod".

**Q: Что такое rolling update и чем он отличается от recreate?**
A: Recreate: остановить все → запустить все → даунтайм. Rolling update: обновляем по одному инстансу, остальные продолжают работать — нулевой даунтайм. Минус rolling: в процессе деплоя в prod одновременно работают два разных версии кода.

**Q: Почему теги образов должны быть уникальными (commit SHA), а не `latest`?**
A: `latest` перезаписывается каждый раз. Если нужен rollback — с `latest` нельзя точно знать что было задеплоено раньше. Commit SHA уникален и неизменен, поэтому откат = `docker pull image:old-sha && docker compose up`.

**Q: Как хранить секреты в CI/CD?**
A: Никогда не в коде. GitHub Actions: Settings → Secrets. GitLab: Settings → CI/CD → Variables (Masked). Terraform: переменные окружения `TF_VAR_*` или Vault. Секреты никогда не попадают в логи.

**Q: Что такое артефакт в CI/CD?**
A: Файл созданный в одном job и переданный в следующий. Например: test coverage report, собранный Docker image, jar-файл. В GitHub Actions — `actions/upload-artifact` и `download-artifact`.

**Q: Что такое CVE и зачем сканировать Docker-образы?**
A: CVE (Common Vulnerabilities and Exposures) — база данных известных уязвимостей с оценкой CVSS 0-10. Docker-образ содержит базовый образ и зависимости — в любом из них может быть дыра. Trivy сканирует образ и сравнивает с CVE-базой. Деплой образа с CRITICAL уязвимостью без ведома — это риск который можно автоматически исключить одним шагом в CI.

**Q: Что такое blocking migration и как её избежать?**
A: Blocking migration — операция ALTER TABLE которая берёт ACCESS EXCLUSIVE LOCK и блокирует все запросы к таблице. На большой таблице это может длиться минуты. Решение: паттерн Expand-Contract: 1) ADD COLUMN NULL (мгновенно), 2) backfill данных батчами, 3) SET NOT NULL (мгновенно). Для индексов — `CREATE INDEX CONCURRENTLY`.

**Q: Почему `CREATE INDEX CONCURRENTLY` лучше `CREATE INDEX` в production?**
A: `CREATE INDEX` берёт блокировку на таблицу — все INSERT/UPDATE ждут пока строится индекс (минуты на большой таблице). `CREATE INDEX CONCURRENTLY` строит индекс в несколько проходов без блокировки — таблица доступна всё время. Минус: нельзя запускать в транзакции и строится вдвое медленнее.

---

## Итог уровня 4 — что ты умеешь

- [ ] Написать GitHub Actions workflow с зависимыми jobs
- [ ] Настроить SSH-деплой через GitHub Secrets
- [ ] Использовать ghcr.io для хранения Docker образов
- [ ] Реализовать rolling update без даунтайма
- [ ] Намеренно сломать и убедиться что CI останавливает деплой
- [ ] Понять разницу между `recreate` и `rolling` стратегиями

**Боль уровня 4:** Docker Compose + SSH — это не то что масштабируется. Нет автоматического перезапуска упавших контейнеров, нет управления ресурсами, нет self-healing → Уровень 5: Kubernetes.

---

## Коммит

```bash
git add level-4-cicd/
git commit -m "level-4: ci/cd with github actions and rolling update"
git push origin main
```

---

## Security Block: Уровень 4

### Секреты в CI/CD — главная боль

**1. GitHub Secrets — единственный правильный способ**

GitHub Actions имеет доступ к переменным через `${{ secrets.NAME }}`. Secrets зашифрованы, не видны в логах (заменяются на `***`), не видны другим пользователям репозитория.

Никогда не делай так:
```yaml
# ПЛОХО — пароль виден в коде и логах:
- run: ssh root@1.2.3.4 -p "mypassword123" "docker compose up -d"
```

**2. Принцип минимальных привилегий для deploy key**

Deploy key — отдельный SSH-ключ только для деплоя. Причина: если скомпрометируют pipeline, атакующий получает только deploy key. Отзываешь его — доступ потерян. Основной ключ остаётся нетронутым.

Deploy-пользователь на сервере должен иметь минимальные права:
- Доступ к папке проекта
- Права запускать `docker` команды
- НЕ нужен `sudo` для деплоя (организуй через группу docker)

**3. Образы с тегами commit SHA — аудит деплоев**

`ghcr.io/user/app:a1b2c3d` позволяет точно знать что сейчас запущено в production. `latest` — не позволяет. При инциденте вопрос "какая версия кода работала в 14:32?" решается за секунду.

**4. Проверь что в образ не попали секреты**

`.dockerignore` должен исключать `.env`, `*.key`, `credentials.*`. Иначе они попадут в слой образа который загружается в публичный registry.

```bash
# Проверить что .env не в образе:
docker run --rm ghcr.io/user/bulletin-board:latest ls -la /app | grep env
# Не должно быть .env файла
```

**5. Сканирование образов на уязвимости**

В реальных командах CI включает сканирование Docker-образа перед деплоем:

```yaml
# Добавить в pipeline (Trivy — популярный инструмент):
- name: Scan image
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ghcr.io/${{ github.actor }}/bulletin-board:${{ github.sha }}
    severity: 'HIGH,CRITICAL'
    exit-code: '1'  # упасть при критических уязвимостях
```

⚠️ **Антипаттерны:**

- **Секреты в `env:` в yaml-файле workflow** — даже если файл приватный, при merge fork-а PR атакующий может попытаться прочитать переменные через специально созданные шаги. Всегда используй `secrets.`.
- **Деплоить от root по SSH** — `ssh root@server "docker compose up"`. Если pipeline скомпрометирован — атакующий получает root на сервере. Используй непривилегированного пользователя в группе `docker`.

---

## Best Practices Checklist

- [ ] Все секреты (SSH ключ, пароли, токены) хранятся в GitHub Secrets, не в yaml
- [ ] Deploy key — отдельный ключ, не основной
- [ ] Pipeline не деплоит при провале тестов — проверено намеренной поломкой
- [ ] Образы тегируются commit SHA, не только `latest`
- [ ] `.dockerignore` исключает `.env` и секретные файлы
- [ ] Rolling update — нулевой даунтайм подтверждён нагрузочным тестом
- [ ] SSH-доступ для деплоя — от непривилегированного пользователя, не root
- [ ] Trivy scan добавлен в pipeline — CI останавливается при CRITICAL уязвимостях
- [ ] Понимаешь разницу между blocking и non-blocking миграцией — можешь объяснить паттерн Expand-Contract

---

## Troubleshooting: Уровень 4

### Проблемы с CI/CD pipeline

**1. SSH деплой не работает: `Permission denied (publickey)`**

Симптом: job `deploy` падает с ошибкой SSH.

```bash
# На сервере проверяем authorized_keys:
cat ~/.ssh/authorized_keys
# Там должен быть deploy_key.pub

# Проверяем права:
ls -la ~/.ssh/
# .ssh должно быть 700, authorized_keys — 600

# Проверяем что sshd принимает ключи:
sudo grep -E "PubkeyAuthentication|AuthorizedKeysFile" /etc/ssh/sshd_config

# Ручная проверка подключения с локальной машины тем же ключом:
ssh -i ~/.ssh/deploy_key devops@<IP> -v 2>&1 | tail -20
# Смотри строки "Offering public key" и "Accepted"
```

**2. Workflow не запускается после push**

Симптом: пушишь, во вкладке Actions ничего нового.

```bash
# Проверяем триггеры в deploy.yml:
grep -A 5 "^on:" .github/workflows/deploy.yml
# on: push: branches: [main]

# Может пушишь в другую ветку:
git branch
# * feature/something   ← не main, workflow не сработает

# Проверь что файл workflow в правильном месте:
ls .github/workflows/
```

**3. Docker push в ghcr.io: `denied: permission_denied`**

Симптом: job `build` падает при `docker push`.

```bash
# В GitHub Actions нужен GITHUB_TOKEN или PAT с правом write:packages
# Проверяем в deploy.yml:
grep -A 3 "ghcr.io" .github/workflows/deploy.yml
# Должно быть: echo ${{ secrets.GITHUB_TOKEN }} | docker login ghcr.io -u ...

# GITHUB_TOKEN автоматически доступен в Actions без настройки
# Но нужно разрешить пакеты в настройках репо:
# Settings → Actions → General → Workflow permissions → Read and write
```

**4. Rolling update вызывает всплеск 502**

Симптом: во время деплоя k6 показывает ошибки.

```bash
# На сервере смотрим nginx логи в момент деплоя:
docker compose logs nginx | grep -E "502|upstream|connect"

# Причина: nginx не успел узнать что инстанс остановлен
# Решение в nginx.conf:
cat nginx/nginx.conf | grep -A 5 "proxy_next_upstream"
# Должно быть: proxy_next_upstream error timeout;
# И: proxy_connect_timeout 2s;

# Проверить что healthcheck настроен в docker-compose.yml:
grep -A 5 "healthcheck" docker-compose.yml
```

**5. Тесты падают в CI но работают локально**

Симптом: `pytest` в GitHub Actions падает, у тебя локально проходит.

```bash
# Запусти тесты в той же среде что CI (чистый Ubuntu-контейнер):
docker run --rm -v $(pwd):/app -w /app python:3.11-slim bash -c \
  "pip install -r level-4-cicd/backend/requirements.txt && pytest level-4-cicd/tests/"

# Частые причины:
# 1. Разные версии Python (проверь в deploy.yml: python-version)
# 2. Переменные окружения не установлены (в CI нет .env файла)
# 3. Зависимость от внешнего сервиса без мока (PostgreSQL не поднят в CI)

# Смотрим полный вывод CI в логах Actions:
# Вкладка Actions → конкретный запуск → job test → шаг Run tests
```
