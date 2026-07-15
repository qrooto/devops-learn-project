# Уровень 9 — Terraform: Infrastructure as Code

> **Это [руки]** — практический маршрут уровня: команды, эксперименты, поломки. Нужна сессия с VM.
> **Теория уровня — в `CURRICULUM.md` → «Уровень 9»**: зачем IaC, анатомия main.tf/variables.tf/outputs.tf, что такое state, вопросы с собеседований. Здесь она не дублируется. Легенда `[голова]`/`[руки]` — в START_HERE.md.

## Шаг 1 — Установить Terraform

```bash
# Ubuntu/Debian
wget -O - https://apt.releases.hashicorp.com/gpg | sudo gpg --dearmor -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/hashicorp.list
sudo apt update && sudo apt install -y terraform

terraform version
```

---

## Шаг 2 — Изучить структуру

```
level-9-terraform/
└── environments/
    └── dev/
        ├── main.tf          ← ресурсы: сеть, PostgreSQL, бэкенд, Nginx
        ├── variables.tf     ← объявление переменных с типами и defaults
        ├── outputs.tf       ← что выводить после apply
        └── terraform.tfvars ← значения переменных для DEV
```

**Почему environments/dev/, а не просто terraform/?**
Потому что в реальности у тебя dev, staging, prod — разные конфигурации одного кода. Каждое окружение в отдельной папке со своими tfvars.

---

## Шаг 3 — Инициализировать

```bash
cd level-9-terraform/environments/dev

# Скачать провайдеры (как npm install для Terraform)
terraform init

# Что произошло:
# - скачан провайдер kreuzwerker/docker
# - создана папка .terraform/
# - создан .terraform.lock.hcl (фиксирует версии провайдеров)
ls -la .terraform/
```

---

## Шаг 4 — План (самое важное)

```bash
# Показывает что БУДЕТ создано/изменено/удалено — без применения
terraform plan

# Сохранить план в файл (для CI/CD: plan в PR, apply после approve)
terraform plan -out=tfplan
```

**Как читать вывод plan:**
- `+ resource` — будет создан (зелёный)
- `~ resource` — будет изменён (жёлтый)
- `- resource` — будет удалён (красный)
- `(known after apply)` — значение вычислится только после создания (например IP)

**В production**: plan запускается в CI на каждый PR, apply — только после код-ревью и апрува.

---

## Шаг 5 — Apply

```bash
# Применить план
terraform apply

# Или применить сохранённый план (точно то что ревьюили)
terraform apply tfplan
```

Terraform создаст Docker-сеть, запустит PostgreSQL, бэкенд, Nginx.

Проверь:
```bash
docker ps | grep dev-
curl http://localhost:8088/api/health
```

---

## Шаг 6 — Изменить инфраструктуру

Открой `terraform.tfvars`, поменяй порт:
```hcl
nginx_port = 9090
```

```bash
terraform plan    # Terraform покажет: ~ docker_container.nginx будет изменён
terraform apply   # Пересоздаст nginx-контейнер с новым портом
```

Обрати внимание: Terraform сам понимает что только nginx нужно изменить. PostgreSQL и бэкенд он не трогает.

---

## Шаг 7 — State

```bash
# Посмотреть все ресурсы в state
terraform state list

# Детали конкретного ресурса
terraform state show docker_container.postgres

# Экспортировать весь state (осторожно — там могут быть секреты)
terraform show
```

**Попробуй:** удали контейнер вручную:
```bash
docker rm -f dev-postgres
```

Теперь запусти:
```bash
terraform plan
```

Terraform обнаружит что ресурс исчез и предложит пересоздать. Это и есть декларативность — ты описываешь желаемое состояние, Terraform приводит к нему.

---

## Шаг 8 — Destroy

```bash
# Удалить ВСЁ что создал Terraform (по state файлу)
terraform destroy
```

Это полностью удалит всю инфраструктуру. В prod используется редко — обычно изменяют конфиг, а не уничтожают.

---

## Шаг 9 — Remote State: работа в команде

До сих пор `terraform.tfstate` лежит локально. Это нормально для одного человека. Как только в проекте два человека — начинается хаос:

- Коллега запустил `apply` → обновил свой `tfstate`
- Ты запустил `apply` со своей устаревшей копией → Terraform не знает что ресурс уже изменили → конфликт или двойное создание

И даже для одного: tfstate потерян при переезде на новый ноутбук → Terraform не знает что создал → при следующем `apply` попытается создать снова.

### Аналогия

Локальный state — это Google Doc на твоей машине. Remote state — это настоящий Google Doc в облаке. Все видят актуальную версию. Один пишет — другие ждут (state locking).

### Три компонента Remote State

```
S3 bucket (или аналог)   ← хранит terraform.tfstate
        +
DynamoDB table           ← locking: один apply за раз
        =
Terraform backend "s3"   ← конфигурация в main.tf
```

**State locking** — пока один `apply` выполняется, другой заблокирован. Без этого два параллельных `apply` повредят state.

### Практика

**Шаг 1 — Понять проблему без remote state**

```bash
cd level-9-terraform/environments/dev
terraform apply   # создаём инфраструктуру, tfstate на диске

# Симулируем работу коллеги — копируем директорию:
cp -r . /tmp/colleague-tf
cd /tmp/colleague-tf

# Коллега изменяет порт:
sed -i 's/nginx_port = 8088/nginx_port = 9090/' terraform.tfvars

# Коллега делает apply со СВОЕЙ устаревшей копией state:
terraform apply
# Terraform не знает о твоих изменениях — конфликт ресурсов

cd -  # возвращаемся
```

**Шаг 2 — Подготовить S3 bucket для state**

Для локальной практики используем MinIO (S3-совместимое хранилище):

```bash
# Запустить MinIO локально (S3-совместимый сервер):
docker run -d \
  --name minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e MINIO_ROOT_USER=minioadmin \
  -e MINIO_ROOT_PASSWORD=minioadmin \
  minio/minio server /data --console-address ":9001"

# Открыть MinIO Console: http://localhost:9001
# Логин: minioadmin / minioadmin

# Создать bucket через CLI:
docker run --rm --network host \
  -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 \
  minio/mc mb local/terraform-state

docker run --rm --network host \
  -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 \
  minio/mc ls local/
# [bucket] terraform-state
```

**Шаг 3 — Настроить backend в Terraform**

Открой `level-9-terraform/environments/dev/main.tf` и добавь:

```hcl
terraform {
  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }

  # Добавить backend для remote state:
  backend "s3" {
    endpoint                    = "http://localhost:9000"
    bucket                      = "terraform-state"
    key                         = "bulletin-board/dev/terraform.tfstate"
    region                      = "us-east-1"       # MinIO принимает любой регион
    access_key                  = "minioadmin"
    secret_key                  = "minioadmin"
    skip_credentials_validation = true               # MinIO не имеет STS
    skip_metadata_api_check     = true
    skip_region_validation      = true
    force_path_style            = true               # S3-style URL вместо subdomain
  }
}
```

**Шаг 4 — Мигрировать local state в remote**

```bash
# Переинициализировать с новым backend:
terraform init -migrate-state

# Terraform предложит:
# "Do you want to migrate your existing state to the new backend?"
# Введи: yes

# После миграции локальный tfstate больше не используется
ls -la
# terraform.tfstate        ← существует, но пустой (или его нет)

# Проверяем что state в MinIO:
docker run --rm --network host \
  -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 \
  minio/mc ls local/terraform-state/bulletin-board/dev/
# [2026-06-23 15:30] terraform.tfstate
```

**Шаг 5 — Наблюдать state locking**

```bash
# Терминал 1: запускаем apply (медленная операция):
terraform apply -auto-approve &

# Терминал 2: сразу же пробуем запустить второй apply:
terraform apply

# Увидишь:
# Error: Error acquiring the state lock
# Lock Info:
#   ID:        a1b2c3d4-...
#   Path:      terraform-state/bulletin-board/dev/terraform.tfstate
#   Operation: OperationTypeApply
#   Who:       user@machine
#   Created:   2026-06-23T15:30:00Z
#   Info:
```

Это и есть защита от параллельных apply. В настоящем S3 backend locking реализуется через DynamoDB.

**Шаг 6 — Production конфигурация**

В настоящем production (AWS):

```hcl
# main.tf — backend для AWS
terraform {
  backend "s3" {
    bucket         = "company-terraform-state"
    key            = "bulletin-board/prod/terraform.tfstate"
    region         = "eu-central-1"
    encrypt        = true                   # шифрование на стороне S3 (SSE-S3)
    dynamodb_table = "terraform-state-lock" # отдельная таблица для locking
  }
}
```

```bash
# Создать DynamoDB таблицу для locking (один раз):
aws dynamodb create-table \
  --table-name terraform-state-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region eu-central-1
```

Для Yandex Cloud (Object Storage + YDB):

```hcl
terraform {
  backend "s3" {
    endpoint   = "https://storage.yandexcloud.net"
    bucket     = "my-terraform-state"
    key        = "bulletin-board/dev/terraform.tfstate"
    region     = "ru-central1"
    # Credentials через переменные окружения:
    # export AWS_ACCESS_KEY_ID=...
    # export AWS_SECRET_ACCESS_KEY=...
    skip_credentials_validation = true
    skip_metadata_api_check     = true
    force_path_style            = true
  }
}
```

**Шаг 7 — Что хранится в state (и почему это опасно)**

```bash
# Посмотреть содержимое remote state:
terraform show

# Или напрямую из MinIO:
docker run --rm --network host \
  -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 \
  minio/mc cat local/terraform-state/bulletin-board/dev/terraform.tfstate | python3 -m json.tool | head -50
```

В выводе увидишь **все атрибуты ресурсов в открытом виде** — включая пароли PostgreSQL, токены, connection strings. Именно поэтому:
- State никогда не в Git
- S3 bucket для state — с `encrypt=true` и закрытый (не публичный)
- Доступ к bucket — только для CI/CD сервисного аккаунта и конкретных людей

**Остановить MinIO:**

```bash
docker stop minio && docker rm minio
```

---

## Что сломать намеренно — Уровень 9

**Поломка 1 — Потерять state**

```bash
mv terraform.tfstate terraform.tfstate.backup
terraform plan
# Terraform думает что ничего не создано и хочет создать всё заново!
# В облаке это означает дублирование ресурсов и лишние деньги;
# здесь — вторую копию контейнеров с теми же именами, apply упадёт на конфликте имён

mv terraform.tfstate.backup terraform.tfstate
```

**Поломка 2 — Изменить ресурс вручную мимо Terraform**

```bash
# Останови и запусти nginx-контейнер с другим портом напрямую через Docker, в обход Terraform:
docker stop dev-nginx
docker rm dev-nginx
docker run -d --name dev-nginx --network dev-bulletin-board -p 9999:80 nginx:alpine
```
Запусти `terraform plan`. Увидишь drift — Terraform обнаружит, что реальный контейнер не соответствует тому, что описано в `.tf` файлах, и предложит пересоздать его в исходном виде (порт из `terraform.tfvars`, а не 9999). Если применить — Terraform вернёт всё к состоянию из кода, ручное изменение будет потеряно. Именно так же ведёт себя `digitalocean_droplet` или любой другой облачный ресурс, изменённый в консоли мимо Terraform.

---

## Справочник команд — Уровень 9

| Команда | Описание |
|---------|---------|
| `terraform init` | Инициализация: скачать провайдеры |
| `terraform plan` | Что изменится? (dry run) |
| `terraform apply` | Применить изменения |
| `terraform destroy` | Удалить всё (осторожно!) |
| `terraform state list` | Список ресурсов в state |
| `terraform state show <resource>` | Детали ресурса в state |
| `terraform state rm <resource>` | Удалить ресурс из state (без уничтожения) |
| `terraform import <type>.<name> <id>` | Импортировать существующий ресурс |
| `terraform init -migrate-state` | Переехать на новый backend |
| `terraform force-unlock <ID>` | Снять зависший lock |
| `terraform validate` | Проверить синтаксис .tf файлов |
| `terraform fmt` | Автоформатирование кода |

---

## Типичные ошибки

- **Коммит terraform.tfstate в Git**: содержит пароли и ключи. Добавь в .gitignore.
- **Ручное изменение ресурсов**: Terraform не знает о ручных изменениях → state расходится → план покажет "удалить и пересоздать".
- **terraform destroy в prod**: уничтожает всё. Всегда читай план перед apply.
- **Нет locking на remote state**: два человека запустили apply одновременно → конфликт → повреждённый state.

---

## .gitignore для Terraform

```gitignore
# Добавь в корневой .gitignore:
**/.terraform/
**/terraform.tfstate
**/terraform.tfstate.backup
**/.terraform.lock.hcl  # спорно — некоторые коммитят для воспроизводимости
**/tfplan
**/*.tfvars             # если содержат секреты
```

---

## Коммит

```bash
cd ../..
git add level-9-terraform/
git commit -m "level-9: terraform infrastructure as code"
git push origin main
```

---

## Security Block: Уровень 9

### State файл — главная security-угроза в Terraform

**1. `terraform.tfstate` никогда не в Git**

State файл содержит все значения ресурсов в открытом виде: пароли PostgreSQL, токены, ключи доступа к облаку. Если он попадёт в публичный репозиторий — это немедленная компрометация.

Добавь в `.gitignore` (уже должно быть в корневом):
```
**/.terraform/
**/terraform.tfstate
**/terraform.tfstate.backup
**/terraform.tfvars    # если содержит секреты
```

**2. Remote state с шифрованием**

В production state хранится в облачном хранилище с шифрованием и блокировкой:
```hcl
terraform {
  backend "s3" {
    bucket         = "terraform-state-prod"
    key            = "bulletin-board/terraform.tfstate"
    region         = "eu-central-1"
    encrypt        = true              # шифрование на стороне S3
    dynamodb_table = "terraform-lock"  # блокировка от параллельного apply
  }
}
```

Без блокировки два человека могут одновременно запустить `apply` → поврежденный state.

**3. Credentials не в коде**

Никогда не хардкодить access_key/secret_key в `.tf` файлах:
```hcl
# ПЛОХО:
provider "aws" {
  access_key = "AKIAIOSFODNN7EXAMPLE"
  secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}

# ХОРОШО — через переменные окружения:
# export AWS_ACCESS_KEY_ID="..."
# export AWS_SECRET_ACCESS_KEY="..."
provider "aws" {}  # Terraform сам подхватит из env
```

**4. `terraform plan` перед `apply` — всегда**

Plan показывает что изменится. В production план сохраняется в файл и применяется именно он:
```bash
terraform plan -out=tfplan     # сохраняем план
terraform show tfplan          # просматриваем что будет сделано
terraform apply tfplan         # применяем точно этот план
```

Это гарантирует что между plan и apply ничего не изменилось.

**5. Принцип минимальных прав для Terraform**

Сервисный аккаунт для Terraform должен иметь права только на нужные ресурсы. Не `AdministratorAccess` — только конкретные разрешения на создание EC2, VPC, RDS.

⚠️ **Антипаттерны:**

- **Коммит `terraform.tfstate` в Git** — даже если репозиторий приватный. Настройки доступа могут измениться, члены команды меняются. State = секреты = не в git.
- **`terraform destroy` без `plan` в production** — это удаляет ВСЁ что в state. Удаление базы данных с данными — необратимо. Всегда: `plan → review → apply`.

---

## Best Practices Checklist

- [ ] `terraform.tfstate` в `.gitignore` — `git status` не показывает его — секреты не должны попасть в историю
- [ ] Credentials не в `.tf` файлах — через переменные окружения или Vault
- [ ] Команда `terraform plan` запускается перед каждым `apply` — surprise-free деплой
- [ ] `terraform validate` проходит без ошибок — базовая проверка синтаксиса
- [ ] Remote state настроен с locking — MinIO локально или S3+DynamoDB в production
- [ ] `terraform.tfvars` с секретами в `.gitignore`
- [ ] Понимаешь разницу `terraform import` vs `terraform state rm` — как работать с ресурсами вне Terraform
- [ ] `encrypt = true` в backend конфигурации — state содержит secrets, шифрование обязательно

---

## Troubleshooting: Уровень 9

### Проблемы с Terraform

**1. `Error: state lock` — state заблокирован**

Симптом: `Error acquiring the state lock: ConditionalCheckFailedException`.

```bash
# Случается если предыдущий apply упал незавершённым
# Посмотреть кто держит блокировку:
terraform force-unlock <LOCK_ID>
# LOCK_ID есть в тексте ошибки

# В DynamoDB можно посмотреть:
# aws dynamodb scan --table-name terraform-lock
```

**2. State расходится с реальностью**

Симптом: `terraform plan` предлагает удалить ресурс который существует, или создать который уже есть.

```bash
# Обновить state из реального состояния:
terraform refresh

# Если ресурс создан вне Terraform — импортировать его:
terraform import docker_container.postgres dev-postgres

# Если ресурс удалён вне Terraform — убрать из state:
terraform state rm docker_container.postgres
```

**3. `Error: Provider configuration not present`**

```bash
# Terraform потерял провайдер — переинициализировать:
terraform init

# Если директория .terraform повреждена:
rm -rf .terraform .terraform.lock.hcl
terraform init
```

**4. `plan` показывает неожиданные изменения**

Симптом: запускаешь plan — он предлагает пересоздать ресурс который не трогал.

```bash
# Смотрим детальный diff:
terraform plan -detailed-exitcode

# Причина часто в изменении аргументов провайдера или версии
# Смотрим что конкретно изменится:
terraform plan | grep -A 5 "must be replaced"

# Проверяем версию провайдера:
terraform version
cat .terraform.lock.hcl | grep version
```

**5. `apply` упал на середине**

```bash
# Terraform частично применил изменения — state может быть неконсистентным
# Запускаем plan чтобы увидеть текущее состояние:
terraform plan

# Если план "разумный" — применяем снова:
terraform apply

# Terraform достаточно умён чтобы не трогать уже созданные ресурсы
# Он доделает только то что не успел
```

**6. Remote state: `terraform init` не может подключиться к backend**

Симптом: `Error: Failed to get existing workspaces: S3 bucket does not exist` или `connection refused`.

```bash
# Проверить что MinIO/S3 доступен:
curl http://localhost:9000/minio/health/live

# Проверить credentials (для AWS):
aws s3 ls s3://your-terraform-state-bucket

# Для MinIO — проверить что контейнер запущен:
docker ps | grep minio

# Проверить bucket существует:
docker run --rm --network host \
  -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 \
  minio/mc ls local/

# Пересоздать backend конфигурацию (без миграции):
terraform init -reconfigure
```

**7. `terraform force-unlock` нужен но нет LOCK_ID**

Симптом: apply завис и был убит, теперь lock есть но ID неизвестен.

```bash
# Для S3 backend с DynamoDB — посмотреть lock напрямую:
aws dynamodb scan --table-name terraform-state-lock

# Для MinIO (нет DynamoDB) — lock хранится в отдельном файле в bucket:
docker run --rm --network host \
  -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 \
  minio/mc ls local/terraform-state/bulletin-board/dev/
# Увидишь terraform.tfstate.tflock — содержит ID

docker run --rm --network host \
  -e MC_HOST_local=http://minioadmin:minioadmin@localhost:9000 \
  minio/mc cat local/terraform-state/bulletin-board/dev/terraform.tfstate.tflock
# Из вывода берём "ID" и передаём в force-unlock:
terraform force-unlock <ID>
```

---

## Архитектура

- [Концепция: Infrastructure as Code в вакууме](../docs/architecture/level-9-terraform/concept.html) — цикл plan → apply → state
- [Реализация: реальный main.tf](../docs/architecture/level-9-terraform/implementation.html) — provider docker управляет локальными контейнерами
- [Боль → решение: ручная инфраструктура → IaC](../docs/architecture/level-9-terraform/pain-solution.html) — от невоспроизводимых команд к версионируемому коду

Сетевой схемы для этого уровня нет: Terraform — инструмент tooling-слоя, он не меняет сетевую топологию приложения, только способ её создания (см. сетевые схемы Level 1-3, которые описывают ту же инфраструктуру).

Диаграммы — самодостаточные `.html` файлы (переключатель темы, экспорт в PNG/SVG в браузере). GitHub покажет только исходный код — открывай файл локально в браузере.
