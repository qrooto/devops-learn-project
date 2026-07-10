# Уровень 5 — Kubernetes (minikube)

> **Тип сессии:** разделы «Зачем», «Аналогия», «Как это работает», «На собеседовании спросят», Security Block — **[голова]**: можно читать в дороге, без терминала. Шаги с командами, «Что сломать намеренно», Troubleshooting на живой поломке — **[руки]**: нужна домашняя сессия с VM. Легенда — в START_HERE.md.

## Зачем начинать отсюда?

Docker Compose — отличный инструмент для разработки. Но в production у него есть принципиальные ограничения:

- **Нет self-healing:** упал контейнер — надо идти и перезапускать вручную
- **Нет автомасштабирования:** нагрузка выросла втрое — добавляй инстансы руками
- **Нет управления ресурсами:** один контейнер может съесть всю RAM, положив остальные
- **Rolling update — сделал сам:** в Docker Compose это набор bash-скриптов, в K8s — встроено
- **Нет самовосстановления:** если сервер перезагрузился, кто запустит контейнеры?

**Kubernetes** решает всё это системно. Это не просто "Docker Compose++", это другой уровень абстракции — ты описываешь желаемое состояние кластера, K8s делает всё остальное.

## Аналогия

Docker Compose — ты сам управляешь каждым работником: кого нанять, уволить, сколько платить.
Kubernetes — HR-отдел с автоматизацией: сам набирает если кто-то заболел, сам масштабирует при наплыве задач, сам следит за ресурсами.

## Ключевые концепции

```
┌─────────────── Cluster ────────────────────┐
│                                            │
│  ┌──── Node (VM/server) ──────────────┐   │
│  │                                    │   │
│  │  Pod (1+ контейнеров вместе)       │   │
│  │    └── Container: backend          │   │
│  │                                    │   │
│  │  Pod                               │   │
│  │    └── Container: postgres         │   │
│  └────────────────────────────────────┘   │
│                                            │
│  Deployment → управляет Pod (replicas)    │
│  Service    → стабильный DNS для Pod      │
│  ConfigMap  → конфигурация (не секреты)   │
│  Secret     → пароли, токены              │
│  HPA        → автомасштабирование Pod     │
└────────────────────────────────────────────┘
```

**Pod vs Container:** Pod — обёртка вокруг контейнера(ов). Контейнеры в одном Pod делят сеть и volumes. Обычно 1 контейнер = 1 Pod.

**Deployment vs Pod:** Никогда не создавай Pod напрямую. Deployment — это "хочу 3 копии этого Pod". Если Pod умрёт — Deployment пересоздаст его.

**Service:** Pod-ы эфемерны — IP меняется при каждом пересоздании. Service — стабильный DNS-адрес (`backend.bulletin-board.svc.cluster.local`) который всегда указывает на живые Pod-ы.

---

## Шаг 1 — Установить minikube и kubectl

```bash
# kubectl — CLI для работы с Kubernetes
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl
kubectl version --client

# minikube — однонодовый K8s для обучения
curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
sudo install minikube-linux-amd64 /usr/local/bin/minikube
minikube version
```

---

## Шаг 2 — Запустить minikube

```bash
# Кластер на 4GB RAM, 2 CPU (минимум для нашего стека)
minikube start --driver=docker --memory=4096 --cpus=2

# Проверка:
minikube status
kubectl get nodes
```

**Что должен увидеть:**
```
NAME       STATUS   ROLES           AGE   VERSION
minikube   Ready    control-plane   1m    v1.31.x
```

`Ready` — кластер работает. `control-plane` — эта нода управляет кластером (в prod control-plane отдельно от рабочих нод).

---

## Шаг 3 — Изучить структуру манифестов

```bash
ls level-5-kubernetes/k8s/
# backend/  nginx/  postgres/  redis/  namespace.yml
```

**Разбери один манифест:**
```bash
cat k8s/backend/deployment.yml
```

**Ключевые части Deployment:**
```yaml
spec:
  replicas: 3                    # сколько Pod держать живыми

  template:
    spec:
      containers:
      - name: backend
        image: bulletin-board-backend:latest
        resources:
          requests:
            cpu: "100m"          # минимум, нужен для планировщика
            memory: "128Mi"
          limits:
            cpu: "500m"          # максимум — не позволит съесть весь CPU
            memory: "512Mi"

        readinessProbe:          # "готов принимать трафик?"
          httpGet:
            path: /api/health
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 5

        livenessProbe:           # "жив ли вообще?"
          httpGet:
            path: /api/health
            port: 8000
          failureThreshold: 3    # 3 провала → перезапустить
```

**Зачем requests и limits?**
- `requests` — гарантированные ресурсы. K8s не поставит Pod на ноду где их нет.
- `limits` — максимум. При превышении CPU — throttling. При превышении memory — OOMKill (Pod убивается и пересоздаётся).

Без limits один Pod может положить весь сервер.

---

## Шаг 4 — Собрать образ в minikube

minikube имеет свой Docker daemon, изолированный от системного. Образы нужно собрать именно там:

```bash
# Переключаем docker CLI на daemon внутри minikube
eval $(minikube docker-env)

# Собираем образ
docker build -t bulletin-board-backend:latest level-3-caching/backend/

# Убедись что образ видит minikube:
docker images | grep bulletin-board
```

**Важно:** `eval $(minikube docker-env)` меняет переменные только в текущем терминале. В новом окне — повтори эту команду.

**В production:** образ берётся из Container Registry (ghcr.io, ECR, GitLab Registry). В манифесте указываешь полный путь: `image: ghcr.io/username/bulletin-board:v1.2.3`

---

## Шаг 5 — Применить манифесты

```bash
cd level-5-kubernetes

# Namespace — изолированное пространство имён для нашего приложения
kubectl apply -f k8s/namespace.yml

# PostgreSQL (Secret + PVC + Deployment + Service)
kubectl apply -f k8s/postgres/

# Redis
kubectl apply -f k8s/redis/

# Ждём пока PostgreSQL запустится (readiness probe должен пройти)
kubectl wait --for=condition=ready pod -l app=postgres -n bulletin-board --timeout=120s

# Backend (ConfigMap + Deployment + Service + HPA)
kubectl apply -f k8s/backend/

# Nginx
kubectl apply -f k8s/nginx/
```

**Смотри что поднялось:**
```bash
kubectl get all -n bulletin-board
```

```
NAME                           READY   STATUS    RESTARTS   AGE
pod/backend-7d9f4b8c5-k2p4n   1/1     Running   0          30s
pod/backend-7d9f4b8c5-m9x7q   1/1     Running   0          30s
pod/backend-7d9f4b8c5-n4r8s   1/1     Running   0          30s
pod/postgres-...               1/1     Running   0          2m
pod/redis-...                  1/1     Running   0          90s

NAME               TYPE       CLUSTER-IP      PORT(S)
service/backend    ClusterIP  10.96.45.12     8000/TCP
service/nginx      NodePort   10.96.78.23     80:30080/TCP
service/postgres   ClusterIP  10.96.34.56     5432/TCP
```

---

## Шаг 6 — Открыть приложение

```bash
# Открыть в браузере через туннель minikube:
minikube service nginx -n bulletin-board

# Или узнать IP и открыть вручную:
echo "http://$(minikube ip):30080"
```

Зарегистрируйся, создай объявление. Всё работает как раньше, но теперь под управлением Kubernetes.

> NodePort на 30080 — учебный «чёрный ход»: нестандартный порт, нет TLS, по порту на каждый сервис. Как устроен реальный вход в кластер (Ingress + cert-manager) — уровень 5.5, после этого уровня.

---

## Шаг 7 — Наблюдать self-healing

Это ключевой урок Kubernetes: ты описываешь **желаемое состояние**, K8s его поддерживает.

**Терминал 1:**
```bash
kubectl get pods -n bulletin-board -w
# -w = watch, обновляется в реальном времени
```

**Терминал 2:**
```bash
# Посмотри имя какого-нибудь backend-pod:
kubectl get pods -n bulletin-board

# Убей его:
kubectl delete pod <имя-pod> -n bulletin-board
```

**В Терминале 1 увидишь:**
```
backend-7d9f4b8c5-k2p4n   1/1   Running    0   5m
backend-7d9f4b8c5-k2p4n   1/1   Terminating  0   5m   ← удалили
backend-7d9f4b8c5-zx9m2   0/1   Pending      0   0s   ← K8s создаёт новый
backend-7d9f4b8c5-zx9m2   0/1   ContainerCreating  0   0s
backend-7d9f4b8c5-zx9m2   1/1   Running      0   8s   ← готов
```

Всё это произошло автоматически. В Docker Compose пришлось бы идти и вручную запускать `docker compose up`.

**Убей Pod дважды быстро** — K8s всё равно поддержит `replicas: 3`.

---

## Шаг 8 — Readiness и Liveness probe

```bash
# Посмотреть детали Pod включая события:
kubectl describe pod <имя-pod> -n bulletin-board
```

В разделе `Events` видишь историю: запуск, прохождение probe, рестарты.

**Сэмулируй нездоровый Pod:**
```bash
# Зайди внутрь Pod
kubectl exec -it <pod-name> -n bulletin-board -- bash

# Убей сервер изнутри (liveness probe перестанет отвечать)
kill 1
exit
```

Kubernetes обнаружит что liveness probe не отвечает и перезапустит контейнер.

**Разница probe:**
- **readinessProbe** — Pod не получает трафик пока не здоров. Приложение стартует 10+ секунд, K8s ждёт.
- **livenessProbe** — если перестал отвечать — пересоздать. Защищает от deadlock.
- **startupProbe** — даёт время стартовать медленным приложениям (JVM, например).

---

## Шаг 9 — ConfigMap и Secret

```bash
# Посмотреть ConfigMap:
kubectl get configmap -n bulletin-board
kubectl describe configmap backend-config -n bulletin-board

# Посмотреть Secret (значения base64):
kubectl get secret -n bulletin-board
kubectl describe secret postgres-secret -n bulletin-board

# Декодировать значение:
kubectl get secret postgres-secret -n bulletin-board -o jsonpath='{.data.password}' | base64 -d
```

**Важно:** Kubernetes Secrets хранятся в etcd в base64, не зашифрованы по умолчанию. В production нужно: Sealed Secrets или External Secrets Operator (интеграция с Vault/AWS Secrets Manager).

---

## Шаг 10 — Rolling update в Kubernetes

```bash
# Обновить образ (симуляция деплоя):
kubectl set image deployment/backend backend=bulletin-board-backend:v2 -n bulletin-board

# Наблюдать прогресс rolling update:
kubectl rollout status deployment/backend -n bulletin-board
```

```
Waiting for deployment "backend" rollout to finish: 1 out of 3 new replicas have been updated...
Waiting for deployment "backend" rollout to finish: 2 out of 3 new replicas have been updated...
deployment "backend" successfully rolled out
```

**История деплоев:**
```bash
kubectl rollout history deployment/backend -n bulletin-board
```

**Откат на предыдущую версию:**
```bash
kubectl rollout undo deployment/backend -n bulletin-board
```

---

## Шаг 11 — HPA (автомасштабирование)

```bash
# Включить metrics-server (нужен HPA для получения CPU-метрик):
minikube addons enable metrics-server

# Подождать 1-2 минуты пока metrics-server запустится
kubectl top pods -n bulletin-board

# Применить HPA:
kubectl apply -f k8s/backend/hpa.yml

# Посмотреть текущее состояние:
kubectl get hpa -n bulletin-board
```

**Запустить нагрузку:**
```bash
# Терминал 1: нагрузочный тест
k6 run ../level-2-scaling/load-tests/stress.js

# Терминал 2: наблюдать HPA
kubectl get hpa -n bulletin-board -w
kubectl get pods -n bulletin-board -w
```

**Что увидишь:**
```
NAME      REFERENCE             TARGETS   MINPODS   MAXPODS   REPLICAS
backend   Deployment/backend   23%/50%   3         10        3
backend   Deployment/backend   67%/50%   3         10        3        ← нагрузка выросла
backend   Deployment/backend   82%/50%   3         10        5        ← добавил 2 Pod
```

При снижении нагрузки — HPA уберёт лишние Pod обратно (scale down медленнее чем scale up — cooldown 5 минут).

---

## Шаг 11.5 — OOM Killer в Kubernetes

В Docker Compose OOM Kill — это `Exit 137` в `docker compose ps`. В Kubernetes это видно значительно лучше: у Pod появляется явный статус `OOMKilled`, счётчик рестартов растёт, и причина читается прямо в `kubectl describe`.

**Шаг 1 — Установить заниженный memory limit**

```bash
# Временно снизим лимит до 80Mi — при нагрузке этого не хватит
kubectl patch deployment backend -n bulletin-board --type='json' -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "80Mi"}
]'

# Проверяем что применилось:
kubectl get deployment backend -n bulletin-board \
  -o jsonpath='{.spec.template.spec.containers[0].resources.limits}{"\n"}'
# {"cpu":"500m","memory":"80Mi"}
```

**Шаг 2 — Открыть три терминала**

```bash
# Терминал 1: следим за Pod-ами
kubectl get pods -n bulletin-board -w

# Терминал 2: нагрузочный тест
k6 run ../level-2-scaling/load-tests/stress.js

# Терминал 3: держим наготове для диагностики
```

**Шаг 3 — Наблюдать OOMKilled**

В Терминале 1 рано или поздно увидишь:
```
backend-abc-xxx   1/1   Running        0   5m
backend-abc-xxx   0/1   OOMKilled      0   5m   ← память кончилась
backend-abc-xxx   0/1   CrashLoopBackOff  1   5m
backend-abc-xxx   1/1   Running        1   5m   ← пересоздался
```

Счётчик `RESTARTS` — это диагностический сигнал. В норме он 0. Растёт — что-то убивает Pod.

**Шаг 4 — Прочитать причину**

```bash
# Терминал 3 — имя Pod:
kubectl get pods -n bulletin-board

# Детальный разбор:
kubectl describe pod <имя-pod> -n bulletin-board

# В выводе ищи раздел "Last State":
# Last State:     Terminated
#   Reason:       OOMKilled     ← вот оно
#   Exit Code:    137
#   Finished:     Mon, 23 Jun 2026 12:34:56

# События namespace:
kubectl get events -n bulletin-board --sort-by=.lastTimestamp | tail -10
# Warning  OOMKilling  node/minikube  Memory cgroup out of memory: ...
```

**Шаг 5 — Сравнить Docker Compose vs Kubernetes**

| | Docker Compose | Kubernetes |
|---|---|---|
| Как видно | `Exit 137` в `docker ps` | Статус `OOMKilled` в `kubectl get pods` |
| Причина | Только через `dmesg` хоста | Прямо в `kubectl describe pod` |
| Счётчик рестартов | Нет | Да (`RESTARTS`) |
| Автоперезапуск | При `restart: unless-stopped` | Всегда |
| Мониторинг | Нужен внешний инструмент | Встроено в kube-state-metrics |

**Шаг 6 — Восстановить нормальный лимит**

```bash
kubectl patch deployment backend -n bulletin-board --type='json' -p='[
  {"op": "replace", "path": "/spec/template/spec/containers/0/resources/limits/memory", "value": "512Mi"}
]'

# Убедиться что новые Pod-ы без рестартов:
kubectl get pods -n bulletin-board
# RESTARTS: 0 у свежих Pod-ов
```

**Главный вывод:**

OOMKilled в K8s — не фатальная ошибка, Pod пересоздаётся. Но нарастающий `RESTARTS` — тревожный сигнал. В Level 6 мы добавим мониторинг на `kube_pod_container_status_restarts_total` и алерт когда `RESTARTS > 5 за 10 минут`.

---

## Шаг 12.5 — Blue-Green деплой в Kubernetes

### Аналогия

Театральная постановка. Главная сцена идёт спектакль (Blue — текущая версия). За кулисами на репетиционной сцене готовится новый (Green). Когда всё готово — переводишь зрителей в новый зал. Если что-то не так — возвращаешь мгновенно: старая сцена никуда не делась.

### Как это работает

```
Service (selector: color=blue)
          ↓ все запросы
[Pod blue-1] [Pod blue-2] [Pod blue-3]   ← v1, обслуживает трафик
[Pod green-1] [Pod green-2] [Pod green-3] ← v2, запущены, прогреты, без трафика

  kubectl patch service → selector: color=green
  ↓ атомарная операция, 0 потерянных запросов

Service (selector: color=green)
          ↓ все запросы
[Pod green-1] [Pod green-2] [Pod green-3] ← v2, теперь активен
[Pod blue-1] [Pod blue-2] [Pod blue-3]    ← v1, standby, откат = одна команда
```

Ключевой момент: переключение selector — атомарная операция kube-proxy. Запросы в полёте не теряются.

### Практика

**Шаг 1 — Создать манифесты**

```bash
mkdir -p level-5-kubernetes/k8s/blue-green
```

`level-5-kubernetes/k8s/blue-green/backend-blue.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-blue
  namespace: bulletin-board
spec:
  replicas: 3
  selector:
    matchLabels:
      app: backend
      color: blue
  template:
    metadata:
      labels:
        app: backend
        color: blue
        version: v1
    spec:
      containers:
        - name: backend
          image: bulletin-backend:v1
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```

`level-5-kubernetes/k8s/blue-green/backend-green.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-green
  namespace: bulletin-board
spec:
  replicas: 3
  selector:
    matchLabels:
      app: backend
      color: green
  template:
    metadata:
      labels:
        app: backend
        color: green
        version: v2
    spec:
      containers:
        - name: backend
          image: bulletin-backend:v2   # новая версия
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 5
            periodSeconds: 5
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```

`level-5-kubernetes/k8s/blue-green/service-active.yaml` — Service с переключаемым selector:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend-active
  namespace: bulletin-board
spec:
  selector:
    app: backend
    color: blue       # ← этот label переключаем при деплое
  ports:
    - port: 80
      targetPort: 8000
  type: ClusterIP
```

**Шаг 2 — Собрать две версии образа**

```bash
eval $(minikube docker-env)

# v1 — текущий образ
docker build -t bulletin-backend:v1 ./backend

# v2 — "новая версия" (для демонстрации: тот же образ с другим тегом)
docker tag bulletin-backend:v1 bulletin-backend:v2
# В реальности: здесь был бы собран образ с новым кодом
```

**Шаг 3 — Запустить Blue окружение**

```bash
kubectl apply -f k8s/blue-green/backend-blue.yaml
kubectl apply -f k8s/blue-green/service-active.yaml

# Ждём готовности:
kubectl rollout status deployment/backend-blue -n bulletin-board
# deployment "backend-blue" successfully rolled out

# Проверяем кто обслуживает:
kubectl get endpoints backend-active -n bulletin-board
# Endpoints: 10.x.x.x:8000,10.x.x.x:8000,10.x.x.x:8000  ← 3 Pod-а Blue
```

**Шаг 4 — Деплоить Green (без переключения)**

```bash
kubectl apply -f k8s/blue-green/backend-green.yaml

# Смотреть что поднимается
kubectl get pods -n bulletin-board -l app=backend

# NAME                          READY   STATUS    
# backend-blue-xxx-aaa          1/1     Running   ← активный
# backend-blue-xxx-bbb          1/1     Running
# backend-blue-xxx-ccc          1/1     Running
# backend-green-xxx-ddd         1/1     Running   ← прогревается, без трафика
# backend-green-xxx-eee         1/1     Running
# backend-green-xxx-fff         1/1     Running
```

Все Green Pod-ы `READY: 1/1` — readiness probe прошла, они готовы, но трафика нет.

**Шаг 5 — Переключить трафик на Green**

```bash
# Терминал 1: нагрузочный тест
k6 run level-5-kubernetes/load-tests/stress.js

# Терминал 2: переключение
kubectl patch service backend-active \
  -n bulletin-board \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/selector/color", "value": "green"}]'

# Убедиться что Endpoints обновились:
kubectl get endpoints backend-active -n bulletin-board
# Новые IP — это IP Pod-ов Green
```

**Что наблюдать:** в k6 — 0 ошибок в момент переключения.

**Шаг 6 — Мгновенный откат**

```bash
kubectl patch service backend-active \
  -n bulletin-board \
  --type='json' \
  -p='[{"op": "replace", "path": "/spec/selector/color", "value": "blue"}]'
# Blue Pod-ы всё время стояли живые — откат за <1 секунду
```

**Шаг 7 — Финализировать деплой**

```bash
# Масштабировать Blue до 0 — ресурсы освобождаются, откат ещё возможен:
kubectl scale deployment backend-blue --replicas=0 -n bulletin-board

# Когда уверен — удалить:
kubectl delete deployment backend-blue -n bulletin-board
```

### Что сломать намеренно

**Переключить на Green с unhealthy Pod-ами**

Измени image в `backend-green.yaml` на несуществующий (`bulletin-backend:broken`). Примени. Дождись пока все Green Pod-ы окажутся в `0/1` (readiness не проходит). Попробуй переключить Service.

```bash
kubectl get endpoints backend-active -n bulletin-board
# <none>  ← Endpoints пустые! Service указывает на color=green,
          # но все Green Pod-ы не прошли readiness
```

Это одно из преимуществ Kubernetes — даже после переключения selector, Pod-ы с неудавшимся readiness probe не получают трафик. Пользователи видят ошибки, но не из-за неисправного приложения — просто нет живых Pod-ов.

**Урок:** всегда проверяй `READY: 1/1` у всех Green Pod-ов **до** переключения Service.

---

## Шаг 12.8 — Canary деплой в Kubernetes

### Аналогия

Фармацевтическая компания выпускает новое лекарство. Сначала — клинические испытания на небольшой группе (5-20% пациентов). Мониторят побочные эффекты. Если всё хорошо — расширяют на всех. Если плохо — останавливают: пострадало немного, не все.

Canary deployment — та же логика для программных релизов.

### Как это работает (через пропорцию реплик)

```
Service (selector: app=backend) → выбирает ВСЕ Pod-ы с этим label

[stable: Pod1] [stable: Pod2] [stable: Pod3] [stable: Pod4]  ← 4 реплики, v1
[canary: Pod1]                                                 ← 1 реплика, v2

Round-robin по 5 Pod-ам: 4/5 = 80% stable, 1/5 = 20% canary
```

Это не точный контроль процентов — но для большинства задач достаточно. Для точного управления (nginx-ingress canary weight) — в конце этого шага.

### Практика

**Шаг 1 — Стабильная версия**

```bash
mkdir -p level-5-kubernetes/k8s/canary
```

`level-5-kubernetes/k8s/canary/backend-stable.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-stable
  namespace: bulletin-board
spec:
  replicas: 4            # ← 80% трафика при 1 canary
  selector:
    matchLabels:
      app: backend
      track: stable
  template:
    metadata:
      labels:
        app: backend     # ← Service выбирает по этому label
        track: stable
    spec:
      containers:
        - name: backend
          image: bulletin-backend:v1
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 5
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```

`level-5-kubernetes/k8s/canary/service-backend.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: backend
  namespace: bulletin-board
spec:
  selector:
    app: backend   # ← выбирает И stable, И canary Pod-ы
  ports:
    - port: 80
      targetPort: 8000
```

```bash
kubectl apply -f k8s/canary/backend-stable.yaml
kubectl apply -f k8s/canary/service-backend.yaml
kubectl rollout status deployment/backend-stable -n bulletin-board
```

**Шаг 2 — Выкатить Canary (20% трафика)**

`level-5-kubernetes/k8s/canary/backend-canary.yaml`:
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: backend-canary
  namespace: bulletin-board
spec:
  replicas: 1             # ← 1 из 5 Pod = 20% трафика
  selector:
    matchLabels:
      app: backend
      track: canary
  template:
    metadata:
      labels:
        app: backend      # ← тот же label → попадает в Service
        track: canary
    spec:
      containers:
        - name: backend
          image: bulletin-backend:v2   # новая версия
          ports:
            - containerPort: 8000
          readinessProbe:
            httpGet:
              path: /api/health
              port: 8000
            initialDelaySeconds: 5
          resources:
            requests:
              memory: "128Mi"
              cpu: "100m"
            limits:
              memory: "256Mi"
              cpu: "500m"
```

```bash
kubectl apply -f k8s/canary/backend-canary.yaml

kubectl get pods -n bulletin-board -l app=backend
# backend-stable-xxx   1/1   Running  (4 штуки) ← 80%
# backend-canary-xxx   1/1   Running  (1 штука) ← 20%
```

**Шаг 3 — Наблюдать распределение трафика**

```bash
# Запросить 10 раз, смотреть на какой Pod попадаем
# Примерно 8 ответов от stable, 2 от canary
for i in $(seq 1 10); do
  kubectl exec -n bulletin-board \
    $(kubectl get pod -n bulletin-board -l track=stable \
      -o jsonpath='{.items[0].metadata.name}') \
    -- wget -qO- http://backend/api/instance 2>/dev/null
  echo ""
done

# Следить за ошибками на canary отдельно:
kubectl logs -n bulletin-board -l track=canary -f
```

**Шаг 4 — Мониторить canary**

Пока канарейка работает — смотри:

```bash
# CPU и память canary Pod-а — не растёт ли аномально?
kubectl top pods -n bulletin-board -l track=canary

# Нет ли ошибок в логах?
kubectl logs -n bulletin-board -l track=canary --tail=20

# Сравнить RESTARTS: если у canary > 0 — что-то не так
kubectl get pods -n bulletin-board -l app=backend
```

В реальном проекте смотришь метрики в Grafana: error rate на canary Pod-ах должен быть не хуже чем на stable.

**Шаг 5a — Graduate (всё хорошо, выкатываем на 100%)**

```bash
# Обновить образ в stable (rolling update внутри stable Deployment):
kubectl set image deployment/backend-stable \
  backend=bulletin-backend:v2 \
  -n bulletin-board

kubectl rollout status deployment/backend-stable -n bulletin-board
# Waiting for deployment "backend-stable" rollout to finish: 1 out of 4 new replicas...
# ...
# deployment "backend-stable" successfully rolled out

# Удалить canary — его работа выполнена:
kubectl delete deployment backend-canary -n bulletin-board

# Итог: 4 Pod-а stable с v2
kubectl get pods -n bulletin-board -l app=backend
```

**Шаг 5b — Rollback (что-то не так с canary)**

```bash
# Просто удалить canary Deployment:
kubectl delete deployment backend-canary -n bulletin-board

# Stable так и остался на v1. Всё, что нужно было сделать — одна команда.
```

### Точный контроль процентов: nginx-ingress canary

Подход с репликами даёт приблизительный процент. В production для точного `weight=20%` используют nginx-ingress canary (сам Ingress и его контроллер разбираются на уровне 5.5):

```yaml
# Ingress для основного трафика (stable):
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: backend
  namespace: bulletin-board
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
                name: backend-stable-svc
                port:
                  number: 80
---
# Canary Ingress — отдельный объект с аннотациями:
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: backend-canary
  namespace: bulletin-board
  annotations:
    nginx.ingress.kubernetes.io/canary: "true"
    nginx.ingress.kubernetes.io/canary-weight: "20"   # ровно 20%
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
                name: backend-canary-svc
                port:
                  number: 80
```

Canary по заголовку — для QA-тестирования: конкретный пользователь всегда попадает на canary:
```yaml
nginx.ingress.kubernetes.io/canary-by-header: "X-Canary"
nginx.ingress.kubernetes.io/canary-by-header-value: "always"
```

```bash
# QA-инженер тестирует canary, не затрагивая обычных пользователей:
curl -H "X-Canary: always" http://bulletin-board.example.com/api/health
```

---

## Шаг 12 — Полезные kubectl команды

```bash
# Все ресурсы в namespace:
kubectl get all -n bulletin-board

# Логи нескольких Pod одновременно:
kubectl logs -f deployment/backend -n bulletin-board

# Зайти внутрь Pod:
kubectl exec -it <pod-name> -n bulletin-board -- bash

# Порт-форвард для прямого доступа (минуя Nginx):
kubectl port-forward svc/backend 8000:8000 -n bulletin-board

# Посмотреть события в namespace (что происходило):
kubectl get events -n bulletin-board --sort-by=.lastTimestamp

# Описание с Events (главное при диагностике):
kubectl describe pod <pod-name> -n bulletin-board

# Применить изменение и наблюдать rolling update:
kubectl rollout restart deployment/backend -n bulletin-board
kubectl rollout status deployment/backend -n bulletin-board
```

---

## Шаг 13 — Остановить minikube

```bash
# Остановить кластер (данные сохраняются):
minikube stop

# Удалить кластер полностью:
minikube delete
```

---

## Типичные ошибки

**"ImagePullBackOff"** → K8s не может скачать образ. Самая частая причина: забыл сделать `eval $(minikube docker-env)` перед сборкой образа. Или в манифесте опечатка в имени образа.

**"CrashLoopBackOff"** → Pod запускается и сразу падает. Смотри логи: `kubectl logs <pod-name> -n bulletin-board --previous`. `--previous` показывает логи предыдущего (упавшего) запуска.

**"Pending" Pod** → Нет ресурсов для размещения. `kubectl describe pod <pod-name>` покажет `Insufficient memory/cpu`. Увеличь `--memory` в `minikube start` или уменьши `requests` в манифесте.

**HPA показывает `<unknown>/50%`** → Не запущен metrics-server. Запусти `minikube addons enable metrics-server` и подожди 2 минуты.

**Secret в base64** → Kubernetes не шифрует секреты по умолчанию — только кодирует base64. Это НЕ безопасность. В production используй Sealed Secrets или External Secrets Operator.

---

## FAQ: база в кластере — Deployment, StatefulSet или вообще снаружи?

Это классический вопрос-ловушка на собеседованиях: «у вас Postgres в Deployment? а почему не StatefulSet?». Разберём честно.

**Почему у нас Deployment + PVC — и это ОК.** У нас одна реплика Postgres, и один PVC примонтирован к этому единственному Pod-у. При пересоздании Pod-а новый подключает тот же PVC — данные на месте. Все гарантии StatefulSet при `replicas: 1` ничего не добавляют, а манифест проще. Для учебного стенда и любых одиночных инстансов это нормальное решение.

**Когда нужен StatefulSet.** Он существует для рабочих нагрузок, где у реплик есть *личность*:
- **Stable network identity** — Pod-ы называются `postgres-0`, `postgres-1`, `postgres-2` и получают постоянные DNS-имена (через headless Service). Реплика №2 после пересоздания остаётся «№2». У Deployment Pod-ы безымянны и взаимозаменяемы (`backend-7f9b...-x2x4`).
- **Per-replica storage** — `volumeClaimTemplates` создаёт каждой реплике СВОЙ PVC. У Deployment все реплики делили бы один (а RWO-диск вообще не смонтируется на двух нодах).
- **Ordered rollout** — Pod-ы создаются и обновляются по порядку: 0 → 1 → 2, удаление в обратном.

Всё это критично, когда у базы репликация: primary (`postgres-0`) и standby (`postgres-1`) — это РАЗНЫЕ роли, их нельзя пересоздавать вслепую и в произвольном порядке. Итого: **несколько реплик stateful-сервиса → StatefulSet; одна реплика → достаточно Deployment + PVC**.

**Почему в проде базу часто выносят из кластера вообще.** Managed DB (RDS, Cloud SQL, Yandex Managed PostgreSQL) даёт бэкапы с point-in-time recovery, репликацию, failover и обновления версий — чужими руками и с SLA. Самостоятельно поднять это в кластере — недели работы и постоянная эксплуатационная нагрузка (поэтому если уж в кластере — то через операторы вроде CloudNativePG, а не голым StatefulSet). Кластер прекрасен для stateless-приложений: Pod-ы можно убивать и двигать. База — это ровно то, что убивать и двигать больно.

**Упражнение (опционально):** переведи Postgres на StatefulSet — `kind: StatefulSet`, добавь `serviceName: postgres`, замени PVC на `volumeClaimTemplates`, сделай Service headless (`clusterIP: None`). Затем удали Pod и сравни с Deployment: имя Pod-а сохранится (`postgres-0`), PVC будет называться `storage-postgres-0`, DNS-имя `postgres-0.postgres` — постоянное.

---

## На собеседовании спросят

**Q: Почему Postgres у вас Deployment, а не StatefulSet? Когда нужен StatefulSet?**
A: Одна реплика + один PVC — гарантии StatefulSet ничего не добавляют. StatefulSet нужен при нескольких stateful-репликах: стабильные имена/DNS (postgres-0, postgres-1), свой PVC на реплику (volumeClaimTemplates), упорядоченный rollout — без этого не построить репликацию primary/standby. В проде базу чаще выносят в managed DB (см. FAQ выше).

**Q: В чём разница между Pod, Deployment и ReplicaSet?**
A: Pod — один экземпляр приложения (1-2 контейнера). ReplicaSet — следит что работает N Pod. Deployment — управляет ReplicaSet, добавляет rolling update и история ревизий. В обычной работе работают только с Deployment, ReplicaSet и Pod создаются автоматически.

**Q: Что такое readiness probe и зачем она нужна?**
A: HTTP-запрос (или TCP, или команда) который K8s делает к Pod перед тем как направить на него трафик. Пока probe не пройдена — Pod в статусе `not ready` и Service не посылает на него запросы. Это решает проблему "трафик пришёл а приложение ещё не инициализировалось".

**Q: Что такое OOMKilled в Kubernetes и почему это не всегда катастрофа?**
A: OOMKilled — Pod превысил `resources.limits.memory`, ядро Linux отправило SIGKILL (exit code 137). Kubernetes автоматически пересоздаёт Pod. Это не катастрофа если происходит редко — плохо если `RESTARTS` растёт постоянно: значит лимит занижен или есть утечка памяти. В норме `RESTARTS: 0` у всех Pod-ов.

**Q: Как работает HPA?**
A: Раз в 15 секунд HPA запрашивает metrics-server, сравнивает текущее использование CPU/memory с целевым (`targetCPUUtilizationPercentage`). Если превышено — добавляет реплики (до `maxReplicas`). Scale down медленнее: ждёт 5 минут стабильно низкой нагрузки.

**Q: Зачем Namespace?**
A: Изолированное пространство имён внутри кластера. В одном кластере могут жить dev/staging/prod в разных namespace. Политики, RBAC, resource quotas применяются на уровне namespace. В нашем проекте `bulletin-board` — namespace для изоляции от других приложений.

**Q: Чем K8s Secret отличается от ConfigMap?**
A: ConfigMap — открытые данные (URL, порты, feature flags). Secret — чувствительные данные (пароли, токены). Технически Secret хранится в base64 (не зашифрован по умолчанию!) — разница больше семантическая и в access control (RBAC).

**Q: В чём разница Rolling Update, Blue-Green и Canary?**
A: Rolling: обновляет Pod-ы по одному, две версии работают одновременно, откат = новый деплой (медленно). Blue-Green: два полных окружения, переключение selector = мгновенный откат, удвоение ресурсов. Canary: малый процент трафика на новую версию, безопасное тестирование на реальных пользователях, градуальное увеличение.

**Q: Как реализовать Blue-Green в Kubernetes без платных инструментов?**
A: Два Deployment (backend-blue, backend-green). Service с selector `{app: backend, color: blue}`. При деплое: создаём green Deployment, ждём readiness, переключаем selector: `kubectl patch service`. Rollback: patch обратно на blue. Минута работы.

**Q: Как canary deployment защищает от инцидентов?**
A: При gradual rollout (canary replicas=1, stable=4) только 20% пользователей попадают на новую версию. Если новая версия деградирует — это видно на метриках canary Pod-ов до того как затронет всех. Rollback = `kubectl delete deployment backend-canary`. Без canary: инцидент затрагивает 100% сразу.

---

## Итог уровня 5 — что ты умеешь

- [ ] Запустить minikube и применить манифесты
- [ ] Объяснить Pod, Deployment, Service, ConfigMap, Secret
- [ ] Наблюдать self-healing: удалить Pod и увидеть автовосстановление
- [ ] Настроить readiness/liveness probe
- [ ] Включить HPA и наблюдать автомасштабирование под нагрузкой
- [ ] Откатить деплой через `kubectl rollout undo`
- [ ] Знать наизусть диагностические команды: describe, logs, events
- [ ] Реализовать Blue-Green деплой через selector на Service
- [ ] Реализовать Canary через пропорцию реплик и graduate/rollback

**Боль уровня 5:** нет видимости. Читать логи по Pod вручную — мучение. Нет графиков RPS/latency/error rate. Нет централизованных логов → Уровень 6: Prometheus + Grafana + Loki.

---

## Коммит

```bash
cd ..
git add level-5-kubernetes/
git commit -m "level-5: kubernetes manifests with hpa and probes"
git push origin main
```

---

## Security Block: Уровень 5

### Kubernetes — новая поверхность атаки

**1. Secrets НЕ зашифрованы по умолчанию**

Kubernetes Secret хранит данные в base64 — это кодирование, не шифрование. Любой кто имеет доступ к etcd (база данных кластера) читает все секреты в открытом виде.

```bash
# Так выглядит "секрет" в K8s:
kubectl get secret postgres-secret -n bulletin-board -o yaml
# data:
#   password: cGFzc3dvcmQxMjM=   ← это просто base64

# Декодируется за секунду:
echo "cGFzc3dvcmQxMjM=" | base64 -d
# password123
```

В production используй:
- **Sealed Secrets** — зашифрованные секреты которые можно коммитить в git
- **External Secrets Operator** — синхронизация из Vault/AWS Secrets Manager
- **Encryption at rest** — шифрование etcd (настройка на уровне кластера)

**2. Non-root контейнеры в K8s**

Dockerfile уже запускает от `appuser`. Но нужно закрепить это на уровне K8s:

```yaml
# deployment.yml — добавить securityContext:
spec:
  containers:
  - name: backend
    securityContext:
      runAsNonRoot: true          # K8s откажет если образ запускается от root
      runAsUser: 1001             # конкретный UID
      allowPrivilegeEscalation: false   # нельзя получить больше прав чем имеет процесс
      readOnlyRootFilesystem: true      # файловая система только для чтения
```

**3. Resource Limits — это и производительность, и безопасность**

Без `limits` один Pod может съесть всю CPU и RAM ноды. Это не только Performance проблема — это потенциальный вектор DoS изнутри кластера (или при компрометации Pod).

```yaml
resources:
  requests:
    cpu: "100m"     # 0.1 CPU — гарантировано
    memory: "128Mi"
  limits:
    cpu: "500m"     # 0.5 CPU — максимум
    memory: "512Mi" # при превышении — OOMKill
```

**4. NetworkPolicy — изоляция на сетевом уровне**

По умолчанию в K8s все Pod-ы могут общаться между собой. PostgreSQL доступен из любого Pod в кластере. NetworkPolicy ограничивает это:

```yaml
# Пример NetworkPolicy (для самостоятельного изучения):
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: postgres-allow-backend
  namespace: bulletin-board
spec:
  podSelector:
    matchLabels:
      app: postgres
  ingress:
  - from:
    - podSelector:
        matchLabels:
          app: backend   # только Pod-ы с этим label могут подключиться к postgres
    ports:
    - port: 5432
```

**5. RBAC — кто что может делать в кластере**

По умолчанию Pod использует `default` ServiceAccount с широкими правами. В production каждый сервис должен иметь свой ServiceAccount с минимальными правами.

⚠️ **Антипаттерны:**

- **Хранить пароли в ConfigMap** — ConfigMap не предназначен для секретов и не имеет ограничений доступа по умолчанию. Всё что конфиденциально — только в Secret.
- **Не устанавливать resource limits** — в production это приводит к `OOMKilled` на всей ноде при утечке памяти в одном Pod, что роняет весь сервис.

---

## Best Practices Checklist

- [ ] Все Pod-ы запущены от non-root пользователя — `kubectl exec ... -- whoami` не возвращает `root`
- [ ] Resource limits установлены для каждого контейнера
- [ ] readinessProbe и livenessProbe настроены — при убийстве Pod сервис не получает 502
- [ ] Секреты в K8s Secret, конфиги в ConfigMap — не перепутаны местами
- [ ] Namespace создан — все ресурсы приложения изолированы от default namespace
- [ ] HPA работает — под нагрузкой появились новые реплики
- [ ] Rolling update протестирован — `kubectl rollout undo` делает откат
- [ ] OOMKilled наблюдал вживую — знаешь как выглядит в `kubectl describe pod` и понимаешь exit code 137
- [ ] Blue-Green деплой выполнен: переключил selector и откатил обратно — понимаешь механизм
- [ ] Canary деплой выполнен: 20% трафика на v2, graduate или rollback — прошёл оба пути
- [ ] Можешь объяснить когда Blue-Green, а когда Canary, а когда Rolling

---

## Troubleshooting: Уровень 5

### Диагностика Kubernetes

Главное правило: **все ответы в `kubectl describe` и `kubectl logs`**.

**1. Pod в статусе `CrashLoopBackOff`**

Симптом: `kubectl get pods -n bulletin-board` показывает `CrashLoopBackOff`. K8s запускает Pod, он падает, K8s ждёт и перезапускает снова.

```bash
# Смотрим логи — там ошибка:
kubectl logs <pod-name> -n bulletin-board

# Если Pod уже упал и перезапустился — логи предыдущего запуска:
kubectl logs <pod-name> -n bulletin-board --previous

# Детальная информация с событиями:
kubectl describe pod <pod-name> -n bulletin-board
# Раздел "Events" — там хронология что происходило

# Частые причины CrashLoopBackOff:
# - Неверные переменные окружения (DATABASE_URL, SECRET_KEY)
# - PostgreSQL ещё не готов (race condition)
# - Ошибка в коде приложения при старте
# - OOMKilled — не хватает памяти

# Если OOMKilled — увеличь memory limit в deployment.yml:
kubectl describe pod <pod-name> -n bulletin-board | grep -A 3 "OOMKill"
```

**2. Pod в статусе `ImagePullBackOff`**

Симптом: Pod не запускается, статус `ImagePullBackOff` или `ErrImagePull`.

```bash
# Детали:
kubectl describe pod <pod-name> -n bulletin-board
# В Events: "Failed to pull image ... 404 Not Found"
# Или: "unauthorized: authentication required"

# Частые причины:
# 1. Опечатка в имени образа в deployment.yml
# 2. Образ собран в системном Docker, не в minikube Docker
# 3. Нет доступа к registry (нужен imagePullSecret)

# Для minikube — пересобери образ в правильном контексте:
eval $(minikube docker-env)
docker build -t bulletin-board-backend:latest level-3-caching/backend/
# Убедись что imagePullPolicy: Never или IfNotPresent в манифесте
```

**3. Pod в статусе `Pending`**

Симптом: Pod создан но не запускается, статус `Pending` долго.

```bash
# Детали почему не может запуститься:
kubectl describe pod <pod-name> -n bulletin-board
# В Events ищи:
# "Insufficient memory" — не хватает RAM на ноде
# "Insufficient cpu" — не хватает CPU
# "no nodes available" — нет подходящей ноды

# Для minikube — посмотреть ресурсы ноды:
kubectl describe node minikube | grep -A 10 "Allocated resources"

# Если не хватает ресурсов — увеличь minikube:
minikube stop
minikube start --memory=6144 --cpus=4

# Или уменьши requests в deployment.yml:
# resources.requests.memory: "64Mi"  (было 128Mi)
```

**4. HPA не масштабирует (показывает `<unknown>/50%`)**

Симптом: `kubectl get hpa -n bulletin-board` показывает `TARGETS: <unknown>/50%`.

```bash
# Причина: metrics-server не запущен
kubectl get pods -n kube-system | grep metrics

# Если нет — включить:
minikube addons enable metrics-server

# Подождать 2-3 минуты и проверить:
kubectl top pods -n bulletin-board
# Если ошибка "Metrics API not available" — metrics-server ещё стартует

# Когда заработает:
kubectl get hpa -n bulletin-board
# TARGETS: 23%/50% — нормально
```

**5. Service недоступен — `Connection refused`**

Симптом: `curl` к приложению не работает, хотя Pod-ы запущены.

```bash
# Проверяем что Service существует:
kubectl get svc -n bulletin-board

# Проверяем что endpoints есть (Pod-ы подключены к Service):
kubectl get endpoints -n bulletin-board
# Если endpoints пустой — label selector в Service не совпадает с label в Pod

# Детали Service:
kubectl describe svc backend -n bulletin-board
# Смотри "Selector" и сравни с labels в deployment.yml

# Проверка изнутри кластера:
kubectl run test-pod --image=curlimages/curl -it --rm -n bulletin-board -- curl http://backend:8000/api/health

# Для minikube — получить URL сервиса:
minikube service nginx -n bulletin-board --url
```

---

## Архитектура

- [Концепция: оркестрация контейнеров в вакууме](../docs/architecture/level-5-kubernetes/concept.html) — декларативное желаемое состояние и reconciliation loop
- [Реализация: реальные манифесты](../docs/architecture/level-5-kubernetes/implementation.html) — Deployments, Services, HPA namespace bulletin-board
- [Боль → решение: Level 4 → Level 5](../docs/architecture/level-5-kubernetes/pain-solution.html) — от ручного восстановления к self-healing и автомасштабированию
- [Сеть: путь запроса в кластере](../docs/architecture/level-5-kubernetes/network.html) — NodePort → kube-proxy → ClusterIP → Pod, резолв через CoreDNS

**Теория сетей глубже:**
- [Типы Service в Kubernetes](../docs/architecture/networking-theory/07-kubernetes-networking.html) — ClusterIP vs NodePort vs LoadBalancer, DNS в кластере

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
