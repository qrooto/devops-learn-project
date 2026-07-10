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

**Сначала — пароль PostgreSQL.** 🔒 Security: в `values.yaml` пароль намеренно пустой — этот файл коммитится в Git, а секретам в Git не место (подробно — `level-8.5-secrets`). Без пароля рендер упадёт с понятной ошибкой (`required` в шаблоне). Создай локальный values-файл:

```bash
cd level-7-helm
cp values-example.yaml values-local.yaml   # values-local.yaml в .gitignore, в Git не попадёт
# при желании поменяй пароль внутри
```

Во всех командах `helm template / install / upgrade` ниже добавляется `-f values-local.yaml`. Альтернатива — каждый раз передавать `--set postgres.password=...`.

**Перед каждым деплоем** — смотри что получится:

```bash
# Отрисовать манифесты без отправки в K8s:
helm template bulletin-board ./bulletin-board/ -f values-local.yaml
```

Выведет все K8s манифесты с подставленными значениями. Можно передать в `kubectl apply` напрямую, но обычно используют `helm install`.

```bash
# Проверить синтаксис чарта:
helm lint ./bulletin-board/
# 1 chart(s) linted, 0 chart(s) failed
```

```bash
# Dry run — симулирует установку, показывает что будет создано:
helm install bulletin-board ./bulletin-board/ -f values-local.yaml --dry-run --debug
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
helm install bulletin-board ./bulletin-board/ -f values-local.yaml
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
helm upgrade bulletin-board ./bulletin-board/ -f values-local.yaml --set backend.replicas=5

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
helm upgrade bulletin-board ./bulletin-board/ -f values-local.yaml -f values-prod.yaml
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
  -f values-local.yaml \
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

> Трюк с репликами даёт только грубые доли (1 из 10 Pod-ов ≈ 10%). Точный canary делается на уровне Ingress: у ingress-nginx (см. `level-5.5-ingress/`) есть аннотации `nginx.ingress.kubernetes.io/canary: "true"` и `canary-weight: "10"` — ровно 10% трафика независимо от числа реплик.

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

**Поздравляю — основы деплоя в Kubernetes пройдены!**

Дальше: `level-8-gitops` (ArgoCD) → `level-9-terraform` (Infrastructure as Code) → `level-10-ansible` (config management).

---

## Коммит

```bash
cd ..
git add level-7-helm/
git commit -m "level-7: helm chart with blue-green and canary deploy"
git push origin main
```

---

## Security Block: Уровень 7

### Секреты в Helm — осторожно

**1. Никогда не хранить пароли в `values.yaml`**

`values.yaml` коммитится в git. Если туда попал пароль PostgreSQL или SECRET_KEY — он навсегда в истории репозитория. Именно поэтому в нашем чарте `postgres.password` пустой, а шаблон через `required` отказывается рендериться без пароля — забыть его невозможно.

Правильный подход:
```bash
# Передавать секреты через --set при деплое (они не попадают в git):
helm upgrade bulletin-board ./bulletin-board/ \
  --set postgres.password="${POSTGRES_PASSWORD}" \
  --set backend.secretKey="${SECRET_KEY}"

# Или использовать Helm Secrets (плагин для шифрования values):
helm plugin install https://github.com/jkroepke/helm-secrets
```

**2. История релизов хранит секреты в K8s Secrets**

Helm хранит каждую ревизию как Kubernetes Secret в namespace. Если Secret передаёт пароль через `--set` — он есть в этих данных. Для очистки истории:
```bash
# Посмотреть helm-секреты:
kubectl get secrets -l owner=helm -n bulletin-board

# Ограничить историю (хранить последние 5 ревизий):
helm upgrade ... --history-max=5
```

**3. Blue-Green: не забудь удалить старый slot**

После переключения трафика на green, blue остаётся запущенным. Если там старая версия с уязвимостью — это лишняя поверхность атаки. Удаляй старый deployment после успешного переключения.

⚠️ **Антипаттерны:**

- **Пароли в `values.yaml`** — даже в приватном репозитории это плохо: CI-системы, коллеги, утечки — и пароль скомпрометирован.
- **`helm install` с `--debug` в CI** — флаг `--debug` выводит все values в лог включая секреты. Используй только для локальной отладки.

---

## Best Practices Checklist

- [ ] Пароли не в `values.yaml` — передаются через `--set` или Helm Secrets
- [ ] `helm lint` проходит без предупреждений
- [ ] `helm template` проверен перед деплоем — нет неожиданных манифестов
- [ ] Blue-Green: после переключения старый deployment удалён
- [ ] `--history-max` настроен чтобы helm history не хранился бесконечно
- [ ] Rollback протестирован — `helm rollback` возвращает предыдущую версию

---

## Troubleshooting: Уровень 7

### Проблемы с Helm

**1. `Error: release already exists`**

```bash
# Смотрим список релизов:
helm list -A

# Если хочешь переустановить:
helm uninstall bulletin-board
helm install bulletin-board ./bulletin-board/ -f values-local.yaml

# Или если хочешь обновить (правильный путь):
helm upgrade --install bulletin-board ./bulletin-board/ -f values-local.yaml
# --install: установит если не существует, обновит если существует
```

**2. Шаблон рендерится с ошибкой**

```bash
# Проверяем без деплоя:
helm template bulletin-board ./bulletin-board/ -f values-local.yaml 2>&1 | head -30

# Lint (статический анализ):
helm lint ./bulletin-board/

# Dry run с подробным выводом:
helm install bulletin-board ./bulletin-board/ -f values-local.yaml --dry-run --debug 2>&1 | grep -E "Error|error"

# Частая ошибка: отступы в шаблонах (YAML чувствителен к пробелам)
# Проверь конкретный файл:
helm template ./bulletin-board/ -f values-local.yaml --show-only templates/backend.yaml
```

**3. Blue-Green: трафик не переключается**

```bash
# Проверяем selector у Service:
kubectl get svc backend -n bulletin-board -o jsonpath='{.spec.selector}' | python3 -m json.tool

# Проверяем labels у Pod-ов:
kubectl get pods -n bulletin-board -l slot=green --show-labels

# Применяем patch вручную:
kubectl patch service backend -n bulletin-board \
  -p '{"spec":{"selector":{"slot":"green","app":"backend"}}}'

# Проверяем endpoints (Pod-ы которые получают трафик):
kubectl get endpoints backend -n bulletin-board
```

**4. Rollback не работает — Pod-ы не стартуют**

```bash
# Helm откатил манифесты, но образ может быть недоступен
helm history bulletin-board

# Посмотреть что Helm пытается применить:
helm get manifest bulletin-board | grep image

# Если образ удалён из registry — нужно пересобрать:
eval $(minikube docker-env)
docker build -t bulletin-board-backend:old-version ../level-3-caching/backend/

# Или откатиться на ревизию где образ точно есть:
helm rollback bulletin-board 1
```

**5. Helm values применяются не те**

```bash
# Посмотреть какие values сейчас у запущенного релиза:
helm get values bulletin-board

# Посмотреть все values (включая defaults):
helm get values bulletin-board --all

# Сравнить с тем что ты хочешь:
helm upgrade bulletin-board ./bulletin-board/ -f values-local.yaml --dry-run | grep replicas
```

---

## Архитектура

- [Концепция: Blue-Green деплой в вакууме](../docs/architecture/level-7-helm/concept.html) — мгновенное атомарное переключение трафика, без привязки к Helm
- [Реализация: реальный Helm-чарт](../docs/architecture/level-7-helm/implementation.html) — templates + values.yaml → готовые манифесты
- [Боль → решение: Level 5 → Level 7](../docs/architecture/level-7-helm/pain-solution.html) — от разрозненных kubectl apply к версионированным релизам

Сетевой схемы для этого уровня нет: топология в кластере та же, что на Level 5 — Helm меняет только способ доставки манифестов, не сеть (см. [network Level 5](../docs/architecture/level-5-kubernetes/network.html)).

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
