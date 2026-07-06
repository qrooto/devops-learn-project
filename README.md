# DevOps Learning Project — Доска объявлений

Практический курс по DevOps: от одного контейнера до Kubernetes с CI/CD, мониторингом и IaC.

**Принцип каждого уровня:** строим → ломаем → наблюдаем → чиним → идём дальше.

Каждый следующий уровень вводит новый инструмент только тогда, когда ты лично почувствовал боль которую он решает.

---

## Подготовка виртуальной машины (Linux)

> Всё выполняется на Linux VM (Ubuntu 24.04 / Debian 12). Для старта (уровни 1-4, 9-10) достаточно 1-2 CPU / 2GB RAM / 20GB SSD; для Kubernetes и мониторинга (уровни 5-8) — от 4GB RAM. Профили и обоснование — [INFRASTRUCTURE_PLANNING.md](INFRASTRUCTURE_PLANNING.md).

### 1. Обновить систему

```bash
sudo apt update && sudo apt upgrade -y
```

### 2. Установить Docker

```bash
# Официальный скрипт установки
curl -fsSL https://get.docker.com | sudo sh

# Добавить себя в группу docker (чтобы не писать sudo каждый раз)
sudo usermod -aG docker $USER

# Применить изменение группы без перелогина
newgrp docker

# Проверить:
docker --version
docker compose version
```

> **Зачем `usermod -aG docker`?** Docker daemon работает от root. Группа `docker` даёт доступ к сокету `/var/run/docker.sock` без sudo. Это нужно для удобства — не безопасность.

### 3. Установить Git и настроить

```bash
sudo apt install -y git

git config --global user.name "Твоё Имя"
git config --global user.email "твой@email.com"

# Сохранить credentials чтобы не вводить пароль каждый раз:
git config --global credential.helper store
```

### 4. Установить k6 (нагрузочное тестирование)

```bash
sudo gpg --no-default-keyring \
  --keyring /usr/share/keyrings/k6-archive-keyring.gpg \
  --keyserver hkp://keyserver.ubuntu.com:80 \
  --recv-keys C5AD17C747E3415A3642D57D77C6C491D6AC1D69

echo "deb [signed-by=/usr/share/keyrings/k6-archive-keyring.gpg] https://dl.k6.io/deb stable main" \
  | sudo tee /etc/apt/sources.list.d/k6.list

sudo apt update && sudo apt install -y k6
k6 version
```

### 5. Клонировать репозиторий

```bash
git clone https://github.com/<твой-username>/devops-project.git
cd devops-project
```

---

## Карта уровней

| Уровень | Папка | Стек | Что осваиваем |
|---------|-------|------|---------------|
| 1 | `level-1-monolith/` | Docker Compose, Nginx, FastAPI, PostgreSQL, JWT, Alembic | Базовый деплой, авторизация, миграции |
| 2 | `level-2-scaling/` | + балансировка Nginx, 3 инстанса | Горизонтальное масштабирование, failover |
| 3 | `level-3-caching/` | + Redis | Кэширование, инвалидация, slow queries |
| 3.5 | `level-3.5-https/` | + Traefik, Let's Encrypt | TLS, HTTPS, автосертификаты |
| 4a | `level-4-cicd/` | GitHub Actions | CI/CD в облаке, rolling update |
| 4b | `level-4-gitlab/` | Self-hosted GitLab CE + GitLab CI | Git-платформа, MR, Registry, Environments |
| 5 | `level-5-kubernetes/` | minikube, kubectl | Оркестрация, self-healing, HPA, probes |
| 6 | `level-6-monitoring/` | Prometheus, Grafana, Loki, Promtail, cAdvisor | Полный observability stack |
| 6.5 | `level-6.5-ai-agent/` | Python, FastAPI, Claude API, Telegram Bot API | AI-диагностика, webhook, approve/reject actions |
| 7 | `level-7-helm/` | Helm | Helm charts, blue-green, canary |
| 8 | `level-8-gitops/` | ArgoCD | GitOps, drift detection, self-healing |
| 9 | `level-9-terraform/` | Terraform | Infrastructure as Code, state, plan/apply |
| 10 | `level-10-ansible/` | Ansible, роли, handlers, Vault | Fleet provisioning, config management |

### Рекомендуемый порядок

```
1 (Монолит) → 2 (Масштабирование) → 3 (Кэш) → 3.5 (HTTPS)
  → 4b (GitLab) → 5 (Kubernetes) → 6 (Мониторинг) → 6.5 (AI Agent) → 7 (Helm)
  → 8 (GitOps) → 9 (Terraform) → 10 (Ansible)
```

Уровень 4a (GitHub Actions) — параллельно с 4b для сравнения двух CI/CD систем.

### Архитектурные диаграммы

[**Мета-схема: вся эволюция системы за 30 секунд**](docs/architecture/00-overview.html) — все 13 уровней как один непрерывный путь от одного сервера до self-healing production-стека.

Для каждого уровня — concept (абстрактная теория) / implementation (реальный конфиг) / pain-solution (было → стало) / network (где есть что показать) диаграммы в `docs/architecture/level-N/`, со ссылками в конце README каждого уровня. Отдельно — [`docs/architecture/networking-theory/`](docs/architecture/networking-theory/) с углублёнными схемами по конкретным сетевым темам (порты и сокеты, TCP-handshake, HTTP, TLS, Docker/Kubernetes сети, webhooks, SSH fan-out) — не привязаны к проекту, пригодятся и за его пределами.

Все диаграммы — самодостаточные `.html` файлы (тема, экспорт в PNG/SVG прямо в браузере); GitHub показывает только код, открывай локально.

---

## Боль → Решение (логика прогрессии)

| Боль | Решение |
|------|---------|
| Один бэкенд задыхается под нагрузкой | Уровень 2: горизонтальное масштабирование |
| PostgreSQL — узкое место при 3 инстансах | Уровень 3: Redis кэш |
| HTTP не защищён, нет сертификата | Уровень 3.5: Traefik + Let's Encrypt |
| Деплой роняет сервис на несколько секунд | Уровень 4: CI/CD + rolling update |
| Docker Compose не перезапускает упавшие контейнеры | Уровень 5: Kubernetes self-healing |
| Не видно что происходит в production | Уровень 6: Prometheus + Grafana + Loki |
| Алерты требуют ручной интерпретации логов и метрик | Уровень 6.5: AI-агент с диагностикой через Claude API |
| Деплой K8s — набор kubectl apply по очереди | Уровень 7: Helm |
| Кто-то вручную изменил K8s ресурс — не знаем | Уровень 8: ArgoCD drift detection |
| Инфраструктура создаётся руками, не воспроизводимо | Уровень 9: Terraform |
| Настройка 10+ VM — вручную, медленно, неповторяемо | Уровень 10: Ansible fleet management |

---

## Как работать с репозиторием

Каждый уровень — самодостаточная папка. Читай README внутри — там пошаговые инструкции с объяснениями.

```bash
cd level-1-monolith
# Читай README.md
docker compose up --build -d
```

**Перед каждым уровнем** убедись что предыдущий остановлен:
```bash
docker compose down
```

---

## Git-воркфлоу

```bash
# Статус изменений
git status

# Коммит после завершения уровня
git add level-1-monolith/
git commit -m "level-1: monolith with jwt auth and alembic migrations"
git push origin main
```

Коммить после каждого уровня — это часть учёбы. Через 9 уровней у тебя будет история прогресса.

---

## Дополнительные инструменты (устанавливаются по мере прохождения)

| Инструмент | Уровень | Зачем |
|-----------|---------|-------|
| kubectl | 5 | Управление Kubernetes |
| minikube | 5 | Локальный K8s |
| Helm | 7 | Пакетный менеджер K8s |
| ArgoCD CLI | 8 | GitOps деплой |
| Terraform | 9 | Infrastructure as Code |
| Ansible | 10 | Fleet provisioning, config management |

Команды установки есть в README каждого уровня.
