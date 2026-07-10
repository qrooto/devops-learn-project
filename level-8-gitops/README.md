# Уровень 8 — GitOps с ArgoCD

> **Тип сессии:** разделы «Зачем», «Аналогия», «Как это работает», «На собеседовании спросят», Security Block — **[голова]**: можно читать в дороге, без терминала. Шаги с командами, «Что сломать намеренно», Troubleshooting на живой поломке — **[руки]**: нужна домашняя сессия с VM. Легенда — в START_HERE.md.

## Зачем это нужно

До сих пор деплой работал так: пишем код → CI запускает `kubectl apply` или `helm upgrade`.
Проблемы этого подхода:
- Кластер может "дрейфовать" — кто-то изменил что-то вручную, и CI не знает об этом
- Нет единственного источника правды
- Нет автоматического обнаружения расхождений между Git и кластером

**GitOps** — подход где Git — единственный источник правды. Всё состояние системы хранится в Git. Изменение инфраструктуры = коммит в Git.

**ArgoCD** — GitOps-оператор для Kubernetes: следит за Git-репозиторием и синхронизирует кластер с тем что там написано.

## Аналогия

Представь повара (кластер) и рецептурную книгу (Git).

**Без GitOps:** повар работает, ты периодически заходишь и говоришь "добавь соли". Рецептурная книга устарела — не отражает что реально происходит на кухне.

**С GitOps:** рецептурная книга — закон. Если повар добавил что-то лишнее (ручное изменение) — ArgoCD это замечает и "выкидывает лишнее" (selfHeal: true). Изменить кухню можно только через книгу (коммит).

## Архитектура

```
Ты → git push → GitHub/GitLab
                     ↑ ArgoCD следит (polling каждые 3 мин или webhook)
                     ↓ обнаружил разницу
               ArgoCD применяет изменения
                     ↓
               Kubernetes кластер (minikube)
```

## GitOps vs традиционный CI/CD

| | Push-based CI/CD | Pull-based GitOps |
|--|--|--|
| Кто деплоит | CI runner (push) | ArgoCD в кластере (pull) |
| Доступ к K8s | CI нужны credentials | ArgoCD внутри кластера |
| Drift detection | Нет | Да, автоматически |
| Rollback | kubectl rollout undo | git revert → автосинк |
| Аудит | CI logs | Git history |

---

## Шаг 1 — Установить ArgoCD

```bash
cd level-8-gitops
chmod +x argocd/install-argocd.sh
bash argocd/install-argocd.sh
```

Скрипт установит ArgoCD в namespace `argocd`, подождёт готовности, выведет пароль и откроет port-forward.

---

## Шаг 2 — Войти в ArgoCD UI

Открой: **https://localhost:8443** (предупреждение о сертификате — нажми "Продолжить")

Логин: `admin`
Пароль: тот что вывел скрипт (или получи снова):
```bash
kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d && echo
```

---

## Шаг 3 — Зарегистрировать репозиторий

В ArgoCD UI → **Settings → Repositories → Connect Repo**:
- Repository URL: `https://github.com/твой_юзернейм/devops-project`
- Если приватный: добавь Username/Password или SSH key

Или через CLI:
```bash
# Логинимся в ArgoCD CLI
argocd login localhost:8443 --insecure --username admin --password <пароль>

# Добавляем репозиторий
argocd repo add https://github.com/твой_юзернейм/devops-project \
  --username твой_юзернейм \
  --password твой_токен_github
```

---

## Шаг 4 — Настроить Application

Открой `apps/bulletin-board-app.yml`, замени `YOUR_USERNAME` на свой GitHub username.

```bash
kubectl apply -f apps/bulletin-board-app.yml
```

ArgoCD начнёт синхронизацию. Открой UI → вкладка **Applications**. Увидишь приложение.

---

## Шаг 5 — Наблюдать первую синхронизацию

В UI нажми на приложение `bulletin-board`. Ты увидишь:
- **Граф ресурсов**: Deployment → ReplicaSet → Pod → Service — всё связано визуально
- **Статус**: Synced (совпадает с Git) или OutOfSync (расхождение)
- **Health**: Healthy / Progressing / Degraded

Статус каждого Pod, последние события — всё в одном месте.

---

## Шаг 6 — Изменить через Git (настоящий GitOps)

```bash
# Меняем количество реплик бэкенда
# Открой level-5-kubernetes/k8s/backend/deployment.yml
# Измени replicas: 3 на replicas: 5

git add level-5-kubernetes/k8s/backend/deployment.yml
git commit -m "scale backend to 5 replicas"
git push origin main
```

ArgoCD заметит изменение в течение 3 минут (или сразу при webhook). Наблюдай в UI как:
1. Статус меняется на **OutOfSync** (Git ≠ кластер)
2. ArgoCD применяет изменение
3. Статус возвращается в **Synced**

---

## Шаг 7 — Обнаружить ручное изменение (drift detection)

```bash
# Изменяем кластер ВРУЧНУЮ (в обход Git)
kubectl scale deployment backend -n bulletin-board --replicas=1
```

Через несколько секунд ArgoCD обнаружит расхождение (Drift!). Если включен `selfHeal: true` — сам восстановит до 5 реплик (как в Git). Если нет — покажет OutOfSync и потребует ручной синхронизации.

**Почему selfHeal важен:** ночью кто-то "быстро поправил" через kubectl. Утром никто не знает что кластер отличается от Git. Drift накапливается. Однажды деплой сломается потому что кластер "не тот".

---

## Шаг 8 — Rollback через git revert

```bash
# Откатываемся не через kubectl rollout undo,
# а через Git — как и должно быть в GitOps
git revert HEAD
git push origin main
```

ArgoCD применит предыдущее состояние. Rollback задокументирован в Git-истории.

---

## Как GitOps узнаёт о новом образе

Классическая грабля: в манифесте `image: backend:latest`, CI собрал новую версию и запушил её под тем же тегом. **Ничего не задеплоится.** ArgoCD сравнивает кластер с Git — а в Git ничего не изменилось: там всё тот же текст `backend:latest`. Kubernetes тоже не перекатит Pod-ы: спека Deployment не поменялась.

Отсюда правило: **тег образа должен быть иммутабельным** — один тег = один конкретный билд, навсегда. Обычно это git SHA (`backend:a1b2c3d`), который CI уже проставляет (см. `$CI_COMMIT_SHA` в level-4-gitlab).

Как тогда деплоится новая версия? **Обновлением тега коммитом в Git** — это и есть GitOps-путь:

```
CI: build → push backend:a1b2c3d
         → меняет тег в манифесте (sed/yq или helm values)
         → commit + push в Git
ArgoCD: видит diff в Git → синхронизирует → Pod-ы перекатываются
```

Такой коммит делает либо CI-джоба (обычно в отдельный «манифест-репозиторий» или отдельную папку), либо человек руками при ручном релизе. Бонусы: история деплоев = история Git, откат = `git revert`, всегда видно ЧТО именно (какой SHA) работает в кластере.

Обзорно: существует **ArgoCD Image Updater** — компонент, который сам следит за registry и коммитит новые теги в Git по правилам (semver, latest по дате). Полезно знать что он есть, но базовый путь — явное обновление тега через CI.

---

## На собеседовании спросят

**Q: В чём разница Push vs Pull deployment?**
A: Push (GitHub Actions, GitLab CI): CI-runner подключается к кластеру и применяет изменения. Pull (ArgoCD, Flux): оператор внутри кластера сам тянет изменения из Git.

**Q: Почему GitOps лучше для безопасности?**
A: CI-runner не нужен доступ к Kubernetes API — не надо хранить куб-конфиг в CI secrets. ArgoCD живёт внутри кластера, имеет ограниченный RBAC.

**Q: Что такое drift в Kubernetes?**
A: Расхождение между желаемым состоянием (Git/манифесты) и фактическим (кластер). Возникает от ручных изменений. ArgoCD это обнаруживает и исправляет.

**Q: Как ArgoCD обнаруживает изменения в Git?**
A: Polling (раз в 3 мин по умолчанию) или Webhook от GitHub/GitLab (мгновенно). В prod лучше webhook.

---

## Итог уровня 8

Ты умеешь:
- Установить и настроить ArgoCD
- Задеплоить приложение через GitOps
- Наблюдать drift detection
- Делать rollback через git revert
- Объяснить разницу Push/Pull CI-CD

---

## Коммит

```bash
cd ..
git add level-8-gitops/
git commit -m "level-8: gitops with argocd"
git push origin main
```

---

## Security Block: Уровень 8

### GitOps — безопаснее традиционного CI/CD

**1. Pull-модель: CI не нужен доступ к кластеру**

В классическом CI/CD: runner подключается к кластеру с помощью kubeconfig. Этот файл хранится в CI secrets и если CI скомпрометирован — атакующий получает доступ к кластеру.

В GitOps: ArgoCD живёт **внутри** кластера и сам тянет изменения из Git. CI вообще не знает про кластер — он только пушит код в репозиторий. Это принципиально безопаснее.

**2. RBAC для ArgoCD**

По умолчанию ArgoCD имеет широкие права. В production ограничь:
```yaml
# ArgoCD AppProject — ограничить что можно деплоить:
apiVersion: argoproj.io/v1alpha1
kind: AppProject
spec:
  destinations:
  - namespace: bulletin-board   # только в этот namespace
    server: https://kubernetes.default.svc
  sourceRepos:
  - 'https://github.com/твой_юзернейм/devops-project'  # только из этого репо
```

**3. Смена дефолтного пароля ArgoCD**

ArgoCD генерирует начальный пароль в Secret `argocd-initial-admin-secret`. После первого входа — немедленно меняй:
```bash
argocd account update-password \
  --current-password $(kubectl -n argocd get secret argocd-initial-admin-secret \
    -o jsonpath="{.data.password}" | base64 -d) \
  --new-password "YourStrongPassword123!"

# Удали начальный secret:
kubectl delete secret argocd-initial-admin-secret -n argocd
```

**4. selfHeal: true — это хорошо для безопасности**

Включённый selfHeal гарантирует что ручные изменения через kubectl не "застрянут" в кластере. Это значит несанкционированные изменения (ошибка, атака) будут автоматически откатаны через несколько минут.

**5. Git как аудит-лог**

Каждое изменение инфраструктуры = коммит с автором и временем. При инциденте легко ответить: "кто и когда изменил количество реплик".

⚠️ **Антипаттерны:**

- **Не менять дефолтный пароль ArgoCD** — `argocd-initial-admin-secret` с захардкоженным паролем это первое что проверяют при атаке на K8s-кластеры.
- **Открывать ArgoCD UI без TLS на публичный IP** — ArgoCD содержит полный доступ к управлению кластером. Всегда за VPN или с ограниченным доступом.

---

## Best Practices Checklist

- [ ] Пароль ArgoCD изменён с дефолтного
- [ ] `argocd-initial-admin-secret` удалён после смены пароля
- [ ] `selfHeal: true` включён — ручные изменения автоматически откатываются
- [ ] Drift detection протестирован: ручное изменение через kubectl → ArgoCD его откатил
- [ ] Rollback через `git revert` работает — ArgoCD применил предыдущее состояние
- [ ] ArgoCD доступен только локально (port-forward), не на публичном порту

---

## Troubleshooting: Уровень 8

### Проблемы с ArgoCD и GitOps

**1. Приложение в статусе `OutOfSync` и не синхронизируется**

```bash
# Детали расхождения:
argocd app diff bulletin-board

# Или в UI: Applications → bulletin-board → вкладка Diff
# Показывает что в Git vs что в кластере

# Принудительная синхронизация:
argocd app sync bulletin-board

# Если синхронизация зависла:
argocd app sync bulletin-board --force

# Смотрим события ArgoCD:
kubectl get events -n argocd --sort-by='.lastTimestamp' | tail -20
```

**2. `ComparisonError`: ArgoCD не может сравнить состояние**

```bash
# Смотрим статус приложения:
argocd app get bulletin-board

# Логи ArgoCD application controller:
kubectl logs -n argocd deployment/argocd-application-controller | grep -E "error|Error" | tail -20

# Частая причина: нет доступа к репозиторию
argocd repo list
# Если статус "Failed" — перепроверь credentials репозитория

# Обновить credentials:
argocd repo add https://github.com/user/repo --username user --password new_token
```

**3. Drift: ручное изменение не откатывается**

```bash
# Проверяем включён ли selfHeal:
kubectl get application bulletin-board -n argocd -o jsonpath='{.spec.syncPolicy}'

# Если не включён — включить:
argocd app set bulletin-board --self-heal

# Принудительно откатить до состояния Git:
argocd app sync bulletin-board --force --prune
```

**4. ArgoCD не видит новый коммит**

```bash
# ArgoCD polling — раз в 3 минуты по умолчанию
# Принудительно обновить:
argocd app refresh bulletin-board

# Проверить webhook (если настроен):
kubectl logs -n argocd deployment/argocd-server | grep webhook

# Статус репозитория:
argocd repo list
```

**5. Pod-ы не запускаются после синхронизации**

```bash
# ArgoCD применил манифесты, но Pod-ы падают
# Проверяем статус в K8s:
kubectl get pods -n bulletin-board
kubectl describe pod <имя-pod> -n bulletin-board

# ArgoCD покажет Health: Degraded если Pod-ы не ready
# В UI → приложение → дерево ресурсов → красные иконки

# Смотрим логи Pod:
kubectl logs <pod-name> -n bulletin-board --previous
```

---

## Архитектура

- [Концепция: push vs pull деплой в вакууме](../docs/architecture/level-8-gitops/concept.html) — где живут credentials и кто инициирует применение изменений
- [Реализация: реальный ArgoCD Application](../docs/architecture/level-8-gitops/implementation.html) — selfHeal, prune, polling/webhook
- [Боль → решение: Level 7 → Level 8](../docs/architecture/level-8-gitops/pain-solution.html) — от дрейфующего кластера к непрерывной сверке с Git

Сетевой схемы для этого уровня нет: ArgoCD работает внутри того же кластера и не открывает новый внешний сегмент — синхронизация с Git идёт исходящим запросом (egress), как и вызовы внешних API на Level 6.5 (см. [теорию про egress](../docs/architecture/networking-theory/08-webhooks-and-egress.html)).

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
