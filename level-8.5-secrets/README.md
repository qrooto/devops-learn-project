# Уровень 8.5 — Секреты в GitOps: Sealed Secrets

> **Это [руки]** — практический маршрут уровня. Нужна сессия с VM (minikube + ArgoCD с уровня 8).
> **Теория уровня — в `CURRICULUM.md` → «Уровень 8.5»**: противоречие GitOps и секретов, как работает асимметричное шифрование SealedSecret, альтернативы (SOPS, ESO), вопросы с собеседований. Легенда `[голова]`/`[руки]` — в START_HERE.md.

## Шаг 1 — Установить контроллер и kubeseal

```bash
cd level-8.5-secrets
chmod +x install-sealed-secrets.sh
bash install-sealed-secrets.sh
```

Скрипт: применит манифест контроллера в `kube-system`, дождётся готовности, установит CLI `kubeseal`.

Проверь:
```bash
kubectl get pods -n kube-system -l name=sealed-secrets-controller
# STATUS: Running

kubeseal --version
```

🔒 Security: приватный ключ пары лежит в Secret `sealed-secrets-key*` в `kube-system`. Кто имеет доступ к нему — может расшифровать ВСЕ SealedSecrets. Доступ к `kube-system` = доступ ко всем секретам, RBAC на этот namespace критичен.

---

## Шаг 2 — Запечатать postgres-secret

Берём существующий плейсхолдерный секрет уровня 5 и делаем из него настоящий:

```bash
# 1. Создай локальную копию с РЕАЛЬНЫМ паролем (файл не для Git!):
cp ../level-5-kubernetes/k8s/postgres/secret.yml /tmp/postgres-secret-real.yml
# Отредактируй /tmp/postgres-secret-real.yml — поставь настоящий пароль
# (не забудь поменять его и внутри DATABASE_URL)

# 2. Запечатай — kubeseal заберёт публичный ключ из кластера и зашифрует:
kubeseal --format yaml \
  < /tmp/postgres-secret-real.yml \
  > sealed/postgres-sealedsecret.yml

# 3. Посмотри что получилось:
cat sealed/postgres-sealedsecret.yml
# kind: SealedSecret, а в encryptedData — длинный шифротекст вместо пароля

# 4. Удали plain-text версию:
rm /tmp/postgres-secret-real.yml
```

Применяем и убеждаемся что контроллер развернул из него обычный Secret:

```bash
kubectl apply -f sealed/postgres-sealedsecret.yml

kubectl get sealedsecret,secret -n bulletin-board | grep postgres
# И SealedSecret, И созданный из него Secret

# Проверь что данные на месте (и заодно убедись насколько «надёжен» base64):
kubectl get secret postgres-secret -n bulletin-board \
  -o jsonpath='{.data.POSTGRES_PASSWORD}' | base64 -d && echo
```

---

## Шаг 3 — Через ArgoCD (настоящий GitOps-цикл)

Теперь тот же секрет — но через Git, как положено в GitOps:

```bash
# 1. Положи SealedSecret в папку которую синхронизирует ArgoCD,
#    а plain-text secret.yml оттуда убери:
git mv sealed/postgres-sealedsecret.yml ../level-5-kubernetes/k8s/postgres/sealedsecret.yml
git rm ../level-5-kubernetes/k8s/postgres/secret.yml

git commit -m "level-8.5: replace plain secret with sealedsecret"
git push origin main

# 2. Наблюдай в ArgoCD UI: OutOfSync → Synced.
#    Контроллер создаст Secret из SealedSecret — приложение продолжит работать.
kubectl get secret postgres-secret -n bulletin-board
```

**Что произошло:** в Git больше нет пароля — только шифротекст. ArgoCD спокойно синхронизирует его, контроллер в кластере разворачивает настоящий Secret. Противоречие «всё в Git vs секреты не в Git» снято.

> Если после этого упражнения захочешь чтобы level-5 снова запускался сам по себе (без контроллера) — верни как было: `git revert` последнего коммита. Факт что plain-secret вернулся в Git — нормален для учебного плейсхолдера, комментарий в самом файле это объясняет.

---

## Что сломать намеренно

**1. Разверни SealedSecret не в том namespace**

```bash
# Скопируй sealedsecret.yml, поменяй в нём metadata.namespace на default, примени:
kubectl apply -n default -f изменённый-файл.yml

kubectl get sealedsecret -n default
# STATUS: контроллер НЕ создаст Secret

kubectl logs -n kube-system -l name=sealed-secrets-controller | tail -5
# "no key could decrypt secret" — шифротекст привязан к namespace+имени.
```

Это не баг, а защита (strict scope): украденный из Git шифротекст нельзя развернуть в чужом namespace и прочитать.

**2. Удали контроллер**

```bash
kubectl delete deployment sealed-secrets-controller -n kube-system
kubectl apply -f sealed/postgres-sealedsecret.yml
kubectl get secret postgres-secret -n bulletin-board
# Secret не появляется: SealedSecret лежит, расшифровать некому.
# Диагностика: kubectl describe sealedsecret — нет событий, контроллера нет.
```

Восстанови контроллер повторным запуском `install-sealed-secrets.sh`.

**3. Потеряй приватный ключ (мысленный эксперимент — или на выброшенном кластере)**

`minikube delete` → новый кластер → новый контроллер сгенерирует **новую** пару ключей. Все старые SealedSecrets в Git превратились в мусор: расшифровать их больше нечем. Вывод: приватный ключ (`kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml`) нужно бэкапить в защищённое место — иначе disaster recovery невозможен.

---

## Альтернативы (обзорно)

| Подход | Где живёт секрет | Когда выбирать |
|---|---|---|
| **Sealed Secrets** | Зашифрованным в Git | Простой K8s-GitOps, один кластер, минимум инфраструктуры |
| **SOPS + age** | Зашифрованным в Git (любые файлы, не только K8s) | Нужно шифровать и tfvars/env-файлы; расшифровка на стороне CI или ArgoCD-плагина |
| **External Secrets Operator** | Во внешнем хранилище (Vault, cloud Secret Manager) | В Git — только ссылка (`ExternalSecret`); центральное управление, ротация, аудит |

**SOPS + age** в двух словах: `age-keygen` создаёт пару ключей, `sops -e secret.yml > secret.enc.yml` шифрует значения (структура YAML остаётся читаемой — видно КАКИЕ ключи есть, но не их значения — удобно для diff). Расшифровывает тот у кого приватный age-ключ. Не привязан к Kubernetes вообще.

**External Secrets Operator** в двух словах: секреты живут в Vault / Yandex Lockbox / AWS Secrets Manager. В Git кладут манифест `ExternalSecret` — «возьми из Vault ключ X и сделай Secret Y». Оператор синхронизирует. Плюс: ротация в одном месте, полный аудит доступа. Минус: нужно поднимать и защищать само хранилище.

Прогрессия по мере роста проекта обычно такая: Sealed Secrets → SOPS → External Secrets + Vault.

---

## Итог уровня 8.5

Ты умеешь:
- Объяснить почему base64 — не защита, а `stringData` — открытый текст
- Установить sealed-secrets контроллер и kubeseal
- Запечатать секрет и хранить его в Git не боясь утечки
- Прогнать секрет через полный GitOps-цикл с ArgoCD
- Диагностировать «no key could decrypt» и объяснить scope SealedSecret
- Сравнить Sealed Secrets / SOPS / External Secrets Operator

---

## Коммит

```bash
cd ..
git add level-8.5-secrets/
git commit -m "level-8.5: sealed secrets for gitops"
git push origin main
```

---

## Security Block: Уровень 8.5

**1. Секрет не должен существовать в открытом виде нигде, кроме кластера**

Весь путь секрета: создал plain-файл → запечатал → **удалил plain-файл** → в Git только шифротекст. Промежуточный `/tmp/postgres-secret-real.yml` — самое слабое звено, не забывай его удалять (и не создавай его в папке репозитория).

**2. Приватный ключ контроллера — новая точка отказа и новая цель атаки**

Шифрование не убирает секрет, а концентрирует риск в одном месте: ключ в `kube-system`. Отсюда два следствия: RBAC на `kube-system` — строгий; бэкап ключа — обязателен и хранится не в Git.

**3. История Git помнит всё**

Если пароль хоть раз был закоммичен открытым текстом — смена файла не помогает: он остаётся в истории. Правильная реакция: **сменить сам пароль**, а не переписывать историю (rewrite истории публичного репо — отдельная боль). Наш `postgres/postgres` — плейсхолдер, но правило запомни.

⚠️ **Антипаттерны:**

- **«Мы закодировали секреты в base64, всё безопасно»** — base64 декодируется одной командой; это сериализация, не защита. Риск: ложное чувство безопасности хуже честного plain-text.
- **Хранить бэкап приватного ключа контроллера в том же Git-репозитории** — обесценивает всю схему: у кого репо, у того и все секреты. Риск: полная компрометация при утечке репозитория.

---

## Best Practices Checklist

- [ ] В синхронизируемых ArgoCD папках нет plain-text Secret — только SealedSecret
- [ ] Промежуточные plain-файлы удалены (`/tmp/...`), не созданы внутри репо
- [ ] Приватный ключ контроллера забэкаплен вне Git
- [ ] Проверено: SealedSecret из чужого namespace не разворачивается (strict scope)
- [ ] `.env` и `values-local.yaml` в `.gitignore` — секреты уровней 1–7 тоже не в Git
- [ ] Можешь объяснить словами разницу base64 / шифрование и `data` / `stringData`

---

## Troubleshooting: Уровень 8.5

**1. SealedSecret применён, а Secret не появляется**

```bash
# Жив ли контроллер:
kubectl get pods -n kube-system -l name=sealed-secrets-controller

# События самого ресурса:
kubectl describe sealedsecret postgres-secret -n bulletin-board

# Логи контроллера — тут будет настоящая причина:
kubectl logs -n kube-system -l name=sealed-secrets-controller | tail -20
```

**2. `no key could decrypt secret`**

Шифротекст не подходит к ключу этого кластера. Причины: SealedSecret сделан для другого кластера; изменили namespace или имя после запечатывания; кластер пересоздан (новый ключ). Лечение: перезапечатать секрет заново под текущий кластер (`kubeseal` берёт актуальный публичный ключ).

**3. `kubeseal: cannot fetch certificate`**

```bash
# kubeseal ходит в кластер за публичным ключом — проверь доступ:
kubectl get svc -n kube-system sealed-secrets-controller
# Если контроллер в другом namespace/имя другое — укажи явно:
kubeseal --controller-namespace kube-system --controller-name sealed-secrets-controller ...
# Оффлайн-вариант: заранее выгрузить сертификат:
kubeseal --fetch-cert > pub-cert.pem   # затем: kubeseal --cert pub-cert.pem ...
```

**4. ArgoCD показывает Degraded на SealedSecret**

```bash
# ArgoCD не умеет оценивать health CRD из коробки — смотри статус ресурса:
kubectl get sealedsecret -n bulletin-board -o yaml | grep -A5 status
# Если Secret создан и приложение работает — это косметика;
# health-check для CRD настраивается в argocd-cm (resource.customizations).
```

**5. После `minikube delete` все SealedSecrets перестали работать**

Это ожидаемо: новый кластер = новый ключ (см. «сломай намеренно», п.3). Восстановление: либо восстановить старый ключ из бэкапа (`kubectl apply` секрета ключа в `kube-system` + перезапуск контроллера), либо перезапечатать все секреты заново.

---

## Архитектура

- [Концепция: путь секрета от plain-файла до кластера](../docs/architecture/level-8.5-secrets/concept.html) — kubeseal, публичный/приватный ключ, границы «твоя машина / Git / кластер»
- [Боль → решение: Level 8 → Level 8.5](../docs/architecture/level-8.5-secrets/pain-solution.html) — от пароля открытым текстом в Git к шифротексту

Сетевой схемы для этого уровня нет: новых сетевых сегментов не появляется — kubeseal ходит в кластер за публичным ключом тем же путём, что kubectl, а ArgoCD синхронизирует Git как на Level 8.

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
