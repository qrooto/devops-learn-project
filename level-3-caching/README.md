# Уровень 3 — Кэширование с Redis

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

## Шаг 8 — Остановить

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
