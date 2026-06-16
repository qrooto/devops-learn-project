# Уровень 4 — CI/CD с GitHub Actions

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
