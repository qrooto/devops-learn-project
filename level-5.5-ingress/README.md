# Уровень 5.5 — Ingress и cert-manager

> **Тип сессии:** разделы «Зачем», «Аналогия», «Как это работает», «На собеседовании спросят», Security Block — **[голова]**: можно читать в дороге, без терминала. Шаги с командами, «Что сломать намеренно», Troubleshooting на живой поломке — **[руки]**: нужна домашняя сессия с VM. Легенда — в START_HERE.md.

## Зачем это нужно

На уровне 5 наружу торчит NodePort: `http://$(minikube ip):30080`. Для учёбы сойдёт, но это «чёрный ход», а не вход:

- **Нестандартный порт.** Пользователи ходят на 80/443, а не на 30080 (диапазон NodePort — 30000-32767).
- **Один сервис = один порт.** Появится второй сайт/API — открывай ещё NodePort, и так на каждый сервис.
- **Нет маршрутизации.** Нельзя сказать «`api.example.com` → backend, `example.com` → frontend» — NodePort про порты, не про имена.
- **Нет TLS.** HTTPS пришлось бы терминировать в каждом сервисе отдельно.

В реальных кластерах вход — **Ingress**: единая точка на 80/443, которая по `Host` и `path` маршрутизирует к нужным Service. **Ingress-контроллер** (у нас ingress-nginx) — это исполнитель правил; сам ресурс `Ingress` — только описание.

**cert-manager** довешивает к этому автоматические TLS-сертификаты. Прямая параллель с уровнем 3.5: там Traefik сам получал сертификаты Let's Encrypt для docker-compose — здесь ingress-nginx + cert-manager делают ровно то же самое, но внутри кластера. Та же боль, тот же паттерн решения, другой инструмент.

## Аналогия

NodePort — служебные двери с номерами 30080, 30081… по периметру здания: работают, но гостям нужно знать номер конкретной двери. Ingress — ресепшн у главного входа: все заходят через одну дверь (80/443), называют кого ищут (`Host`-заголовок), и их провожают. cert-manager — сотрудник, который следит чтобы табличка «вход защищён» (сертификат) всегда была свежей, и сам её продлевает.

---

## Шаг 1 — Включить ingress-контроллер

```bash
# в minikube ingress-nginx ставится аддоном:
minikube addons enable ingress

# Дождись пока контроллер поднимется:
kubectl get pods -n ingress-nginx
# ingress-nginx-controller-...   1/1   Running
```

Убедись что приложение уровня 5 развёрнуто (`kubectl get pods -n bulletin-board` — всё Running). Если нет — сначала `kubectl apply -f ../level-5-kubernetes/k8s/ -R`.

---

## Шаг 2 — NodePort → ClusterIP

Раз внешний вход теперь через Ingress, nginx-сервису достаточно быть видимым внутри кластера:

```bash
cd level-5.5-ingress

kubectl apply -f k8s/nginx-service.yml

kubectl get svc nginx -n bulletin-board
# TYPE: ClusterIP, порта 30080 больше нет
```

🔒 Security: это принцип Default Deny в действии — снаружи доступна ровно одна точка (Ingress-контроллер), всё остальное закрыто. Меньше открытых портов = меньше поверхность атаки.

**Проверь боль:** `curl http://$(minikube ip):30080` — теперь отказ. Старый вход закрыт, новый ещё не открыт. Открываем.

---

## Шаг 3 — Ingress

```bash
kubectl apply -f k8s/ingress.yml

kubectl get ingress -n bulletin-board
# NAME             CLASS   HOSTS            ADDRESS        PORTS
# bulletin-board   nginx   bulletin.local   192.168.49.2   80
# ADDRESS может появиться не сразу (до минуты)
```

Ingress маршрутизирует по `Host`-заголовку, значит имя `bulletin.local` должно резолвиться в IP minikube. Пропиши локально:

```bash
echo "$(minikube ip) bulletin.local" | sudo tee -a /etc/hosts

curl http://bulletin.local/api/health
# и открой http://bulletin.local в браузере — доска работает, порт стандартный
```

**Задание для самопроверки:** объясни путь запроса: браузер → `/etc/hosts` → IP minikube:80 → ingress-nginx controller → (по Host) → Service nginx (ClusterIP) → Pod nginx → …

---

## Шаг 4 — cert-manager и TLS

```bash
# Установить cert-manager (CRD + контроллеры в namespace cert-manager):
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.16.2/cert-manager.yaml

kubectl get pods -n cert-manager
# cert-manager, cainjector, webhook — все Running (займёт ~минуту)

# Создать issuer-ы (кто выдаёт сертификаты):
kubectl apply -f k8s/cluster-issuers.yml
```

В `k8s/cluster-issuers.yml` два issuer-а — прочитай комментарии в файле:
- `selfsigned` — для локального minikube (Let's Encrypt не может достучаться до твоего ноутбука для проверки владения доменом);
- `letsencrypt-staging` — настоящий ACME-флоу, сработает только на сервере с публичным доменом. Это тот же процесс, что Traefik делал на уровне 3.5 — сравни `certresolver` там и `ClusterIssuer` здесь.

```bash
# Включаем TLS на Ingress (аннотация cert-manager.io/cluster-issuer + секция tls):
kubectl apply -f k8s/ingress-tls.yml

# cert-manager заметит аннотацию и создаст Certificate → CertificateRequest → Secret:
kubectl get certificate -n bulletin-board
# NAME                 READY   SECRET
# bulletin-local-tls   True    bulletin-local-tls

curl -k https://bulletin.local/api/health   # -k: сертификат self-signed, браузер ему не верит — это ожидаемо
```

**Что произошло:** ты не создавал ни ключа, ни сертификата — cert-manager выпустил их сам и положил в Secret, а ingress-nginx подхватил. Продление тоже автоматическое. На проде меняется одна строка — имя issuer-а.

---

## Что сломать намеренно

**1. Неправильный host**

```bash
# Поменяй в k8s/ingress-tls.yml host: bulletin.local на host: wrong.local, примени.
curl http://bulletin.local/
# 404 Not Found — и это 404 от nginx (ingress-контроллера), не от приложения!

# Диагностика — у контроллера есть default backend для неизвестных Host:
kubectl describe ingress bulletin-board -n bulletin-board   # смотри Rules: какой host обслуживается
kubectl logs -n ingress-nginx deployment/ingress-nginx-controller | tail -5
# в логе виден запрос с host=bulletin.local и ответ 404
```

Верни `bulletin.local` обратно. Запомни симптом: «404 на правильном URL» при работающих Pod-ах — первым делом сверь Host в Ingress.

**2. Убери ingressClassName**

```bash
# Закомментируй строку ingressClassName: nginx в k8s/ingress.yml, примени заново.
kubectl get ingress -n bulletin-board
# ADDRESS пустой и не появляется: ни один контроллер не считает этот Ingress своим

kubectl describe ingress bulletin-board -n bulletin-board
# Events: пусто — никто его даже не взял в работу. Это ключевая улика.
```

Ingress без класса — правила, у которых нет исполнителя. Верни строку, `ADDRESS` появится.

**3. Опечатка в имени Service**

```bash
# В k8s/ingress.yml поменяй name: nginx на name: nginxx, примени.
curl http://bulletin.local/
# 503 Service Temporarily Unavailable — контроллер не нашёл endpoints

kubectl describe ingress bulletin-board -n bulletin-board
# в Backends увидишь nginxx:80 (<error: service "nginxx" not found>)
```

Три поломки — три разных симптома (404 / нет ADDRESS / 503). Научись различать их: это сильно сужает поиск.

---

## Связь с другими уровнями

- **Уровень 3.5:** Traefik + Let's Encrypt для docker-compose — тот же паттерн «edge-прокси терминирует TLS и маршрутизирует», но на уровне контейнеров.
- **Уровень 7 (canary):** у ingress-nginx есть аннотации `nginx.ingress.kubernetes.io/canary: "true"` и `canary-weight` — canary-деплой можно делать на уровне Ingress, точнее чем трюк с репликами из уровня 7.
- **Уровень 8:** Ingress и ClusterIssuer — обычные манифесты, их место в Git под управлением ArgoCD.

---

## На собеседовании спросят

**Q: Чем Ingress отличается от Service типа LoadBalancer?**
A: LoadBalancer — L4 (TCP), один сервис = один внешний IP/балансировщик (в облаке — деньги). Ingress — L7 (HTTP): один вход на весь кластер, маршрутизация по Host/path, TLS-терминация. Обычно LoadBalancer один — перед ingress-контроллером.

**Q: Что будет если применить Ingress в кластере без ingress-контроллера?**
A: Ничего: ресурс создастся, но это только правила — исполнять их некому. ADDRESS останется пустым, трафик никуда не пойдёт. Частая ловушка.

**Q: Как cert-manager получает сертификат Let's Encrypt?**
A: ACME-протокол: cert-manager создаёт CertificateRequest, LE требует доказать владение доменом (HTTP-01: отдать файл по `http://домен/.well-known/acme-challenge/...`, или DNS-01: TXT-запись), cert-manager сам поднимает challenge через Ingress, LE проверяет и выдаёт сертификат, тот кладётся в Secret. Продление автоматическое.

**Q: Почему в проде начинают со staging-issuer?**
A: У прод Let's Encrypt жёсткие rate-limit-ы (например, 5 неудачных попыток в час). Отладка конфигурации на проде может заблокировать выдачу на часы. Staging безлимитный, но сертификаты «недоверенные» — отладился, переключил issuer.

---

## Итог уровня 5.5

Ты умеешь:
- Объяснить зачем Ingress и почему NodePort — не вход для пользователей
- Включить ingress-nginx и написать Ingress с маршрутизацией по Host
- Перевести сервис с NodePort на ClusterIP
- Поставить cert-manager, объяснить ClusterIssuer и ACME challenge
- Различать симптомы: 404 (host), пустой ADDRESS (class), 503 (backend)

---

## Коммит

```bash
cd ..
git add level-5.5-ingress/
git commit -m "level-5.5: ingress-nginx and cert-manager"
git push origin main
```

---

## Security Block: Уровень 5.5

**1. Одна точка входа (Default Deny)**

До: NodePort 30080 (+ по порту на каждый будущий сервис). После: наружу открыт только ingress-контроллер на 80/443, все Service — ClusterIP, изнутри кластера. Поверхность атаки минимальна и не растёт с числом сервисов.

**2. TLS-терминация в одном месте**

Сертификаты живут на границе (Ingress), приложениям не нужно знать про TLS вообще. Одно место для конфигурации — одно место для аудита и обновления протоколов/шифров.

**3. Автоматизация продления — это безопасность, не только удобство**

Просроченный сертификат = недоступный сервис и приученные к «нажми Продолжить» пользователи. cert-manager продлевает сам — человеческий фактор исключён.

⚠️ **Антипаттерны:**

- **Скопировать сертификат руками в Secret и забыть** — через 90 дней он истечёт молча. Риск: внезапный простой и MITM-привычки у пользователей.
- **Отлаживать выдачу сертификатов на прод-issuer Let's Encrypt** — упрёшься в rate-limit и заблокируешь себе выдачу на часы именно тогда, когда надо срочно. Сначала staging.

---

## Best Practices Checklist

- [ ] Все Service — ClusterIP; NodePort/LoadBalancer только там, где осознанно нужен
- [ ] В каждом Ingress указан `ingressClassName` — без него правила никто не исполнит
- [ ] TLS через cert-manager, не руками — продление автоматическое
- [ ] Отладка ACME — на staging-issuer, прод-issuer только после успеха
- [ ] Прошёл все три поломки и можешь по симптому (404 / пустой ADDRESS / 503) назвать причину

---

## Troubleshooting: Уровень 5.5

**1. Ingress создан, ADDRESS пустой**

```bash
kubectl get ingressclass                       # есть ли класс nginx вообще
kubectl get pods -n ingress-nginx              # жив ли контроллер
kubectl describe ingress <имя> -n <ns>         # Events пустые? — нет ingressClassName
```

**2. 404 от nginx на правильном URL**

Host в запросе не совпадает с host в правилах. `kubectl describe ingress` → Rules; `curl -H "Host: bulletin.local" http://$(minikube ip)/` — если так работает, проблема в DNS//etc/hosts, а не в Ingress.

**3. 503 Service Temporarily Unavailable**

Контроллер не нашёл живых endpoints: опечатка в имени/порте Service или Pod-ы не Ready. `kubectl describe ingress` (секция Backends) → `kubectl get endpoints <svc> -n <ns>` — пустые endpoints = смотри readinessProbe у Pod-ов.

**4. Certificate висит в READY: False**

```bash
kubectl describe certificate <имя> -n <ns>     # последнее событие — что не так
kubectl get certificaterequest,order,challenge -n <ns>   # где застряло по цепочке
kubectl logs -n cert-manager deployment/cert-manager | tail -20
```
Частое: challenge не проходит потому что домен не резолвится снаружи (локальный minikube + letsencrypt-issuer — см. комментарий в cluster-issuers.yml).

**5. Браузер ругается на сертификат**

Для `selfsigned` и `letsencrypt-staging` это норма — они не в доверенных корнях. Проверяй цепочку явно: `openssl s_client -connect bulletin.local:443 -servername bulletin.local </dev/null | head -20`. «Доверенный» замок даёт только прод Let's Encrypt на публичном домене.

---

## Архитектура

- [Концепция: Ingress в вакууме](../docs/architecture/level-5.5-ingress/concept.html) — ресурс-правила vs контроллер-исполнитель, маршрутизация по Host
- [Реализация: путь запроса через Ingress](../docs/architecture/level-5.5-ingress/network.html) — один вход :80/:443, TLS-терминация на границе, cert-manager
- [Боль → решение: Level 5 → Level 5.5](../docs/architecture/level-5.5-ingress/pain-solution.html) — от NodePort на каждый сервис к единой точке входа
- [Теория: ACME HTTP-01 challenge](../docs/architecture/networking-theory/10-acme-challenge.html) — как Let's Encrypt проверяет владение доменом
- [Теория: TLS handshake](../docs/architecture/networking-theory/06-tls-handshake.html) — что происходит до первого байта приложения

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
