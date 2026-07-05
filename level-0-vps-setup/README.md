# Уровень 0 — Настройка нового VPS

## Зачем это нужно?

Каждый раз когда арендуешь сервер — он приходит в базовом состоянии: root-доступ по паролю, все порты открыты, нет защиты от брутфорса. В первые часы после создания сервера боты уже пытаются подобрать пароль к SSH.

Этот уровень — 15 минут работы которые защищают всё что будет построено дальше. Делается один раз.

**Среда:** Ubuntu 22.04 LTS

---

## Шаг 1 — Первый вход

Провайдер дал тебе IP-адрес и root-пароль. Подключись:

```bash
ssh root@<IP-адрес-сервера>
```

Первое что делаем — обновляем пакеты. На новом сервере они могут быть устаревшими на месяцы:

```bash
apt update && apt upgrade -y
```

**Что ты увидишь:** список обновляемых пакетов, потом `0 upgraded` (если свежий сервер) или список обновлений. Это нормально, жди завершения.

---

## Шаг 2 — Создать пользователя для работы

🔒 **Security:** никогда не работай от root постоянно. Если ошибёшься в команде — `rm -rf /` выполнится без вопросов. Если взломают — атакующий сразу получит root.

```bash
# Создаём пользователя (замени devops на своё имя)
adduser devops

# Добавляем его в группу sudo — может выполнять привилегированные команды через sudo
usermod -aG sudo devops

# Проверяем что пользователь создан:
id devops
# uid=1001(devops) gid=1001(devops) groups=1001(devops),27(sudo)
```

---

## Шаг 3 — Настроить SSH-ключи

SSH-ключи безопаснее паролей: пароль можно подобрать, ключ математически невозможно угадать при правильной длине.

**На своей локальной машине** (не на сервере!):

```bash
# Генерируем ключ типа Ed25519 — современный и быстрый
ssh-keygen -t ed25519 -C "my-vps" -f ~/.ssh/vps_key

# Будет два файла:
# ~/.ssh/vps_key      — приватный ключ (никому не показывай)
# ~/.ssh/vps_key.pub  — публичный ключ (можно передавать)

# Смотрим публичный ключ:
cat ~/.ssh/vps_key.pub
# ssh-ed25519 AAAAC3NzaC1lZDI1NTE5... my-vps
```

**На сервере** (всё ещё подключены как root):

```bash
# Переключаемся на нового пользователя
su - devops

# Создаём директорию для ключей
mkdir -p ~/.ssh
chmod 700 ~/.ssh

# Добавляем публичный ключ (скопируй содержимое vps_key.pub)
nano ~/.ssh/authorized_keys
# Вставь строку с публичным ключом, сохрани (Ctrl+O, Enter, Ctrl+X)

# Устанавливаем права
chmod 600 ~/.ssh/authorized_keys

# Возвращаемся к root
exit
```

**Проверяем что вход по ключу работает** — открой новый терминал на локальной машине:

```bash
ssh -i ~/.ssh/vps_key devops@<IP-адрес>
# Должен войти без запроса пароля
```

🔒 **Security:** не закрывай старый терминал с root пока не убедился что новый вход работает. Иначе рискуешь потерять доступ к серверу.

---

## Шаг 4 — Отключить вход по паролю

После того как убедился что вход по ключу работает — отключаем парольный вход. Теперь без ключа в SSH не попасть.

```bash
# На сервере (как root или через sudo):
sudo nano /etc/ssh/sshd_config
```

Найди и измени эти строки (или добавь если нет):

```
PermitRootLogin no           # запретить вход root по SSH
PasswordAuthentication no    # запретить парольный вход
PubkeyAuthentication yes     # разрешить только ключи
```

```bash
# Перезапускаем SSH-демон
sudo systemctl restart sshd

# Проверяем что SSH работает:
sudo systemctl status sshd
# Active: active (running)
```

**Задание:** не закрывая текущее соединение, открой ещё одно и попробуй зайти по паролю: `ssh devops@<IP>`. Должен получить `Permission denied (publickey)`.

---

## Шаг 5 — Настроить файрвол (UFW)

🔒 **Security:** принцип "запрещено всё что не разрешено". По умолчанию закрываем все порты, потом открываем только те что нужны.

```bash
# Проверяем текущее состояние
sudo ufw status
# Status: inactive — ещё не включён

# Устанавливаем политику по умолчанию: всё входящее — запрещено
sudo ufw default deny incoming

# Исходящие разрешены (сервер может подключаться к интернету)
sudo ufw default allow outgoing

# Разрешаем SSH — ОБЯЗАТЕЛЬНО перед включением UFW
# Иначе потеряешь доступ к серверу!
sudo ufw allow 22/tcp comment 'SSH'

# Разрешаем HTTP и HTTPS (нужны для нашего приложения)
sudo ufw allow 80/tcp comment 'HTTP'
sudo ufw allow 443/tcp comment 'HTTPS'

# Включаем UFW
sudo ufw enable
# Command may disrupt existing ssh connections. Proceed with operation (y|n)? y

# Проверяем:
sudo ufw status verbose
```

**Что увидишь:**
```
Status: active
Logging: on (low)
Default: deny (incoming), allow (outgoing)

To                         Action      From
--                         ------      ----
22/tcp                     ALLOW IN    Anywhere
80/tcp                     ALLOW IN    Anywhere
443/tcp                    ALLOW IN    Anywhere
```

---

## Шаг 6 — Установить fail2ban

fail2ban следит за логами SSH и блокирует IP-адреса которые слишком часто неправильно вводят пароль/ключ. Защита от брутфорса.

```bash
sudo apt install -y fail2ban

# Создаём локальный конфиг (никогда не редактируй jail.conf — он перезапишется при обновлении)
sudo nano /etc/fail2ban/jail.local
```

Содержимое файла:

```ini
[DEFAULT]
bantime  = 1h       ; блокируем на 1 час
findtime = 10m      ; если за 10 минут
maxretry = 5        ; больше 5 неудачных попыток

[sshd]
enabled = true
port    = ssh
logpath = /var/log/auth.log
```

```bash
sudo systemctl enable fail2ban
sudo systemctl start fail2ban

# Проверяем статус:
sudo fail2ban-client status
# Number of jail: 1
# Jail list: sshd

sudo fail2ban-client status sshd
# Status for the jail: sshd
# |- Filter
# |  `- Currently failed: 0
# `- Actions
#    `- Currently banned: 0
```

---

## Шаг 7 — Настроить автоматические security-обновления

Уязвимости в пакетах закрываются патчами. Без автообновлений сервер будет уязвим пока ты не обновишь руками.

```bash
sudo apt install -y unattended-upgrades

# Включаем автообновления:
sudo dpkg-reconfigure --priority=low unattended-upgrades
# Выбери "Yes"

# Проверяем конфиг:
cat /etc/apt/apt.conf.d/20auto-upgrades
# APT::Periodic::Update-Package-Lists "1";
# APT::Periodic::Unattended-Upgrade "1";
```

---

## Шаг 8 — Установить необходимые инструменты

```bash
# Базовые утилиты которые всегда нужны
sudo apt install -y \
  htop \          # удобный top
  curl \          # HTTP-запросы
  wget \          # скачивание файлов
  git \           # версионирование
  vim \           # редактор
  net-tools \     # netstat
  jq              # парсинг JSON в терминале
```

---

## Шаг 9 — Установить Docker

```bash
# Официальный способ установки Docker на Ubuntu:
curl -fsSL https://get.docker.com | sh

# Добавляем нашего пользователя в группу docker
# (чтобы не писать sudo перед каждой командой docker)
sudo usermod -aG docker devops

# ВАЖНО: перелогиниться чтобы изменение группы вступило в силу
exit
ssh -i ~/.ssh/vps_key devops@<IP>

# Проверяем:
docker run hello-world
# Hello from Docker!
```

---

## Шаг 10 — Итоговая проверка

```bash
# Права пользователя:
id
# должна быть группа docker и sudo

# UFW работает:
sudo ufw status

# fail2ban работает:
sudo fail2ban-client status

# SSH: вход root запрещён:
ssh root@<IP>
# Permission denied (publickey)

# Docker работает:
docker ps

# Открытые порты (должны быть только 22, 80, 443):
ss -tulpn | grep LISTEN
```

---

## Security Block: VPS Hardening

### Что мы сделали и зачем

| Действие | Принцип | Риск без этого |
|---|---|---|
| Создали отдельного пользователя | Least Privilege | Одна ошибка от root = уничтожение сервера |
| SSH-ключи вместо пароля | Defence in Depth | Пароль подбирается брутфорсом, ключ — нет |
| Отключили root по SSH | Least Privilege | Root — первый аккаунт который атакуют |
| UFW с default deny | Default Deny | Случайно открытый порт сразу доступен всему интернету |
| fail2ban | Defence in Depth | Без него боты делают тысячи попыток в час |
| Автообновления | Patch Management | Известные уязвимости остаются незакрытыми |

### Принцип Default Deny

Самая важная концепция в безопасности: **запрещено всё что явно не разрешено**, а не "разрешено всё что явно не запрещено".

Аналогия: охранник на входе с белым списком (кого пускать) vs охранник с чёрным списком (кого не пускать). Белый список — безопаснее: все кого нет в списке — не проходят автоматически.

### Принцип Least Privilege

Каждый пользователь и процесс имеет только те права которые нужны для конкретной задачи. Пользователь `devops` может выполнять sudo только при необходимости. Приложение в Docker запускается от пользователя без прав (об этом — на Уровне 1).

⚠️ **Антипаттерны:**

- **Работать постоянно от root** — когда скопируешь команду из интернета и в ней опечатка, root её выполнит без вопросов. Пользователь без прав — запросит подтверждение.
- **Оставить SSH открытым с паролем** — запусти `grep "Failed password" /var/log/auth.log | wc -l` на любом публичном сервере через 24 часа после создания. Увидишь сотни или тысячи попыток.

---

## Best Practices Checklist

После настройки сервера пройдись по списку:

- [ ] Пользователь не root, есть sudo — `id` показывает группу `sudo`
- [ ] SSH-ключи работают — вход без пароля
- [ ] Вход по паролю отключён — `PasswordAuthentication no` в sshd_config
- [ ] Вход root по SSH запрещён — `PermitRootLogin no`
- [ ] UFW включён и показывает три правила: 22, 80, 443
- [ ] fail2ban запущен — `sudo fail2ban-client status` без ошибок
- [ ] Автообновления включены — файл `/etc/apt/apt.conf.d/20auto-upgrades` существует
- [ ] Docker установлен и работает без sudo

---

## Troubleshooting: Базовая диагностика Linux

Эти команды используются на **любом** уровне при любых проблемах. Запомни их — они нужны всегда.

### CPU и нагрузка

```bash
top                    # живой список процессов с CPU/RAM
htop                   # удобнее top (цветная визуализация)
uptime                 # нагрузка за 1/5/15 минут (load average)
```

**Читать load average:** три числа — средняя нагрузка за 1, 5, 15 минут. Норма: меньше числа CPU-ядер. `nproc` покажет сколько ядер. Если load average 3.5 при 2 ядрах — сервер перегружен.

### Память

```bash
free -h                # занято / свободно / кэш
vmstat 1 5             # динамика памяти каждую секунду, 5 раз
```

**На что смотреть:** колонка `swap used` в `free`. Если swap активно используется — RAM не хватает, процессы начнут работать медленно.

### Диск

```bash
df -h                  # место на всех разделах
du -sh /var/log        # сколько занимают логи
du -sh /* 2>/dev/null  # что занимает место в /
iostat -x 1            # нагрузка на диск (нужен sysstat: apt install sysstat)
```

**На что смотреть:** `Use%` близко к 100% = диск заканчивается. Docker, базы данных и логи заполняют диск незаметно.

### Сеть и порты

```bash
ss -tulpn              # какие порты слушает сервер и какой процесс
curl -I localhost:80   # отвечает ли сервис локально
ping 8.8.8.8           # есть ли выход в интернет
```

**Если сервис не отвечает снаружи:** сначала проверь `ss -tulpn` — если порта нет, сервис не запущен. Если порт есть — проверь UFW: `sudo ufw status`.

### Процессы

```bash
ps aux                 # все запущенные процессы
ps aux | grep nginx    # запущен ли конкретный процесс
kill -9 <PID>          # принудительно завершить
lsof -i :80            # кто использует порт 80
```

### Системные логи

```bash
journalctl -f                              # живой поток всех системных логов
journalctl -u nginx --since "1 hour ago"   # логи конкретного сервиса
journalctl --priority=err                  # только ошибки
tail -f /var/log/syslog                    # системный лог (альтернатива)
grep "Failed" /var/log/auth.log            # неудачные попытки входа
```

### Типичные проблемы с доступом к серверу

**Не могу зайти по SSH:**
```bash
# 1. Проверь что SSH-демон запущен (нужен другой способ доступа — консоль провайдера):
systemctl status sshd

# 2. Проверь что порт 22 открыт в UFW:
sudo ufw status

# 3. Проверь authorized_keys:
cat ~/.ssh/authorized_keys
ls -la ~/.ssh/   # права должны быть: .ssh = 700, authorized_keys = 600
```

**UFW заблокировал собственный SSH:**
Войди через консоль провайдера (VNC/Console в панели управления).
```bash
sudo ufw allow 22
sudo ufw reload
```

**Диск 100%:**
```bash
# Найти что занимает место:
du -sh /* 2>/dev/null | sort -rh | head -10

# Почистить Docker мусор:
docker system prune -f

# Почистить старые логи:
sudo journalctl --vacuum-time=7d
```

---

## Архитектура

- [Концепция: VPS hardening в вакууме](../docs/architecture/level-0-vps-setup/concept.html) — default deny + ключи вместо паролей, без привязки к проекту
- [Реализация: что реально настроено на этом VPS](../docs/architecture/level-0-vps-setup/implementation.html) — ufw, sshd_config, fail2ban с конкретными правилами
- [Сеть: что видно снаружи VPS](../docs/architecture/level-0-vps-setup/network.html) — какие порты открыты, чем открытый-но-неслушающий порт отличается от заблокированного

**Теория сетей глубже** (общая, не привязана к проекту — пригодится за пределами этого репо):
- [IP, порт, сокет](../docs/architecture/networking-theory/01-ports-and-sockets.html) — что на самом деле определяет TCP-соединение
- [TCP-handshake и 3 исхода на firewall](../docs/architecture/networking-theory/02-tcp-handshake-and-firewall.html) — почему RST и тишина от firewall выглядят по-разному и как это использовать при диагностике

Диаграммы — самодостаточные `.html` файлы (переключатель тёмной/светлой темы, экспорт в PNG/SVG прямо в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
