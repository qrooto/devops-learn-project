# Уровень 7 — Helm + Blue-Green деплой

## Зачем начинать отсюда?

На уровне 5 ты применял манифесты по одному: `kubectl apply -f k8s/postgres/`, потом `k8s/redis/`, потом `k8s/backend/`... При обновлении образа — редактируй deployment.yml, помни порядок. При добавлении нового окружения (staging) — копируй папку, меняй значения в 10 файлах.

**Проблемы голых манифестов:**
- Конфигурация размазана по десяткам файлов
- Нет версионирования: "что именно было задеплоено вчера?"
- Нет удобного отката: нужно помнить что менял
- Дублирование: dev/staging/prod — три копии почти одинаковых файлов

**Helm** — пакетный менеджер для Kubernetes. Как `apt` для Ubuntu или `npm` для Node.js, только для K8s-приложений. Один чарт — одна команда — весь стек задеплоен.

## Аналогия

Голые манифесты — как IKEA инструкция на 40 листах где каждый шаг надо читать и повторять.
Helm — как собранный IKEA с кнопкой "установить версию X". История сборок хранится, нажал rollback — вернулось как было.

## Архитектура: Chart

```
bulletin-board/              ← Chart (пакет)
├── Chart.yaml               ← имя, версия, описание
├── values.yaml              ← параметры по умолчанию
├── values-prod.yaml         ← переопределение для production
└── templates/               ← K8s манифесты с Go-шаблонами
    ├── namespace.yaml
    ├── postgres.yaml        ← {{ .Values.postgres.password }}
    ├── redis.yaml
    ├── backend.yaml         ← {{ .Values.backend.replicas }}
    └── nginx.yaml           ← {{ .Values.nginx.port }}
```

**Как это работает:**
```
helm install my-app ./bulletin-board/ --set backend.replicas=5
        │
        └── Helm читает values.yaml + --set параметры
            → подставляет в templates/
            → получает обычные K8s манифесты
            → применяет через kubectl
            → сохраняет "релиз" в K8s Secret (история)
```

---

## Шаг 1 — Установить Helm

```bash
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
helm version
# version.BuildInfo{Version:"v3.x.x"...}
```

---

## Шаг 2 — Изучить структуру чарта

```bash
cat level-7-helm/bulletin-board/Chart.yaml
```

```yaml
apiVersion: v2
name: bulletin-board
description: Доска объявлений — учебный проект
type: application
version: 0.1.0         # версия самого чарта
appVersion: "2.0.0"    # версия приложения
```

```bash
cat level-7-helm/bulletin-board/values.yaml
```

**Посмотри на шаблон:**
```bash
cat level-7-helm/bulletin-board/templates/backend.yaml
```

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend
  namespace: {{ .Values.namespace }}      # ← из values
spec:
  replicas: {{ .Values.backend.replicas }} # ← из values
  template:
    spec:
      containers:
      - image: {{ .Values.backend.image }}:{{ .Values.backend.tag }}
        resources:
          limits:
            memory: {{ .Values.backend.resources.limits.memory }}
```

**Задание:** Найди в `values.yaml` значение `backend.replicas`. Что произойдёт если при установке передать `--set backend.replicas=5`?

---

## Шаг 3 — Проверить шаблоны (без K8s)

**Перед каждым деплоем** — смотри что получится:

```bash
cd level-7-helm

# Отрисовать манифесты без отправки в K8s:
helm template bulletin-board ./bulletin-board/
```

Выведет все K8s манифесты с подставленными значениями. Можно передать в `kubectl apply` напрямую, но обычно используют `helm install`.

```bash
# Проверить синтаксис чарта:
helm lint ./bulletin-board/
# 1 chart(s) linted, 0 chart(s) failed
```

```bash
# Dry run — симулирует установку, показывает что будет создано:
helm install bulletin-board ./bulletin-board/ --dry-run --debug
```

---

## Шаг 4 — Установить чарт

```bash
# Убедись что minikube запущен:
minikube start --driver=docker

# Загрузи образ бэкенда в minikube:
eval $(minikube docker-env)
docker build -t bulletin-board-backend:latest ../level-3-caching/backend/

# Установить чарт:
helm install bulletin-board ./bulletin-board/
```

**Вывод:**
```
NAME: bulletin-board
LAST DEPLOYED: Mon Jan 01 12:00:00 2025
NAMESPACE: default
STATUS: deployed
REVISION: 1
```

```bash
# Статус релиза:
helm status bulletin-board

# Что создано:
kubectl get all -n bulletin-board
```

---

## Шаг 5 — Обновить релиз

```bash
# Изменить количество реплик без редактирования файлов:
helm upgrade bulletin-board ./bulletin-board/ --set backend.replicas=5

# Наблюдать rolling update:
kubectl get pods -n bulletin-board -w
```

**Для разных окружений — разные values-файлы:**

```bash
cat level-7-helm/values-prod.yaml
```

```yaml
backend:
  replicas: 5
  resources:
    limits:
      memory: "512Mi"
      cpu: "1000m"

postgres:
  storage: "20Gi"
```

```bash
# Деплой в prod:
helm upgrade bulletin-board ./bulletin-board/ -f values-prod.yaml
```

Один чарт — три окружения (dev/staging/prod), каждое с своими values.

---

## Шаг 6 — История и откат

```bash
# История всех деплоев этого релиза:
helm history bulletin-board
```

```
REVISION  STATUS     CHART                DESCRIPTION
1         superseded bulletin-board-0.1.0  Install complete
2         superseded bulletin-board-0.1.0  Upgrade complete
3         deployed   bulletin-board-0.1.0  Upgrade complete
```

```bash
# Откатиться на конкретную ревизию:
helm rollback bulletin-board 1

# Helm автоматически запустит rolling update назад
# Через 10-15 секунд:
helm status bulletin-board
```

```
REVISION  STATUS     DESCRIPTION
1         superseded Install complete
2         superseded Upgrade complete
3         superseded Upgrade complete
4         deployed   Rollback to 1
```

**Почему Helm rollback удобнее `kubectl rollout undo`?**
`kubectl rollout undo` откатывает только Deployment (один ресурс). Helm откатывает **все** ресурсы релиза: Deployment, Service, ConfigMap, Secret — до состояния той ревизии.

---

## Шаг 7 — Blue-Green деплой

Rolling update (уровни 4-5) заменяет Pod-ы постепенно. В процессе деплоя одновременно работают старая и новая версия кода. Для большинства приложений это нормально.

**Когда нужен blue-green:**
- Breaking changes в API (старые и новые клиенты не совместимы)
- Критичные деплои где нельзя иметь смешанные версии
- Нужен немедленный rollback (не 5 минут, а секунды)

```
Blue (текущая версия) → Service → трафик
Green (новая версия)  → (нет трафика, тестируем)

После проверки:
Blue → (остановить)
Green → Service → трафик
```

**Реализация:**

```bash
# Проверь что blue запущен (наш текущий деплой):
kubectl get pods -n bulletin-board -l slot=blue

# Собери новую версию образа:
docker build -t bulletin-board-backend:v2 ../level-3-caching/backend/

# Создай green Deployment через helm upgrade с новым слотом:
helm upgrade bulletin-board ./bulletin-board/ \
  --set backend.slot=green \
  --set backend.image.tag=v2

# Дождись пока green Pod-ы поднялись:
kubectl rollout status deployment/backend-green -n bulletin-board

# Проверь green напрямую (без nginx):
kubectl port-forward deployment/backend-green 8001:8000 -n bulletin-board &
curl http://localhost:8001/api/health
# Тестируй как угодно — пользователи всё ещё на blue

# Переключаем трафик на green:
kubectl patch service backend -n bulletin-board \
  -p '{"spec":{"selector":{"slot":"green"}}}'

# Убеждаемся что работает:
curl http://$(minikube ip):30080/api/health

# Если всё хорошо — удаляем blue:
kubectl delete deployment backend-blue -n bulletin-board

# Если что-то пошло не так — откат за 1 секунду:
kubectl patch service backend -n bulletin-board \
  -p '{"spec":{"selector":{"slot":"blue"}}}'
```

**Что происходит при переключении:** Service меняет `selector`. Kubernetes немедленно обновляет endpoints — трафик идёт на новые Pod. Ни один запрос не теряется.

---

## Шаг 8 — Canary деплой (бонус)

Blue-green — переключение всего трафика сразу. Canary — постепенное: сначала 10% на новую версию.

```yaml
# Два Deployment с разными replicas:
# backend-stable: 9 реплик (90% трафика при round-robin)
# backend-canary: 1 реплика (10% трафика)

# Оба имеют label: app=backend
# Service selector: app=backend → балансирует между всеми 10 Pod
```

```bash
# Создать canary:
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-canary
  namespace: bulletin-board
spec:
  replicas: 1
  selector:
    matchLabels:
      app: backend
      track: canary
  template:
    metadata:
      labels:
        app: backend
        track: canary
    spec:
      containers:
      - name: backend
        image: bulletin-board-backend:v2
EOF

# Мониторим метрики на /api/metrics — смотрим error rate для новой версии
# Если всё хорошо — увеличиваем canary replicas и уменьшаем stable
# Если плохо — удаляем canary без последствий для пользователей
```

---

## Шаг 9 — Удалить всё

```bash
# Удалить весь Helm-релиз (все K8s ресурсы):
helm uninstall bulletin-board

# Проверить что ничего не осталось:
kubectl get all -n bulletin-board

# Остановить minikube:
minikube stop
```

---

## Типичные ошибки

**"release already exists"** → Уже есть релиз с этим именем. Используй `helm upgrade` вместо `helm install`. Или удали старый: `helm uninstall bulletin-board`.

**"rendered manifests contain a resource that already exists"** → Ресурс создан не через Helm (например через `kubectl apply`). Решение: `helm install ... --replace` или удали ресурс вручную.

**"helm rollback — новые Pod не запускаются"** → Образ который был в той ревизии может быть недоступен (удалён из Registry). Rollback в Helm откатывает манифесты, но не восстанавливает образы.

**"values в --set vs -f"** → `--set` переопределяет конкретные значения. `-f values-prod.yaml` подгружает весь файл. Оба можно использовать одновременно, `--set` приоритетнее.

---

## На собеседовании спросят

**Q: Чем Helm отличается от простого `kubectl apply -f`?**
A: kubectl apply — применить манифест. Нет версионирования, нет отката, нет параметризации. Helm добавляет: шаблоны (один чарт для dev/prod), историю ревизий, rollback одной командой, управление зависимостями (подчарты).

**Q: Что такое Helm Release и где хранится история?**
A: Release — экземпляр установленного чарта. История хранится как Kubernetes Secret в том же namespace. `kubectl get secret -l owner=helm` покажет все ревизии.

**Q: В чём разница Blue-Green и Canary?**
A: Blue-Green: одномоментное переключение всего трафика. Нулевой риск смешанных версий, быстрый rollback, но нет возможности "попробовать на части пользователей". Canary: постепенное переключение (10% → 30% → 100%). Можно поймать проблему на малом трафике до полного rollout. Сложнее в реализации.

**Q: Как Helm управляет зависимостями?**
A: Через `Chart.yaml → dependencies`. Можно указать что ваш чарт зависит от `postgresql` и `redis` чартов из публичных репозиториев. `helm dependency update` скачает их в `charts/`. При установке всё ставится вместе.

---

## Итог уровня 7 — что ты умеешь

- [ ] Создать Helm-чарт с параметризацией через values.yaml
- [ ] Установить, обновить и откатить релиз
- [ ] Использовать разные values для dev/staging/prod
- [ ] Реализовать blue-green деплой через переключение Service selector
- [ ] Понять разницу rolling update vs blue-green vs canary
- [ ] `helm template` и `helm lint` для отладки до деплоя

**Поздравляю — все 7 основных уровней пройдены!**

Дальше: `level-3.5-https` (Traefik + TLS), `level-8-gitops` (ArgoCD), `level-9-terraform` (Infrastructure as Code).

---

## Коммит

```bash
cd ..
git add level-7-helm/
git commit -m "level-7: helm chart with blue-green and canary deploy"
git push origin main
```
