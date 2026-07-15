# Уровень 4 (GitLab) — Self-hosted GitLab CE + GitLab CI/CD

> **Это [руки]** — практический маршрут уровня: команды, эксперименты, поломки. Нужна сессия с VM (минимум 4GB RAM).
> **Теория уровня — в `CURRICULUM.md` → «Уровень 4»**: зачем CI/CD, анатомия `.github/workflows/deploy.yml` и `.gitlab-ci.yml`, сравнение GitLab CI vs GitHub Actions, вопросы с собеседований. Здесь она не дублируется. Легенда `[голова]`/`[руки]` — в START_HERE.md.

## Требования к VM

GitLab требователен к ресурсам. **Минимум 4GB RAM**, рекомендуется 6GB.

```bash
free -h
# Нужно: available 3G+

# Если памяти мало — добавь swap:
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

---

## Шаг 1 — Запустить GitLab

```bash
cd level-4-gitlab
docker compose up -d

# Следим за запуском — займёт 3-5 минут первый раз
docker compose logs -f gitlab
```

**Что ждёшь в логах:**
```
gitlab    | ==> /var/log/gitlab/gitlab-rails/production.log <==
...
gitlab    | gitlab Reconfigured!
```

Это значит что Omnibus (встроенный менеджер GitLab) настроил все 20+ внутренних сервисов.

Проверь что все внутренние сервисы запущены:
```bash
docker compose exec gitlab gitlab-ctl status
```

Каждая строка должна быть `run`. Если что-то в `down` — подожди ещё минуту и повтори.

---

## Шаг 2 — Первый вход и базовая безопасность

Открой в браузере: `http://ВАШ-IP:8929`

**Получить пароль root:**
```bash
docker compose exec gitlab grep 'Password:' /etc/gitlab/initial_root_password
# Password: AbCdEfGh1234...
```

Этот файл удаляется автоматически через 24 часа — смени пароль сразу.

**Войди:** логин `root`, пароль из команды выше.

**Обязательные настройки безопасности:**
1. Смени пароль root: иконка пользователя (верхний правый угол) → **Edit Profile → Password**
2. Отключи публичную регистрацию: **Admin → Settings → General → Sign-up restrictions → отключи "Sign-up enabled"** → Save
3. Отключи публичный доступ: **Admin → Settings → General → Visibility and access controls → Default project visibility: Private**

---

## Шаг 3 — Создать проект в GitLab

1. Нажми **New project → Create blank project**
2. Project name: `devops-project`
3. Visibility level: **Private**
4. **Снять галочку** "Initialize repository with a README" — у нас уже есть репозиторий
5. Нажми **Create project**

GitLab покажет инструкции по добавлению remote. Запомни URL: `http://localhost:8929/root/devops-project.git`

---

## Шаг 4 — Запушить проект в GitLab

```bash
# В папке devops-project на VM
cd ~/devops-project

# Добавляем GitLab как второй remote (origin — это GitHub, gitlab — локальный)
git remote add gitlab http://localhost:8929/root/devops-project.git

# Пушим (потребует логин/пароль)
git push gitlab main
```

**Настрой SSH чтобы не вводить пароль каждый раз:**
```bash
# 1. Скопируй свой публичный ключ:
cat ~/.ssh/id_rsa.pub
# или
cat ~/.ssh/id_ed25519.pub

# 2. В GitLab: иконка пользователя → Edit Profile → SSH Keys → Add new key
# 3. Вставь ключ, сохрани

# 4. Измени remote на SSH:
git remote set-url gitlab git@localhost:2222/root/devops-project.git

# 5. Проверь:
git push gitlab main  # теперь без пароля
```

Обнови страницу GitLab — все файлы должны быть видны в репозитории.

---

## Шаг 5 — Понять GitLab Runner

**Runner** — отдельный процесс (агент) который получает задания от GitLab и выполняет их. GitLab сам не выполняет код — только раздаёт задания.

У нас **Docker executor**: каждый job запускается в отдельном Docker-контейнере. Чистое окружение на каждый job, изоляция, воспроизводимость.

**Как работает:**
```
git push → GitLab → отправляет задание Runner-у → Runner запускает Docker контейнер → выполняет команды → отправляет результат в GitLab
```

**Зарегистрировать Runner:**

GitLab → твой проект → **Settings → CI/CD → Runners → New project runner**:
- Tags: `docker`
- Нажми **Create runner**
- Скопируй токен (вида `glrt-xxxx`)

```bash
cd level-4-gitlab
bash runner/register.sh glrt-ТВОЙ_ТОКЕН
```

**Проверить:**
```bash
docker compose exec gitlab-runner gitlab-runner list
```

В GitLab UI (Settings → CI/CD → Runners) появится зелёная точка рядом с runner — он онлайн и готов.

---

## Шаг 6 — Настроить переменные CI/CD

GitLab → проект → **Settings → CI/CD → Variables → Add variable**

| Key | Value | Protected | Masked | Зачем |
|-----|-------|-----------|--------|-------|
| `SSH_PRIVATE_KEY` | содержимое `~/.ssh/deploy_key` | ✓ | ✓ | SSH на сервер |
| `SERVER_HOST` | IP твоей VM | ✓ | | куда деплоить |
| `SERVER_USER` | `ubuntu` | | | от чьего имени |

**Protected** — переменная доступна только в защищённых ветках (main). Предотвращает утечку секретов в фичёвых ветках.

**Masked** — значение скрыто в логах pipeline. Даже если pipeline публичный — ключ не виден.

---

## Шаг 7 — Запустить первый pipeline

```bash
cp level-4-gitlab/gitlab-ci/.gitlab-ci.yml ~/devops-project/.gitlab-ci.yml
cd ~/devops-project
git add .gitlab-ci.yml
git commit -m "ci: add gitlab ci pipeline"
git push gitlab main
```

GitLab → **CI/CD → Pipelines**. Pipeline запустился автоматически при push.

**Что видишь:** три стадии в виде карточек — `test`, `build`, `deploy`. Кликни на любую job для просмотра логов в реальном времени.

---

## Шаг 8 — Разобрать `.gitlab-ci.yml`

```bash
cat .gitlab-ci.yml
```

**Структура:**
```yaml
stages:          # порядок стадий
  - test
  - build
  - deploy

variables:       # переменные доступные всем job
  REGISTRY: $CI_REGISTRY   # встроенная переменная GitLab — адрес Registry

unit-tests:      # название job
  stage: test
  image: python:3.12-slim  # какой Docker образ использовать
  script:
    - pip install -r requirements.txt
    - pytest tests/

build-backend:
  stage: build
  image: docker:24
  services:
    - docker:24-dind        # Docker-in-Docker — чтобы внутри runner'а строить образы
  script:
    # пароль через stdin, а не -p: иначе он засветится в argv и warning-е docker
    - echo "$CI_REGISTRY_PASSWORD" | docker login -u $CI_REGISTRY_USER --password-stdin $CI_REGISTRY
    - docker build -t $CI_REGISTRY_IMAGE/backend:$CI_COMMIT_SHA .
    - docker push ...

deploy-prod:
  stage: deploy
  when: manual              # НЕ автоматически — нужно нажать кнопку ▶ в UI
  environment:
    name: production        # GitLab будет вести историю деплоев
```

**Встроенные переменные GitLab (CI_*):**
- `$CI_REGISTRY` — адрес встроенного Container Registry
- `$CI_COMMIT_SHA` — хэш коммита (уникальный тег образа)
- `$CI_PROJECT_NAME` — имя проекта
- `$CI_PIPELINE_ID` — ID пайплайна

---

## Шаг 9 — GitLab Container Registry

После успешного job `build-backend` образ запушен в **встроенный** Registry GitLab.

GitLab → проект → **Packages & Registries → Container Registry**

Ты увидишь образы с тегами по commit SHA.

```bash
# Залогиниться в GitLab Registry:
docker login localhost:8929 -u root -p <ТВОЙ_ПАРОЛЬ>

# Скачать образ:
docker pull localhost:8929/root/devops-project/backend:latest
```

**Почему встроенный Registry удобен:**
- Нет отдельного сервиса — всё в GitLab
- Права: если есть доступ к проекту — есть доступ к Registry
- Не нужны отдельные credentials

---

## Шаг 10 — Merge Request (правильный рабочий процесс)

В реальной команде **никто не пушит напрямую в `main`**. Работают через ветки и Merge Requests.

```bash
# Создаём ветку для изменения
git checkout -b feature/update-price-validation
git push gitlab feature/update-price-validation
```

GitLab предложит создать MR (Merge Request). Нажми на ссылку в выводе git push.

**В MR ты видишь:**
- Diff изменений — что именно меняется
- Pipeline для этой ветки запустился автоматически
- Можно оставить code review комментарии к конкретным строкам
- Pipeline должен быть зелёным чтобы смержить
- После merge — опционально удалить ветку

**Защита ветки main:**
GitLab → проект → **Settings → Repository → Protected branches**:
- `main` → Allowed to merge: Maintainers, Allowed to push: No one

Теперь никто не может пушить напрямую в main — только через MR.

---

## Шаг 11 — Environments и история деплоев

В job `deploy-prod` есть блок `environment: name: production`. Это не просто метка — GitLab ведёт историю.

GitLab → **Deployments → Environments → production**

Ты видишь:
- Список всех деплоев с датой, автором, commit SHA
- Для каждого деплоя — кнопка **Rollback**: GitLab запустит pipeline с старым commit SHA
- Текущий задеплоенный коммит

**Зачем это нужно:**
В 3:00 ночи пришёл алерт что prod упал после деплоя. Rollback в один клик — не нужно разбираться с git revert под давлением.

---

## Шаг 12 — Что сломать намеренно — Уровень 4

**Поломка 1 — Сломать код (CI должен остановить деплой)**

```bash
echo "BROKEN = )(" >> ~/devops-project/level-3-caching/backend/main.py
git add .
git commit -m "broken: test ci stops bad code"
git push gitlab main
```

GitLab → Pipelines → красный pipeline. Job `unit-tests` упал, `build` и `deploy` не запустились.

```bash
# Откатить:
git revert HEAD
git push gitlab main
```

Новый pipeline — зелёный, код починен.

**Поломка 2 — Сломать Dockerfile**

Добавь синтаксическую ошибку в `level-3-caching/backend/Dockerfile` (это реальный build-контекст пайплайна). Запушь. Pipeline должен упасть на стадии `build` — тесты прошли, но образ не собрался. Верни и запушь снова.

**Поломка 3 — Симуляция ошибки деплоя**

В `.gitlab-ci.yml` добавь `exit 1` в начало script у `deploy-prod`. Запушь и запусти деплой. Pipeline падает. Твои пользователи видят старую (рабочую) версию — rolling update не начался. Верни.

**Поломка 4 — Деплой без rolling update**

Измени деплой-скрипт на: `docker compose down && docker compose up -d`. Запусти k6 во время деплоя. Увидишь 100% ошибок пока сервис перезапускается — вот от чего спасает rolling update.

---

## Шаг 13 — Остановить GitLab

```bash
cd level-4-gitlab
docker compose down
# Данные в volumes (gitlab_data, gitlab_config, runner_config) сохраняются

# Полная очистка:
docker compose down -v
```

---

## Справочник команд — Уровень 4

| Команда | Описание |
|---------|---------|
| `docker compose exec gitlab cat /etc/gitlab/initial_root_password` | Начальный пароль root |
| `./runner/register.sh <RUNNER_TOKEN>` | Зарегистрировать runner |
| `docker compose pull && docker compose up -d --no-deps backend_1` | Обновить только один сервис |
| `git push gitlab main` | Запушить в self-hosted GitLab (второй remote) |
| `git tag v1.2.3 && git push --tags` | Создать тег (триггер для release pipeline) |
| `docker images \| grep bulletin` | Список образов с тегами |
| `trivy image --severity HIGH,CRITICAL --exit-code 1 <image>` | Блокирующая проверка на CVE |

---

## Типичные ошибки

**GitLab не запускается / OOMKilled** → Недостаточно памяти. Нужно минимум 4GB RAM. Добавь swap или увеличь VM.

**Runner не подключается** → Проверь что GitLab доступен изнутри Runner-контейнера. В docker-compose.yml runner должен быть в той же сети что и gitlab.

**"Docker-in-Docker permission denied"** → В job с `docker:dind` нужно явно подключить сервис `services: - docker:dind`. Без него docker-команды внутри runner не работают.

**Pipeline запущен, но job не берётся** → Нет доступного runner. Проверь в GitLab → Settings → Runners что runner онлайн (зелёная точка). Проверь что tag job совпадает с тегом runner.

**"Merge request pipeline failed but I want to merge"** → В settings можно отключить обязательность прохождения pipeline, но не нужно. Починить тесты.

---

## Итог уровня 4 (GitLab) — что ты умеешь

- [ ] Поднять self-hosted GitLab CE в Docker
- [ ] Настроить GitLab Runner с Docker executor
- [ ] Написать `.gitlab-ci.yml` со stages, variables, environments
- [ ] Использовать GitLab Container Registry
- [ ] Работать с Merge Requests и code review
- [ ] Наблюдать историю деплоев и делать rollback
- [ ] Объяснить разницу GitLab CI vs GitHub Actions

---

## Security Block: Уровень 4 (GitLab)

### Self-hosted платформа — сам себе облако, сам себе и защита

В отличие от GitHub/GitLab.com, здесь никто за тебя не патчит сервер и не следит за доступом — вся ответственность на тебе.

**1. Первые минуты после установки — самое уязвимое окно**

`initial_root_password` живёт в файле только 24 часа не просто так — пароль сгенерирован автоматически и должен быть заменён немедленно (Шаг 2). Публичная регистрация и публичная видимость проектов отключены сразу же (`Sign-up enabled` → off, `Default project visibility` → Private) — иначе self-hosted GitLab на публичном IP превращается в открытую платформу для кого угодно.

**2. Docker-in-Docker и privileged-режим — осознанный компромисс**

`gitlab-runner register --docker-privileged` даёт раннеру расширенные права почти до уровня хоста — это нужно, чтобы job'ы сами могли делать `docker build`. Это реальный компромисс безопасности ради функциональности: скомпрометированный job получает гораздо больше, чем без privileged. Смягчение — раннер выполняет только код из твоего же репозитория (или проверенных MR), не произвольный внешний код.

**3. Разделение портов — SSH-порт GitLab не совпадает с системным**

GitLab слушает git-SSH на `2222`, а не на `22` — системный SSH с Level 0 остаётся отдельным и не смешивается с git-трафиком (см. network-схему уровня).

**4. Registry credentials — управляются автоматически, не хардкодятся**

`$CI_REGISTRY_USER`/`$CI_REGISTRY_PASSWORD` — временные автоматические переменные GitLab, не токены, которые ты создаёшь и куда-то вписываешь руками.

⚠️ **Антипаттерны:**

- **Не сменить root-пароль в первые же минуты** — окно между установкой и первым логином видно в логах Docker и потенциально доступно любому, кто уже знает дефолт до твоей смены пароля.
- **Смонтировать `/var/run/docker.sock` с хоста в раннер вместо DinD "для простоты"** — это даёт раннеру полный контроль над Docker хост-машины (может управлять ЛЮБЫМ контейнером, включая сам GitLab), а не только временным DinD-демоном внутри job'а.

---

## Best Practices Checklist

- [ ] Root-пароль сменён сразу после первого входа, файл `initial_root_password` не используется повторно
- [ ] `Sign-up enabled` выключен — новые пользователи не могут зарегистрироваться сами
- [ ] `Default project visibility` — Private, а не Public/Internal
- [ ] Protected branch на `main` — пуш только через Merge Request
- [ ] CI/CD-секреты (SSH-ключ для деплоя) добавлены как **Masked + Protected** переменные, не в `.gitlab-ci.yml`
- [ ] Раннер использует `--docker-privileged`/DinD, а не смонтированный хостовый `docker.sock`
- [ ] Понимаешь, почему GitLab SSH на 2222, а не на 22

---

## Troubleshooting: Уровень 4 (GitLab)

### Проблемы с self-hosted платформой

**1. GitLab не отвечает / контейнер падает по памяти**

Симптом: `docker compose ps` показывает `gitlab` в статусе `Restarting` или `Exited`.

```bash
docker compose logs gitlab | tail -50
free -h
```
Вероятная причина: недостаточно RAM (нужно минимум 4GB, см. Требования к VM) — GitLab CE один занимает 2-3GB при старте. Добавь swap или увеличь VM.

**2. Runner видит job, но он висит в `pending`**

Симптом: pipeline создан, job не переходит в `running`.

```bash
docker compose logs gitlab-runner | tail -30
# В GitLab UI: Settings → CI/CD → Runners — раннер должен быть "online" (зелёная точка)
```
Вероятная причина: раннер не зарегистрирован (см. Шаг 5, `runner/register.sh`) или тег job'а (`tags: [docker, linux]`) не совпадает с тегами раннера.

**3. "Docker-in-Docker permission denied" внутри job'а**

Симптом: job падает на любой `docker build`/`docker push` команде.

```bash
cat .gitlab-ci.yml | grep -A3 "services:"
```
Вероятная причина: в job нет `services: - docker:dind`, либо раннер зарегистрирован без `--docker-privileged` — без него DinD не может поднять свой daemon.

**4. Деплой падает на SSH-шаге**

Симптом: job `deploy-prod` падает с `Permission denied (publickey)` или `Host key verification failed`.

```bash
# Проверь что переменные заданы (Settings → CI/CD → Variables):
# SSH_PRIVATE_KEY, SERVER_HOST, SERVER_USER
```
Вероятная причина: приватный ключ не добавлен как CI/CD-переменная целиком (включая `-----BEGIN...-----`/`-----END...-----`), либо публичный ключ не добавлен в `~/.ssh/authorized_keys` на VPS.

**5. Registry: `docker login` из job'а не проходит**

Симптом: `unauthorized: authentication required` на `docker push`.

```bash
echo $CI_REGISTRY_PASSWORD | docker login -u $CI_REGISTRY_USER --password-stdin $CI_REGISTRY
```
Вероятная причина: используется старый/личный токен вместо автоматических `$CI_REGISTRY_USER`/`$CI_REGISTRY_PASSWORD` — они действительны только во время выполнения конкретного job'а.

---

## Коммит

```bash
cd ~/devops-project
git add level-4-gitlab/
git add .gitlab-ci.yml
git commit -m "level-4-gitlab: self-hosted gitlab ce with ci/cd pipeline"
git push origin main
git push gitlab main
```

---

## Архитектура

- [Концепция: self-hosted CI/CD в вакууме](../docs/architecture/level-4-gitlab/concept.html) — код и registry остаются на своей инфраструктуре
- [Реализация: реальный pipeline](../docs/architecture/level-4-gitlab/implementation.html) — gitlab-ce, gitlab-runner (dind + privileged), .gitlab-ci.yml с manual gate на деплой
- [Боль → решение: Level 3 → Level 4](../docs/architecture/level-4-gitlab/pain-solution.html) — от ручного простоя к rolling-деплою с контролем над кодом
- [Сеть: новые порты 8929 и 2222](../docs/architecture/level-4-gitlab/network.html) — почему GitLab слушает SSH не на 22

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
