# Уровень 8 — GitOps с ArgoCD

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
