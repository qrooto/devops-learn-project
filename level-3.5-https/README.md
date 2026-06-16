# Уровень 3.5 — HTTPS с Traefik и Let's Encrypt

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

## Коммит

```bash
cd ..
git add level-3.5-https/
git commit -m "level-3.5: https with traefik and let's encrypt"
git push origin main
```
