# Уровень 3.5 — HTTPS с Traefik и Let's Encrypt

> **Тип сессии:** разделы «Зачем», «Аналогия», «Как это работает», «На собеседовании спросят», Security Block — **[голова]**: можно читать в дороге, без терминала. Шаги с командами, «Что сломать намеренно», Troubleshooting на живой поломке — **[руки]**: нужна домашняя сессия с VM. Легенда — в START_HERE.md.

## Зачем это нужно

До этого момента всё работало по HTTP — незашифрованному протоколу. Это значит:
- Логин и пароль передаются в открытом виде
- JWT-токен перехватывается при MITM-атаке
- Браузеры помечают такой сайт как "небезопасный"
- В 2025 году HTTP-only приложение воспринимается как нерабочее

**Let's Encrypt** — бесплатный центр сертификации, работает с 2015 года.
Выдаёт сертификаты автоматически через протокол ACME.

## Аналогия

HTTP — разговор в людном месте, все слышат.
HTTPS — разговор в звуконепроницаемой кабинке с проверенным собеседником.
TLS шифрует трафик и подтверждает что ты общаешься именно с тем сервером.

## Почему Traefik, а не Nginx + Certbot?

**Certbot + Nginx**: получить сертификат → настроить Nginx → написать cron для обновления → следить что не истёк.

**Traefik**: пишешь label в docker-compose, Traefik сам получает сертификат, сам обновляет за 30 дней до истечения, сам обновляет конфигурацию — без перезапуска.

В Kubernetes Traefik также работает как Ingress Controller — это делает его полезным на нескольких уровнях.

---

## Шаг 1 — Подготовка (требования)

Для Let's Encrypt нужен **реальный публичный домен** с A-записью, указывающей на IP твоей VM.

```
A  yourdomain.com → IP.вашей.VM
```

Для локального тестирования без домена используем self-signed сертификат:

```bash
cd level-3.5-https

# Генерируем self-signed сертификат (годен 365 дней)
mkdir -p certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout certs/key.pem \
  -out certs/cert.pem \
  -subj "/C=RU/ST=Moscow/L=Moscow/O=Dev/CN=localhost"

echo "Self-signed cert created"
ls -la certs/
```

> **Что такое self-signed?** Сертификат подписан сам собой, а не доверенным CA. Браузер предупредит "Небезопасно" но шифрование работает. В prod — только Let's Encrypt.

---

## Шаг 2 — Понять как Traefik Discovery работает

Traefik подключается к Docker socket (`/var/run/docker.sock`) и **автоматически обнаруживает** контейнеры с labels `traefik.enable=true`.

```
Запрос → Traefik :443
              читает labels у запущенных контейнеров
              находит: Host(`yourdomain.com`) && PathPrefix(`/api`) → backend:8000
              проксирует запрос
```

Открой `docker-compose.yml`, найди блок `labels:` у сервиса `backend`. Это и есть маршрутизация.

**Ключевые концепции Traefik:**
- **EntryPoint** — порт где Traefik слушает (80, 443)
- **Router** — правило "если запрос такой → отдай этому сервису"
- **Service** — сервис (контейнер) куда идёт трафик
- **Middleware** — преобразование запроса/ответа (редирект, auth, rate limit)

---

## Шаг 3 — Настроить домен (или localhost)

```bash
# Для реального домена — замени example.com в docker-compose.yml
sed -i 's/example.com/ТВОЙ_ДОМЕН/g' docker-compose.yml

# Также в traefik.yml замени email:
# email: your@email.com → твой реальный email

# Создай пустой acme.json (Traefik сохраняет сертификаты сюда)
touch certs/acme.json
chmod 600 certs/acme.json   # ОБЯЗАТЕЛЬНО — Let's Encrypt требует строгие права
```

---

## Шаг 4 — Запустить

```bash
docker compose up -d
docker compose logs -f traefik
```

**Что смотреть в логах Traefik:**
- `"Starting provider"` — Traefik стартовал
- `"Configuration loaded"` — обнаружил контейнеры
- `"Obtained certificate"` — получил сертификат от Let's Encrypt

---

## Шаг 5 — Traefik Dashboard

Открой: **http://localhost:8080**

Здесь видно:
- **Routers** — все маршруты (зелёный = активен, красный = ошибка)
- **Services** — бэкенд-сервисы и их статус
- **Middlewares** — настроенные преобразования

Это незаменимо при отладке — сразу видно применилось ли правило.

---

## Шаг 6 — Проверить HTTPS

```bash
# Для реального домена
curl -v https://ТВОЙ_ДОМЕН/api/health

# Для self-signed (игнорируем предупреждение)
curl -k https://localhost/api/health

# Проверить редирект HTTP → HTTPS
curl -v http://ТВОЙ_ДОМЕН/
# Должен вернуть 301 Moved Permanently → https://
```

---

## Шаг 7 — Понять автообновление сертификатов

Let's Encrypt выдаёт сертификаты на 90 дней. Traefik проверяет срок ежедневно и обновляет за 30 дней до истечения — автоматически, без перезапуска.

Проверить срок сертификата:
```bash
echo | openssl s_client -connect ТВОЙ_ДОМЕН:443 2>/dev/null | openssl x509 -noout -dates
```

---

## Последствия без HTTPS

| Без HTTPS | С HTTPS |
|-----------|---------|
| Пароли в открытом виде | Шифрование TLS |
| JWT перехватывается | Токены защищены |
| Браузер: "Небезопасно" | Замочек в адресной строке |
| SEO: пессимизация | SEO: бонус |
| Нарушение GDPR/152-ФЗ | Соответствие требованиям |

---

## На собеседовании спросят

**Q: Что такое TLS handshake?**
A: Процесс установки зашифрованного соединения: клиент и сервер обмениваются ключами, договариваются об алгоритме шифрования, сервер предъявляет сертификат.

**Q: Чем отличается симметричное и асимметричное шифрование в TLS?**
A: Handshake — асимметричное (RSA/ECDSA, медленное). Обмен данными — симметричное (AES, быстрое). Асимметричное используется только для безопасной передачи симметричного ключа.

**Q: Что делает Let's Encrypt при HTTP Challenge?**
A: Просит разместить файл по URL `http://domain/.well-known/acme-challenge/<token>`. Если файл доступен — значит у тебя контроль над доменом → выдаёт сертификат.

**Q: Что такое SNI?**
A: Server Name Indication — расширение TLS, позволяет серверу на одном IP держать сертификаты для нескольких доменов. Клиент в handshake говорит какой домен запрашивает.

---

## Типичные ошибки

- `chmod 600 certs/acme.json` забыли → Traefik не стартует
- Email не заменили в traefik.yml → Let's Encrypt не выдаёт сертификат
- Порт 80 занят (nginx от level-1) → остановить предыдущий compose
- Rate limit Let's Encrypt: 5 запросов на сертификат в неделю для одного домена → используй staging для тестов

---

## Security Block: Уровень 3.5 (HTTPS)

### TLS защищает канал, но появляются новые точки риска

**1. TLS termination и то, что происходит после**

Traefik расшифровывает трафик на границе VPS — дальше к backend/nginx он идёт обычным HTTP (см. network-схему уровня). Это безопасно только потому, что docker-сеть между Traefik и остальными сервисами недостижима снаружи VPS (см. Level 1).

**2. `acme.json` — это файл с приватными ключами**

`chmod 600 certs/acme.json` — не формальность: без этого права Traefik сам откажется стартовать. Файл содержит приватные ключи выданных сертификатов; если он читается кем угодно на сервере — скомпрометированы все домены, которыми управляет этот Traefik.

**3. ⚠️ Traefik Dashboard (Шаг 5) — сейчас поднят БЕЗ аутентификации**

`api.dashboard: true` + `insecure: true` в `traefik.yml`, порт `8080` published в `docker-compose.yml` — это значит, что дашборд со всеми роутами, сервисами и внутренней конфигурацией доступен любому, кто достучится до порта 8080, без пароля вообще. Для локальной учёбы это осознанный компромисс скорости, но **в production так оставлять нельзя**:
```bash
# Быстрая проверка прямо сейчас — открыт ли дашборд наружу VPS:
curl -I http://ТВОЙ_IP:8080
# Если отвечает 200 — дашборд публично доступен
```
Исправить: либо `sudo ufw deny 8080` (отключить внешний доступ совсем, смотреть дашборд только через `ssh -L 8080:localhost:8080`), либо включить `middlewares` с basic-auth перед dashboard-роутером, либо `insecure: false` + собственный TLS-защищённый роут с auth.

**4. Docker socket у Traefik — read-only, но это всё ещё информация обо всех контейнерах**

`/var/run/docker.sock:/var/run/docker.sock:ro` — Traefik читает лейблы контейнеров, чтобы строить маршруты автоматически. `:ro` не даёт ему управлять контейнерами, но даёт полную видимость того, что вообще запущено на хосте.

⚠️ **Антипаттерны:**

- **Оставить Traefik dashboard с `insecure: true` доступным из интернета в production** — раскрывает всю топологию маршрутизации, самый частый пример из этого самого уровня.
- **Закоммитить `certs/acme.json` в Git** — так же плохо, как закоммитить приватный SSH-ключ; добавь в `.gitignore` сразу.

---

## Best Practices Checklist

- [ ] `chmod 600 certs/acme.json` выполнен
- [ ] Email в `traefik.yml` заменён на реальный (Let's Encrypt использует его для уведомлений об истечении)
- [ ] HTTP → HTTPS редирект работает (`curl -v http://домен/` возвращает 301)
- [ ] Traefik dashboard закрыт от внешнего доступа (`ufw deny 8080` или auth-middleware) — не оставлен `insecure: true` наружу
- [ ] `certs/` добавлен в `.gitignore`, не закоммичен
- [ ] Понимаешь, где именно заканчивается шифрование (TLS termination) и что дальше трафик — plaintext внутри доверенной docker-сети

---

## Troubleshooting: Уровень 3.5 (HTTPS)

### Проблемы с TLS и Traefik

**1. Traefik не стартует вообще**

Симптом: `docker compose ps` показывает `traefik` в статусе `Exited`.

```bash
docker compose logs traefik | tail -30
ls -la certs/acme.json
```
Вероятная причина: права на `acme.json` не `600`, или файл не существует (создай пустым: `touch certs/acme.json && chmod 600 certs/acme.json`).

**2. Сертификат не выдаётся, роутер работает по HTTP**

Симптом: `https://домен` не открывается, только `http://`.

```bash
docker compose logs traefik | grep -i "acme\|certificate\|error"
```
Вероятная причина: email не заменён на реальный в `traefik.yml`, домен не резолвится на IP этого VPS (`dig домен +short` должен вернуть IP сервера), либо упёрлись в rate limit Let's Encrypt (5 сертификатов в неделю на домен — используй staging-окружение ACME для тестов).

**3. Порт 80 занят, Traefik не может его слушать**

Симптом: `Error starting userland proxy: listen tcp4 0.0.0.0:80: bind: address already in use`.

```bash
sudo ss -tulpn | grep :80
```
Вероятная причина: nginx с предыдущего уровня (Level 1-3) всё ещё запущен — останови его compose-стек перед стартом Traefik.

**4. Дашборд отвечает на 8080 снаружи VPS**

Симптом: `curl -I http://ТВОЙ_IP:8080` с другой машины возвращает `200 OK`.

```bash
sudo ufw status | grep 8080
```
Вероятная причина: порт 8080 published в docker-compose.yml и не заблокирован ufw — см. Security Block выше, это ожидаемо в дефолтной конфигурации, но требует ручного закрытия.

**5. Браузер ругается "Небезопасно" даже с валидным доменом**

Симптом: замочек перечёркнут, хотя сертификат должен быть от Let's Encrypt.

```bash
curl -vI https://домен 2>&1 | grep -i "issuer\|subject"
```
Вероятная причина: используется self-signed сертификат вместо Let's Encrypt (нет реального домена, см. Шаг 1), или закешированный старый сертификат в браузере — попробуй в приватном окне.

---

## Коммит

```bash
cd ..
git add level-3.5-https/
git commit -m "level-3.5: https with traefik and let's encrypt"
git push origin main
```

---

## Архитектура

- [Концепция: TLS termination в вакууме](../docs/architecture/level-3.5-https/concept.html) — где расшифровывается трафик и что происходит дальше
- [Реализация: реальный docker-compose.yml](../docs/architecture/level-3.5-https/implementation.html) — Traefik v3.2, ACME, docker-labels для роутинга
- [Боль → решение: Level 3 → Level 3.5](../docs/architecture/level-3.5-https/pain-solution.html) — было/стало/почему это работает
- [Сеть: TLS termination на границе VPS](../docs/architecture/level-3.5-https/network.html) — включая антипаттерн этого конфига (Traefik dashboard без аутентификации, published наружу)

**Теория сетей глубже:**
- [TLS 1.3 handshake](../docs/architecture/networking-theory/06-tls-handshake.html) — что происходит до первого байта приложения, почему SNI виден в открытую даже по HTTPS

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
