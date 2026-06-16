# Уровень 10 — Ansible: управление конфигурацией

## Зачем это нужно?

К этому моменту ты умеешь поднимать инфраструктуру через Terraform, деплоить в Kubernetes, настраивать мониторинг. Но вся эта работа предполагает что VM уже готова: на ней стоит Docker, Python, нужные пакеты, настроены пользователи.

Когда серверов один или два — это делается вручную за полчаса. Когда их 10, 50, 100 — ручная настройка превращается в боль: медленно, неповторяемо, одна опечатка — и сервер настроен иначе остальных.

**Ansible** решает это: описываешь желаемое состояние в YAML, Ansible подключается по SSH и приводит серверы к нему. Без агентов на серверах. Без специального сервера управления. Только SSH + Python.

## Аналогия

Инструкция по сборке мебели IKEA — ты можешь собрать один шкаф следуя ей. Ansible — это роботизированный цех: та же инструкция, но теперь 50 роботов собирают 50 шкафов параллельно за то же время что ты один.

## Ключевые принципы

**Идемпотентность** — запусти плейбук 10 раз, результат тот же что после первого. Ansible перед каждым действием проверяет: "а вдруг уже сделано?" Если Docker уже установлен — не устанавливает снова.

**Декларативность** — описываешь ЧТО должно быть, не КАК этого достичь. Ты пишешь `docker: state=present`, а Ansible сам разберётся как установить Docker на Ubuntu vs CentOS.

**Agentless (без агентов)** — на управляемых серверах не нужно ничего дополнительно устанавливать. Ansible использует SSH (или WinRM на Windows).

## Архитектура

```
[Управляющая машина — твоя VM с Ansible]
        │
        ├── SSH → devops-vm-1 (192.168.1.100)  ← только Python нужен
        ├── SSH → devops-vm-2 (192.168.1.101)  ← только Python нужен
        └── ansible_connection=local → localhost (сам себя)
```

## Структура проекта

```
level-10-ansible/
├── ansible.cfg                  ← настройки: где инвентарь, какой user, timeout
├── inventory/
│   └── hosts.ini                ← список управляемых хостов
└── playbooks/
    ├── site.yml                 ← главный плейбук (всё сразу)
    ├── deploy.yml               ← только деплой приложения
    ├── check.yml                ← аудит состояния серверов
    └── roles/
        ├── common/              ← apt update, базовые пакеты, таймзона
        ├── docker/              ← Docker Engine из официального репозитория
        ├── tools/               ← k6, kubectl, helm
        └── app/                 ← git clone/pull + docker compose up
```

**Роль** — переиспользуемая единица. Вместо одного огромного плейбука на 500 строк — набор маленьких ролей, каждая делает одну вещь. Роль `docker` можно скопировать в любой другой проект.

---

## Шаг 1 — Установить Ansible

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install -y software-properties-common
sudo add-apt-repository --yes --update ppa:ansible/ansible
sudo apt install -y ansible

# Проверить:
ansible --version
# ansible [core 2.16.x]

# Установить коллекции (расширения — как плагины):
ansible-galaxy collection install community.general community.docker
```

**Зачем коллекции?**
Ansible — базовый движок. Коллекции расширяют его модулями:
- `community.docker` — модуль `docker_compose_v2` для управления compose-стеком
- `community.general` — `timezone`, `make`, сотни других утилит

---

## Шаг 2 — Изучить инвентарь

```bash
cd level-10-ansible

# Список всех хостов
ansible all --list-hosts

# Проверить соединение
ansible all -m ping
```

Открой `inventory/hosts.ini`:
```ini
[local]
localhost ansible_connection=local

[webservers]
# server1 ansible_host=192.168.1.100 ansible_user=ubuntu
```

**Задание:** Что значит `ansible_connection=local`? Почему для localhost не нужен SSH?
(Ответ: Ansible может управлять самим собой без SSH — выполняет команды напрямую в процессе.)

---

## Шаг 3 — Ad-hoc команды (без плейбука)

Ad-hoc — выполнить один модуль прямо из терминала. Полезно для диагностики:

```bash
# Пинг всех хостов
ansible all -m ping
# localhost | SUCCESS => {"ping": "pong"}

# Собрать всю информацию о хосте (факты)
ansible localhost -m setup | grep -A2 "ansible_mem"
# "ansible_memtotal_mb": 7982

# Выполнить shell-команду
ansible localhost -m command -a "uname -a"

# Установить пакет
ansible localhost -m apt -a "name=htop state=present" --become

# Создать файл
ansible localhost -m file -a "path=/tmp/ansible-test state=touch mode=0644"

# Скопировать контент в файл
ansible localhost -m copy -a "content='hello from ansible\n' dest=/tmp/hello"
cat /tmp/hello
```

**Что видишь в выводе:**
- `changed=1` — Ansible что-то изменил
- `ok=1` — уже было настроено, ничего не делал (идемпотентность)
- `failed=1` — ошибка

**Задание:** узнай через `setup` сколько ядер CPU на твоей VM (ищи `ansible_processor_vcpus`).

---

## Шаг 4 — Аудит состояния сервера

```bash
ansible-playbook playbooks/check.yml
```

**Что увидишь:**
```
TASK [Display OS info]
ok: [localhost] => {"msg": "Ubuntu 22.04 LTS (x86_64), 8192 MB RAM"}

TASK [Check Docker]
ok: [localhost] => {"msg": "Docker 24.x — installed"}

TASK [Check disk space]
ok: [localhost] => {"msg": "Disk /: 45% used (23G / 50G)"}
```

Это хороший шаблон для health-check всего флота серверов перед деплоем.

---

## Шаг 5 — Основной плейбук

```bash
# Dry run — показывает что ИЗМЕНИТСЯ, не применяя
# Обязательно запускай перед первым apply на prod!
ansible-playbook playbooks/site.yml --check

# Запустить только одну роль (по тегу):
ansible-playbook playbooks/site.yml --tags docker

# Запустить полностью:
ansible-playbook playbooks/site.yml
```

**Что произойдёт при полном запуске:**
1. **common** — `apt update`, установка `git curl wget htop vim`, настройка таймзоны
2. **docker** — добавление официального репозитория Docker, установка `docker-ce docker-ce-cli containerd.io`
3. **tools** — установка k6, kubectl, helm

**Запусти второй раз:**
```bash
ansible-playbook playbooks/site.yml
```

```
PLAY RECAP
localhost : ok=14  changed=0  unreachable=0  failed=0
```

`changed=0` — всё уже настроено, ничего не тронул. Это **идемпотентность** в действии.

**Почему это важно в production:**
- Можно запускать по расписанию — будет поддерживать конфигурацию
- Если кто-то вручную что-то сломал — следующий запуск починит
- Безопасно запускать повторно без страха "а вдруг что-то дважды выполнится"

---

## Шаг 6 — Деплой приложения

```bash
ansible-playbook playbooks/deploy.yml \
  -e "app_level=level-1-monolith" \
  -e "github_username=ВАШ_GITHUB_USERNAME" \
  -e "deploy_app=true"
```

**Что делает плейбук:**
1. Клонирует репозиторий (`git clone`) или обновляет (`git pull`) если уже есть
2. Запускает `docker compose up --build -d` в нужной папке

Проверь:
```bash
curl http://localhost/api/health
# {"status": "ok"}
```

**Задание:** Запусти деплой второй раз. Что показывает Ansible? Что происходит с уже запущенными контейнерами?

---

## Шаг 7 — Понять структуру роли

Открой роль `docker`:
```bash
ls playbooks/roles/docker/
# tasks/  handlers/  defaults/  meta/
```

```bash
cat playbooks/roles/docker/tasks/main.yml
```

**Структура роли:**
- `tasks/main.yml` — список задач
- `handlers/main.yml` — обработчики событий (например, рестарт сервиса после изменения конфига)
- `defaults/main.yml` — переменные по умолчанию
- `meta/main.yml` — зависимости от других ролей

**Handler** — специальная задача которая запускается только если была вызвана через `notify`. Используется для рестарта сервиса:
```yaml
# tasks/main.yml
- name: copy docker daemon config
  copy:
    src: daemon.json
    dest: /etc/docker/daemon.json
  notify: restart docker  # ← вызовет handler только если файл изменился

# handlers/main.yml
- name: restart docker
  service:
    name: docker
    state: restarted
```

Если файл не изменился — Docker не перезапустится. Идемпотентность работает и здесь.

---

## Шаг 8 — Ansible Vault (шифрование секретов)

Пароли в открытом виде в репозитории — критическая ошибка. Vault шифрует их:

```bash
# Создать зашифрованный файл:
ansible-vault create inventory/group_vars/all/vault.yml
# Vault введёт запрос пароля — запомни его!
```

Добавь в файл:
```yaml
vault_postgres_password: "SuperSecretPass123"
vault_jwt_secret: "my-production-secret-key"
```

```bash
# Посмотреть зашифрованный файл — это cipher text, не yaml:
cat inventory/group_vars/all/vault.yml
# $ANSIBLE_VAULT;1.1;AES256
# 62613263613161303830323...

# Запустить с расшифровкой:
ansible-playbook playbooks/site.yml --ask-vault-pass

# Или через файл с паролем (для CI/CD):
echo "my-vault-password" > ~/.vault_pass
chmod 600 ~/.vault_pass
ansible-playbook playbooks/site.yml --vault-password-file ~/.vault_pass
```

**В production:** пароль от vault хранится в CI/CD secrets (GitHub Actions → Settings → Secrets), а не в репозитории.

---

## Шаг 9 — Multi-server (если есть вторая VM)

Добавь в `inventory/hosts.ini`:
```ini
[webservers]
server1 ansible_host=192.168.1.100 ansible_user=ubuntu
server2 ansible_host=192.168.1.101 ansible_user=ubuntu
```

Скопируй SSH ключ на оба сервера:
```bash
ssh-copy-id ubuntu@192.168.1.100
ssh-copy-id ubuntu@192.168.1.101
```

Запусти:
```bash
ansible-playbook playbooks/site.yml
```

Ansible настроит оба сервера **параллельно** (по умолчанию 5 одновременно). Смотри в выводе: задачи выполняются на server1 и server2 одновременно.

---

## Типичные ошибки

**"UNREACHABLE — SSH refused"** → Проверь что SSH-ключ добавлен (`ssh-copy-id`), что пользователь правильный, что порт 22 открыт.

**"Missing sudo password"** → Добавь `-K` к команде или настрой passwordless sudo: `echo "ubuntu ALL=(ALL) NOPASSWD: ALL" | sudo tee /etc/sudoers.d/ubuntu`.

**"Module not found: docker_compose_v2"** → Не установлена коллекция. Запусти: `ansible-galaxy collection install community.docker`.

**Плейбук не идемпотентный** → Если каждый запуск показывает `changed=N` без реальных изменений — ты использовал `command`/`shell` вместо специализированного модуля (apt, copy, file). Модули умеют проверять текущее состояние, shell — нет.

**"Vault password is incorrect"** → Пароль Vault хранится только у тебя. Если забыл — нет способа восстановить, только пересоздать vault-файл.

---

## На собеседовании спросят

**Q: В чём разница Ansible и Terraform?**
A: Terraform создаёт инфраструктуру (VM, сети, storage в облаке). Ansible настраивает существующие серверы (устанавливает пакеты, разворачивает приложения). В реальных проектах используются вместе: Terraform создаёт VM, Ansible настраивает.

**Q: Что такое идемпотентность и почему она важна?**
A: Результат одинаков при любом количестве повторных запусков. Важно потому что в production нельзя рисковать: если что-то пошло не так и плейбук прервался на середине — можно запустить снова, он доделает остаток не ломая уже сделанное.

**Q: Чем отличается push-модель (Ansible) от pull-модели (Puppet/Chef)?**
A: Push: управляющая машина сама подключается к агентам и применяет конфигурацию. Pull: агент на сервере сам периодически обращается к серверу конфигурации за обновлениями. Push проще для старта, pull лучше масштабируется на тысячи серверов и самовосстанавливается.

**Q: Что такое handler в Ansible и когда он запускается?**
A: Handler — задача которая запускается только если другая задача вызвала `notify`. Классический пример: рестарт nginx только если изменился конфиг. Handlers запускаются в конце play, даже если notify был вызван несколько раз — handler выполнится один раз.

**Q: Как Ansible хранит состояние?**
A: Никак. В отличие от Terraform, Ansible не имеет state-файла. Он проверяет текущее состояние системы каждый раз при запуске. Это упрощает архитектуру, но означает что нельзя узнать "что Ansible изменял" без его повторного запуска.

---

## Итог уровня 0 — что ты умеешь

- [ ] Устанавливать Ansible и коллекции
- [ ] Писать инвентарь для одного и нескольких хостов
- [ ] Запускать ad-hoc команды для диагностики
- [ ] Писать плейбук с ролями и тегами
- [ ] Понимать идемпотентность на практике
- [ ] Деплоить приложение через Ansible
- [ ] Шифровать секреты через Vault
- [ ] Объяснить разницу Ansible vs Terraform

---

## Коммит

```bash
cd ..
git add level-10-ansible/
git commit -m "level-10: ansible playbooks for fleet provisioning and deployment"
git push origin main
```
