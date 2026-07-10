# Уровень 3 — Кэширование с Redis

> **Тип сессии:** разделы «Зачем», «Аналогия», «Как это работает», «На собеседовании спросят», Security Block — **[голова]**: можно читать в дороге, без терминала. Шаги с командами, «Что сломать намеренно», Troubleshooting на живой поломке — **[руки]**: нужна домашняя сессия с VM. Легенда — в START_HERE.md.

## Зачем начинать отсюда?

На уровне 2 три бэкенда хорошо делят нагрузку между собой. Но PostgreSQL один — при 100 RPS это 100 запросов в секунду к базе. Каждый `GET /api/ads` делает `JOIN` + `ORDER BY` + перебирает всю таблицу. При росте числа объявлений — время ответа деградирует несмотря на горизонтальное масштабирование бэкенда.

Решение: большинство запросов читают **одинаковые данные**. Зачем каждый раз идти в БД если список объявлений не менялся последние 30 секунд?

## Аналогия

У нас есть справочная (PostgreSQL) — туда за каждым ответом ходить долго. Но у нас есть доска объявлений у входа (Redis) — туда кто-то переписывает самую популярную информацию каждые 30 минут. 99% посетителей получают ответ у доски мгновенно. Только при изменении данных — обновляем доску.

## Архитектура

```
Браузер
    │
    └── Nginx → upstream backend (3 инстанса)
                        │
                        ├── GET /api/ads
                        │       │
                        │       ├── Cache HIT  ─→ Redis (~0.1ms) ──→ ответ
                        │       └── Cache MISS ─→ PostgreSQL (~5-10ms)
                        │                               └── сохранить в Redis (TTL 30s)
                        │
                        └── POST/DELETE /api/ads
                                └── изменить в PostgreSQL → удалить ключ из Redis
```

**Ключевые понятия:**
- **Cache HIT** — данные найдены в Redis, PostgreSQL не трогаем
- **Cache MISS** — в Redis пусто, идём в PostgreSQL, результат кладём в кэш
- **Cache invalidation** — при изменении данных удаляем ключ из Redis. Следующий запрос — Cache MISS и получит свежие данные.
- **TTL (Time To Live)** — время жизни записи в кэше. У нас 30 секунд.

**Почему Redis, а не просто память бэкенда?**
Три инстанса бэкенда. Если каждый хранит кэш в своей памяти — они несинхронизированы: backend_1 инвалидировал кэш, а backend_2 и backend_3 всё ещё отдают устаревшее. Redis — единое внешнее хранилище, один кэш для всех инстансов.

---

## Шаг 1 — Понять изменения в коде

```bash
cat backend/main.py
```

**Найди функцию `list_ads()` и разбери её логику:**
```python
def list_ads():
    cached = cache.get("ads:list")      # проверяем Redis
    if cached:
        return json.loads(cached)        # Cache HIT — возвращаем без БД

    # Cache MISS — идём в PostgreSQL
    rows = engine.connect().execute(...)
    result = [...]
    cache.setex("ads:list", CACHE_TTL, json.dumps(result))  # сохраняем на 30с
    return result
```

**Найди `create_ad()` и `delete_ad()`:**
```python
cache.delete("ads:list")  # инвалидация — старые данные больше не актуальны
```

**Задание:** Что произойдёт если убрать инвалидацию из `create_ad()`? Как долго новое объявление будет невидимо?

---

## Шаг 2 — Запустить

```bash
cd level-3-caching
docker compose up --build -d
docker compose ps
```

**Что должны увидеть:** 6 контейнеров — nginx, postgres, redis, backend_1, backend_2, backend_3.

Проверь что Redis доступен:
```bash
docker compose exec redis redis-cli ping
# PONG
```

---

## Шаг 3 — Наблюдать кэш в действии

```bash
# Терминал 1: следим за Redis
docker compose exec redis redis-cli monitor
# Будет показывать все команды к Redis в реальном времени

# Терминал 2: делаем запросы
curl -s http://localhost/api/ads > /dev/null  # Cache MISS — увидишь GET ads:list в monitor
curl -s http://localhost/api/ads > /dev/null  # Cache HIT — снова GET, но быстро
curl -s http://localhost/api/ads > /dev/null  # Cache HIT
```

В Терминале 1 увидишь разницу:
- При MISS: `GET "ads:list"` → ответ `nil` → потом `SETEX "ads:list" 30 "..."`
- При HIT: `GET "ads:list"` → ответ с данными (без SETEX)

---

## Шаг 4 — Зайти в Redis напрямую

```bash
docker compose exec redis redis-cli
```

```
# Все ключи в Redis:
KEYS *
# 1) "ads:list"

# Посмотреть содержимое:
GET ads:list
# "[{\"id\": 1, \"title\": \"...

# Сколько секунд осталось жить ключу:
TTL ads:list
# (integer) 27

# Статистика кэша:
INFO stats
# keyspace_hits:5
# keyspace_misses:1

# Принудительно удалить кэш (симуляция инвалидации):
DEL ads:list

# Выйти:
quit
```

**Задание:** Создай объявление через curl с JWT, потом сразу проверь `KEYS *` в redis-cli. Ключ `ads:list` должен исчезнуть — его удалила инвалидация.

---

## Шаг 5 — Замерить разницу в скорости

**Тест 1 — с прогретым кэшем:**
```bash
# Сначала прогреем кэш одним запросом:
curl -s http://localhost/api/ads > /dev/null

# Нагрузочный тест:
k6 run load-tests/cache-test.js
```
Запиши `http_req_duration` (p95).

**Сброс кэша:**
```bash
docker compose exec redis redis-cli FLUSHALL
```

**Тест 2 — холодный кэш (каждый запрос идёт в PostgreSQL):**
```bash
k6 run load-tests/cache-test.js
```

**Что увидишь:** p95 при прогретом кэше — в 5-20 раз меньше. При 50 VU без кэша — PostgreSQL начинает задыхаться (видно в `docker stats`).

```bash
# Смотри в реальном времени:
docker stats
# С кэшем: postgres CPU низкий, redis CPU заметный
# Без кэша: postgres CPU высокий
```

---

## Шаг 6 — Наблюдать cache-stats

```bash
# Открой в браузере или через curl:
curl -s http://localhost/api/cache-stats | python3 -m json.tool
```

```json
{
    "hits": 142,
    "misses": 7,
    "hit_rate_percent": 95.3,
    "cache_ttl_seconds": 30
}
```

**Хороший hit_rate** — 90%+. Это значит 90% запросов не трогают PostgreSQL.

---

## Шаг 7 — Медленные запросы и индексы в PostgreSQL

Включим логирование медленных запросов (замедлить порог до 0ms чтобы видеть все):

```bash
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  ALTER SYSTEM SET log_min_duration_statement = 0;
  SELECT pg_reload_conf();
"
```

Сбрось кэш и сделай несколько запросов:
```bash
docker compose exec redis redis-cli FLUSHALL
curl -s http://localhost/api/ads > /dev/null
curl -s http://localhost/api/ads > /dev/null
```

Посмотри логи PostgreSQL:
```bash
docker compose logs postgres | grep "duration"
# duration: 12.341 ms  statement: SELECT a.id, a.title...
```

Теперь проверь план выполнения запроса:
```bash
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  EXPLAIN ANALYZE
  SELECT a.id, a.title, a.description, a.price, u.username, a.created_at
  FROM ads a LEFT JOIN users u ON a.user_id = u.id
  ORDER BY a.created_at DESC;
"
```

**Что ищи в выводе:**
- `Index Scan using ix_ads_created_at` — хорошо, используется индекс
- `Seq Scan on ads` — плохо, перебирает всю таблицу. Нужен индекс!

У нас индексы уже созданы миграцией 001 (`ix_ads_created_at`, `ix_ads_user_id`). Сравни с тем что было бы без них — удали и посмотри:
```bash
docker compose exec postgres psql -U postgres -d bulletin_board -c "
  DROP INDEX ix_ads_created_at;
  EXPLAIN ANALYZE SELECT ... ORDER BY created_at DESC;
  -- теперь Seq Scan
  CREATE INDEX ix_ads_created_at ON ads(created_at);
"
```

---

## Шаг 8 — Backup & Recovery: защита данных

До сих пор мы оптимизировали как данные хранятся и читаются. Но есть вопрос который игнорируют пока не случится катастрофа: **что будет с данными если диск умрёт?**

`docker compose down -v` — и всё. Объявления, пользователи, история — исчезли. Если это production — это конец.

Единственная защита — регулярные бэкапы которые **проверены на восстановление**. Бэкап который не проверен — не бэкап.

### Аналогия

Бэкап — это ксерокопия важного документа. Сам документ может сгореть, но копия остаётся. При этом копию нужно хранить **не в том же здании** — иначе какой смысл. И хотя бы раз прочитать — убедиться что напечатано разборчиво.

### Анатомия pg_dump

`pg_dump` — утилита PostgreSQL которая экспортирует базу данных в файл. Можно перенести базу на другой сервер, откатиться к точке во времени, или просто иметь резервную копию.

**Форматы:**

| Формат | Флаг | Восстановление | Когда использовать |
|--------|------|---------------|-------------------|
| Plain SQL | `--format=plain` | `psql` | Читаемый файл, понять что внутри |
| Custom (бинарный) | `--format=custom` | `pg_restore` | **Рекомендуемый**: сжат, выборочное восстановление |
| Directory | `--format=directory` | `pg_restore` | Параллельный дамп огромных баз |

**Ключевые флаги:**
```bash
--compress=9    # максимальное сжатие (1-9)
--no-owner      # не включать SET ROLE (нужно если пользователи разные в target)
--clean         # добавить DROP TABLE перед CREATE (для перезаписи существующей схемы)
--if-exists     # DROP TABLE IF EXISTS (безопаснее чем без него)
```

### Практика

**Шаг 1 — Подготовить данные**

```bash
cd level-3-caching
docker compose up -d

# Создаём тестовые данные:
curl -s -X POST http://localhost/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123","email":"alice@test.com"}' > /dev/null

TOKEN=$(curl -s -X POST http://localhost/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"secret123"}' | \
  python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

for i in 1 2 3; do
  curl -s -X POST http://localhost/api/ads \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $TOKEN" \
    -d "{\"title\":\"Объявление $i\",\"description\":\"Важные данные\",\"price\":$((i*1000))}" > /dev/null
done

curl -s http://localhost/api/ads | python3 -m json.tool
# Видим 3 объявления — это то что нужно сохранить
```

**Шаг 2 — Создать бэкап**

```bash
# Создаём директорию для бэкапов:
mkdir -p ~/backups/postgres

# pg_dump внутри контейнера, результат выводим наружу через stdout:
docker compose exec postgres pg_dump \
  -U postgres \
  --format=custom \
  --compress=9 \
  bulletin_board > ~/backups/postgres/backup_$(date +%Y%m%d_%H%M%S).dump

# Проверяем файл:
ls -lh ~/backups/postgres/
# -rw-r--r-- 1 user user 4.2K Jun 23 15:30 backup_20260623_153045.dump

# Список объектов в бэкапе (без восстановления):
pg_restore --list ~/backups/postgres/backup_*.dump
# если pg_restore не установлен локально:
docker compose exec postgres pg_restore --list /dev/stdin < ~/backups/postgres/backup_*.dump
```

**Шаг 3 — Тест восстановления (главное правило)**

```bash
# Создаём отдельную базу для проверки:
docker compose exec postgres psql -U postgres -c "CREATE DATABASE restore_test;"

# Восстанавливаем туда:
docker compose exec -T postgres pg_restore \
  -U postgres \
  --dbname=restore_test \
  --no-owner \
  < ~/backups/postgres/backup_*.dump

# Проверяем что данные на месте:
docker compose exec postgres psql -U postgres -d restore_test \
  -c "SELECT count(*) FROM ads;"
# count: 3  ← совпадает с оригиналом

docker compose exec postgres psql -U postgres -d restore_test \
  -c "SELECT title, price FROM ads ORDER BY id;"
# Объявление 1 | 1000
# Объявление 2 | 2000
# Объявление 3 | 3000

# Убираем тестовую базу:
docker compose exec postgres psql -U postgres -c "DROP DATABASE restore_test;"
```

**Что увидишь:** данные восстановились точно — объявления, пользователи, всё.

**Шаг 4 — Симулировать катастрофу и восстановление**

Это самый важный шаг. Нужно убедиться что восстановление работает в реальной ситуации — не только в теории.

```bash
# КАТАСТРОФА: удаляем данные как будто диск умер
docker compose down -v
# Данные в postgres_data volume — уничтожены

# Поднимаем заново — пустая база:
docker compose up -d

# Проверяем что данных нет:
sleep 15  # ждём пока postgres поднимется
curl -s http://localhost/api/ads
# []  ← пусто, всё потеряно

# ВОССТАНОВЛЕНИЕ:
docker compose exec -T postgres pg_restore \
  -U postgres \
  --dbname=bulletin_board \
  --no-owner \
  < ~/backups/postgres/backup_*.dump

# Данные вернулись:
curl -s http://localhost/api/ads | python3 -m json.tool
# Видим наши 3 объявления — восстановлено!
```

**Шаг 5 — Автоматизация: скрипт с ротацией**

Бэкап который нужно запускать руками — не бэкап. Нужна автоматизация:

```bash
# Создаём скрипт:
cat > ~/backup-postgres.sh << 'SCRIPT'
#!/bin/bash
set -e  # остановиться при любой ошибке

BACKUP_DIR="$HOME/backups/postgres"
COMPOSE_DIR="$HOME/devops-project/level-3-caching"
DATE=$(date +%Y%m%d_%H%M%S)
FILENAME="bulletin_board_${DATE}.dump"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"

echo "[$(date)] Starting backup..."

# Создаём бэкап
docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T postgres \
  pg_dump -U postgres --format=custom --compress=9 bulletin_board \
  > "${BACKUP_DIR}/${FILENAME}"

SIZE=$(du -sh "${BACKUP_DIR}/${FILENAME}" | cut -f1)
echo "[$(date)] Backup created: $FILENAME ($SIZE)"

# Удаляем старые бэкапы (старше KEEP_DAYS дней)
DELETED=$(find "$BACKUP_DIR" -name "*.dump" -mtime +${KEEP_DAYS} -delete -print | wc -l)
echo "[$(date)] Deleted $DELETED old backups"

echo "[$(date)] Done. Total backups: $(ls $BACKUP_DIR/*.dump | wc -l)"
SCRIPT

chmod +x ~/backup-postgres.sh

# Проверяем что скрипт работает:
~/backup-postgres.sh
# [2026-06-23 15:30:00] Starting backup...
# [2026-06-23 15:30:01] Backup created: bulletin_board_20260623_153001.dump (4.2K)
# [2026-06-23 15:30:01] Deleted 0 old backups
# [2026-06-23 15:30:01] Done. Total backups: 2

# Добавить в cron (бэкап каждую ночь в 3:00):
# crontab -e
# 0 3 * * * /home/ubuntu/backup-postgres.sh >> /var/log/backup.log 2>&1
```

**Шаг 6 — Что такое PITR и когда нужен**

`pg_dump` — логический бэкап: снимок в момент времени. Если делаешь бэкап раз в сутки и база упала в 23:59 — потерял почти сутки данных.

**PITR (Point-in-Time Recovery)** — позволяет восстановить базу на любой момент времени. PostgreSQL ведёт WAL (Write-Ahead Log) — лог всех изменений. Базовый бэкап + WAL-файлы = восстановление на любую секунду.

```
pg_basebackup (базовый снимок)  +  WAL-архив (все изменения после снимка)
                                            ↓
              pg_restore на любой момент времени
              "хочу базу как вчера в 14:32:47"
```

PITR используется когда:
- Данные меняются часто и потеря даже часа критична
- Нужно восстановить "до момента когда кто-то случайно удалил таблицу"
- SLA требует RPO < 1 час (Recovery Point Objective)

Для учебного проекта `pg_dump` достаточен. В production с критичными данными — PITR обязателен.

---

### Что сломать намеренно

**Поломка — восстановить поверх существующей базы**

```bash
# Попробуй восстановить в непустую базу без --clean:
docker compose exec -T postgres pg_restore \
  -U postgres \
  --dbname=bulletin_board \
  --no-owner \
  < ~/backups/postgres/backup_*.dump

# Увидишь ошибки:
# pg_restore: error: could not execute query: ERROR: relation "users" already exists
# pg_restore: error: could not execute query: ERROR: relation "ads" already exists

# Это не катастрофа — pg_restore продолжает несмотря на ошибки
# Данные при этом могут задвоиться или не восстановиться

# Правильный способ — с флагом --clean:
docker compose exec -T postgres pg_restore \
  -U postgres \
  --dbname=bulletin_board \
  --no-owner \
  --clean \
  --if-exists \
  < ~/backups/postgres/backup_*.dump
# Сначала DROP TABLE IF EXISTS, потом CREATE TABLE, потом INSERT
```

**Диагностика:** `pg_restore` возвращает exit code 1 при ошибках даже если большинство данных восстановилось. В скриптах: проверяй exit code И верификационный запрос (`SELECT count(*) FROM ads`).

---

## Шаг 9 — Остановить

```bash
docker compose down
docker compose down -v  # с удалением данных
```

---

## Типичные ошибки

**"Connection refused" к Redis** → Redis ещё не запустился. Проверь `docker compose logs redis`.

**Кэш не инвалидируется** → Убедись что в `create_ad()` и `delete_ad()` вызывается `cache.delete("ads:list")`. Без этого данные будут устаревшими до истечения TTL.

**`FLUSHALL` в production** → Никогда. Это удаляет ВСЕ ключи из Redis. В prod используй `DEL` конкретных ключей. `FLUSHALL` только для разработки.

**Redis занимает слишком много памяти** → Настрой `maxmemory` и политику вытеснения (`maxmemory-policy allkeys-lru`). По умолчанию Redis будет расти пока есть RAM.

**"Cache poisoning"** → Если в кэш попали некорректные данные — они будут отдаваться всем до истечения TTL. Решение: правильная инвалидация + не доверять данным из кэша без валидации.

---

## На собеседовании спросят

**Q: Что такое cache invalidation и почему это одна из двух сложных проблем в CS?**
A: Инвалидация — удаление устаревших данных из кэша. Сложность: надо знать когда данные изменились. Наш подход (delete при write) прост, но при высокой конкурентности возникает "thundering herd" — сотни запросов одновременно уходят в БД после инвалидации.

**Q: Чем Redis отличается от Memcached?**
A: Redis: персистентность (RDB/AOF), структуры данных (hash, list, set, sorted set), pub/sub, Lua scripting, cluster. Memcached: проще, быстрее при простом key-value, нет персистентности. Для большинства задач Redis.

**Q: Что такое TTL и как выбрать правильное значение?**
A: Time To Live — время жизни ключа. Слишком маленькое: много Cache MISS, не даёт эффекта. Слишком большое: устаревшие данные. Выбор зависит от частоты изменений: для списка объявлений 30-60с нормально, для котировок акций — 1с.

**Q: Как работает LRU eviction в Redis?**
A: При `maxmemory-policy allkeys-lru` Redis при нехватке памяти удаляет давно неиспользуемые ключи (Least Recently Used). Это нормальное поведение кэша — горячие данные остаются, холодные вытесняются.

**Q: Что такое "thundering herd" при инвалидации кэша?**
A: Кэш для популярного ключа истёк одновременно. 1000 параллельных запросов увидели Cache MISS и все пошли в БД. База получила 1000 одинаковых запросов вместо одного. Решение: mutex lock на первый запрос, остальные ждут результата.

**Q: Чем `pg_dump` отличается от `pg_basebackup`?**
A: `pg_dump` — логический бэкап: SQL-дамп конкретной базы в момент времени. Можно восстановить в другую версию PostgreSQL, на другую схему. `pg_basebackup` — физическая копия всего кластера (все базы, WAL). Используется для PITR и настройки репликации. Для ежедневных бэкапов — `pg_dump`. Для disaster recovery с минимальным RPO — `pg_basebackup` + WAL-архивирование.

**Q: Что такое RPO и RTO, и как они связаны с бэкапами?**
A: RPO (Recovery Point Objective) — максимально допустимая потеря данных по времени. Бэкап раз в сутки → RPO = 24 часа (потеряешь до суток данных при катастрофе). RTO (Recovery Time Objective) — максимально допустимое время восстановления. Большой бэкап и медленный диск → высокий RTO. Эти метрики определяют требования к бэкап-стратегии.

---

## Итог уровня 3 — что ты умеешь

- [ ] Подключить Redis как внешний кэш
- [ ] Реализовать cache-aside pattern (check → miss → load → store)
- [ ] Инвалидировать кэш при изменении данных
- [ ] Читать статистику Redis (hits/misses/hit_rate)
- [ ] Использовать `redis-cli MONITOR` для наблюдения команд в реальном времени
- [ ] Объяснить зачем EXPLAIN ANALYZE и что такое Seq Scan vs Index Scan

**Боль уровня 3:** при обновлении образа бэкенда надо остановить все три инстанса — сервис недоступен. Нужен rolling update → Уровень 4 (CI/CD).

---

## Коммит

```bash
cd ..
git add level-3-caching/
git commit -m "level-3: redis caching with cache invalidation"
git push origin main
```

---

## Security Block: Уровень 3

### Redis — открытый по умолчанию

Redis спроектирован для использования в доверенной сети и по умолчанию не требует пароля. Это хорошо для разработки, но опасно в production.

**Почему Redis нужен пароль:**
Без пароля любой кто добрался до сети где живёт Redis может:
- Читать все закэшированные данные (потенциально чувствительные)
- Выполнить `FLUSHALL` и обнулить кэш
- В старых версиях Redis — выполнить произвольные команды на хосте через `CONFIG SET`

**Как добавить пароль Redis:**

```yaml
# docker-compose.yml:
redis:
  image: redis:7-alpine
  command: redis-server --requirepass ${REDIS_PASSWORD}
  environment:
    - REDIS_PASSWORD=${REDIS_PASSWORD}
```

```python
# backend/main.py:
cache = redis.Redis(host='redis', port=6379, password=os.getenv('REDIS_PASSWORD'))
```

```bash
# .env файл (не коммитить в git!):
REDIS_PASSWORD=your_strong_password_here
```

**Redis не должен быть доступен снаружи**

Как и PostgreSQL — Redis не должен иметь проброшенных портов. В нашем compose у Redis нет `ports:` — верно. Если когда-то добавишь для отладки — убери перед деплоем.

**`FLUSHALL` — только в разработке**

`FLUSHALL` удаляет все ключи из Redis. В production это означает потерю всего кэша одной командой — всплеск нагрузки на PostgreSQL. Используй только в dev. В production для очистки конкретного ключа: `DEL ads:list`.

**Ограничение памяти Redis**

Без `maxmemory` Redis будет расти пока не съест всю RAM сервера. В production обязательно:

```
# redis.conf или command:
maxmemory 256mb
maxmemory-policy allkeys-lru
```

`allkeys-lru` — при нехватке памяти удаляет давно неиспользуемые ключи. Это нормальное поведение кэша.

⚠️ **Антипаттерны:**

- **Redis без пароля в production** — при компрометации любого контейнера в той же сети атакующий получает полный доступ к кэшу (и к данным которые в нём хранятся).
- **`FLUSHALL` в скриптах деплоя** — некоторые добавляют его "для надёжности" при деплое. Это вызывает thundering herd: все запросы сразу идут в PostgreSQL.

---

## Best Practices Checklist

- [ ] Redis не имеет проброшенного порта на хост (`ss -tulpn | grep 6379` пуст)
- [ ] `FLUSHALL` вызывается только руками при разработке, не в скриптах
- [ ] `maxmemory` настроен хотя бы для понимания ограничений
- [ ] Инвалидация кэша работает — создал объявление, `KEYS *` в redis-cli показывает пустой список
- [ ] Hit rate выше 80% при нормальной нагрузке — `curl /api/cache-stats`
- [ ] Индексы в PostgreSQL созданы — `EXPLAIN ANALYZE` показывает `Index Scan`, не `Seq Scan`
- [ ] `log_min_duration_statement` возвращён в нормальное значение после отладки (0ms = логировать всё = замедляет базу)
- [ ] Бэкап создан и **протестирован** — не просто создан файл, а выполнено восстановление в `restore_test` с проверкой `SELECT count(*)`
- [ ] Скрипт ротации бэкапов написан — старые бэкапы удаляются автоматически
- [ ] Понимаешь разницу RPO/RTO и что значит бэкап раз в сутки для продакшена

---

## Troubleshooting: Уровень 3

### Проблемы с Redis и кэшированием

**1. Redis не отвечает / Connection refused**

Симптом: `docker compose exec redis redis-cli ping` возвращает ошибку или бэкенд падает с `ConnectionRefusedError`.

```bash
# Проверяем запущен ли Redis:
docker compose ps redis

# Смотрим логи Redis:
docker compose logs redis

# Проверяем ping изнутри бэкенда:
docker compose exec backend_1 python3 -c "import redis; r=redis.Redis(host='redis'); print(r.ping())"

# Если не запускается — проверяем что нет конфликта портов:
ss -tulpn | grep 6379
```

**2. Кэш не инвалидируется — старые данные после изменений**

Симптом: создал объявление, обновил страницу — нового объявления нет (или удалил — оно всё ещё видно).

```bash
# Следим за Redis командами в реальном времени:
docker compose exec redis redis-cli monitor

# В другом терминале делаем операцию (POST /api/ads):
# В monitor должен появиться DEL ads:list

# Если DEL не появляется — смотрим код create_ad():
docker compose exec backend_1 grep -A 5 "cache.delete" /app/main.py

# Принудительно сбросить кэш для диагностики:
docker compose exec redis redis-cli DEL ads:list
```

**3. Низкий hit rate (меньше 50%)**

Симптом: `curl /api/cache-stats` показывает `hit_rate_percent: 30`.

```bash
# Смотрим TTL — возможно слишком маленький:
docker compose exec redis redis-cli TTL ads:list
# Если 1-2 — кэш протухает раньше чем успевают прийти повторные запросы

# Статистика Redis:
docker compose exec redis redis-cli INFO stats | grep -E "hits|misses"
# keyspace_hits: сколько раз нашли ключ
# keyspace_misses: сколько раз не нашли

# Проверяем что кэш вообще пишется:
docker compose exec redis redis-cli KEYS '*'
# Если пусто при работающем приложении — SETEX не вызывается
```

**4. Redis занял слишком много памяти**

Симптом: `docker stats` показывает что redis контейнер потребляет несколько GB.

```bash
# Текущее использование памяти:
docker compose exec redis redis-cli INFO memory | grep -E "used_memory_human|maxmemory"

# Сколько ключей в Redis и какого типа:
docker compose exec redis redis-cli INFO keyspace
docker compose exec redis redis-cli DBSIZE

# Найти самые большие ключи:
docker compose exec redis redis-cli --bigkeys

# Установить лимит без перезапуска:
docker compose exec redis redis-cli CONFIG SET maxmemory 256mb
docker compose exec redis redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

**6. Бэкап упал / восстановление не работает**

Симптом: `pg_restore` выдаёт ошибки или данные не появились после восстановления.

```bash
# Смотреть полный вывод pg_restore с деталями ошибок:
docker compose exec -T postgres pg_restore \
  -U postgres \
  --dbname=bulletin_board \
  --no-owner \
  --verbose \
  < ~/backups/postgres/backup_*.dump 2>&1 | grep -E "ERROR|error|creating"

# Ошибка "relation already exists":
# Решение: добавь --clean --if-exists
# Это сначала удалит таблицы, потом создаст заново

# Ошибка "role does not exist":
# pg_dump сохранил имя владельца, на новом сервере его нет
# Решение: добавь --no-owner

# Проверить что бэкап не повреждён:
docker compose exec postgres pg_restore \
  --list /dev/stdin < ~/backups/postgres/backup_*.dump | head -20
# Если вывод есть — файл читается. Если ошибка — файл повреждён.

# Проверить что данные реально восстановились:
docker compose exec postgres psql -U postgres -d bulletin_board \
  -c "SELECT count(*) FROM ads; SELECT count(*) FROM users;"
# Если count = 0 после restore — что-то пошло не так
```

**5. PostgreSQL медленно работает несмотря на кэш**

Симптом: высокий CPU у postgres, медленные запросы даже при хорошем hit rate.

```bash
# Включаем логирование медленных запросов (>100ms):
docker compose exec postgres psql -U postgres -c "ALTER SYSTEM SET log_min_duration_statement = 100;"
docker compose exec postgres psql -U postgres -c "SELECT pg_reload_conf();"

# Смотрим какие запросы медленные:
docker compose logs postgres | grep "duration" | sort -t':' -k2 -rn | head -10

# Проверяем план конкретного запроса:
docker compose exec postgres psql -U postgres -d bulletin_board -c "
EXPLAIN (ANALYZE, BUFFERS) SELECT a.id, a.title, a.price, u.username
FROM ads a LEFT JOIN users u ON a.user_id = u.id
ORDER BY a.created_at DESC LIMIT 20;"
# Ищи: Index Scan (хорошо) vs Seq Scan (плохо, нужен индекс)

# Статистика использования индексов:
docker compose exec postgres psql -U postgres -d bulletin_board -c "
SELECT relname, idx_scan, seq_scan FROM pg_stat_user_tables ORDER BY seq_scan DESC;"
```

---

## Архитектура

- [Концепция: cache-aside в вакууме](../docs/architecture/level-3-caching/concept.html) — когда приложение читает из кэша, когда из БД, и почему это компромисс, а не бесплатный ускоритель
- [Реализация: реальный docker-compose.yml](../docs/architecture/level-3-caching/implementation.html) — общий redis:7-alpine для всех 3 backend, TTL 30s
- [Боль → решение: Level 2 → Level 3](../docs/architecture/level-3-caching/pain-solution.html) — было/стало/почему это работает и какой ценой

Сетевой диаграммы для этого уровня нет: у Redis нет published-порта, набор портов, видимых снаружи VPS, не изменился с Level 2 (см. [network Level 2](../docs/architecture/level-2-scaling/network.html)).

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
