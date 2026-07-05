# Уровень 4 (GitLab) — Self-hosted GitLab CE + GitLab CI/CD

## Зачем начинать отсюда?

GitHub Actions — удобный облачный сервис. Но в реальных компаниях (банки, госструктуры, enterprise) часто поднимают **self-hosted GitLab**: их код не должен уходить на сторонние серверы, им нужен полный контроль над данными и инфраструктурой.

Ты должен уметь работать с обоими. GitLab CI — один из наиболее распространённых CI/CD инструментов в enterprise.

**Что получаем в одном инструменте:**
- Git-репозиторий с кодом
- Container Registry (как ghcr.io, только свой)
- CI/CD pipelines (`.gitlab-ci.yml`)
- Issue Tracker, Wiki, Merge Requests
- Environments — история деплоев с возможностью rollback

## Аналогия

GitHub Actions — снимать офис в коворкинге: удобно, быстро, но здание не твоё.
Self-hosted GitLab — купить офис: больше ответственности, но полный контроль.

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
    - docker login $CI_REGISTRY -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD
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

## Шаг 12 — Сломать pipeline намеренно

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

## Сравнение GitLab CI vs GitHub Actions

| | GitHub Actions | GitLab CI |
|--|--|--|
| Где хранится pipeline | `.github/workflows/*.yml` | `.gitlab-ci.yml` в корне |
| Registry | ghcr.io (отдельно) | Встроен в GitLab |
| Runner | GitHub-managed (бесплатно) | Свой runner (настраиваешь сам) |
| Переменные | Secrets в GitHub Settings | Variables в GitLab Settings |
| Approval для деплоя | Environment protection rules | `when: manual` или approval |
| Merge Request | Pull Request | Merge Request |
| История деплоев | Deployments tab | Environments |

---

## Типичные ошибки

**GitLab не запускается / OOMKilled** → Недостаточно памяти. Нужно минимум 4GB RAM. Добавь swap или увеличь VM.

**Runner не подключается** → Проверь что GitLab доступен изнутри Runner-контейнера. В docker-compose.yml runner должен быть в той же сети что и gitlab.

**"Docker-in-Docker permission denied"** → В job с `docker:dind` нужно явно подключить сервис `services: - docker:dind`. Без него docker-команды внутри runner не работают.

**Pipeline запущен, но job не берётся** → Нет доступного runner. Проверь в GitLab → Settings → Runners что runner онлайн (зелёная точка). Проверь что tag job совпадает с тегом runner.

**"Merge request pipeline failed but I want to merge"** → В settings можно отключить обязательность прохождения pipeline, но не нужно. Починить тесты.

---

## На собеседовании спросят

**Q: Зачем нужен Container Registry и почему не хранить образы на сервере?**
A: Сервер ephemeral — он может упасть. Registry — персистентное хранилище. При rolling update нужно скачать образ с registry на 3 разных сервера. Без registry нужно строить образ на каждом сервере отдельно.

**Q: Что такое Docker-in-Docker и зачем он нужен в CI?**
A: Наш runner сам работает в Docker-контейнере. Чтобы внутри него делать `docker build`, нужен доступ к Docker daemon. DinD (Docker in Docker) запускает отдельный Docker daemon внутри контейнера. Альтернатива — монтировать `/var/run/docker.sock` с хоста (проще, но менее безопасно).

**Q: Что такое "Protected branch" и зачем?**
A: Ветка куда нельзя пушить напрямую — только через Merge Request. Это обеспечивает: code review перед мержем, обязательное прохождение CI, аудит кто и что менял.

**Q: Как организовать деплой в несколько окружений (dev/staging/prod)?**
A: Разные jobs с разными `environment:` и разными условиями запуска. Dev: автоматически при push в feature-ветку. Staging: автоматически при мерже в main. Prod: `when: manual` после approve.

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
