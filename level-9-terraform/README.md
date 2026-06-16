# Уровень 9 — Terraform: Infrastructure as Code

## Зачем это нужно

Ansible = управление конфигурацией существующих серверов.
Terraform = создание и управление самой инфраструктурой.

Разница на примере:
- **Ansible**: "на этом сервере установи Docker" (знает что сервер уже есть)
- **Terraform**: "создай сервер в AWS, дай ему 4 ядра, 8GB RAM, открой порт 80"

Terraform управляет жизненным циклом ресурсов: создал → изменил → удалил.

## Аналогия

Ansible — прораб который руководит рабочими на уже построенной стройке.
Terraform — архитектор который сначала проектирует здание (plan), потом строит его (apply), и может полностью снести (destroy).

## Ключевые концепции

```
Код (.tf файлы)
    ↓ terraform plan   → показывает ЧТО изменится (не применяет)
    ↓ terraform apply  → применяет изменения
    ↓
State файл (terraform.tfstate)
    ↑ terraform читает state чтобы знать текущее состояние
    ↑ сравнивает с кодом → вычисляет diff
```

**State** — самое важное понятие в Terraform. Это JSON-файл где хранится информация о всех созданных ресурсах. Terraform сравнивает state с кодом → понимает что нужно создать/изменить/удалить.

**Почему state нельзя коммить в Git:** он содержит чувствительные данные (пароли, ключи). В команде state хранят в S3/GCS/Terraform Cloud — там он общий для всех.

---

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

## Шаг 9 — Remote State (как в prod)

В prod state нельзя хранить локально — при работе в команде каждый имеет свою копию и они расходятся.

```hcl
# В реальном проекте backend выглядит так:

# AWS S3:
terraform {
  backend "s3" {
    bucket = "my-terraform-state"
    key    = "bulletin-board/dev/terraform.tfstate"
    region = "eu-central-1"
  }
}

# Yandex Object Storage (аналог S3):
terraform {
  backend "s3" {
    endpoint = "https://storage.yandexcloud.net"
    bucket   = "my-tf-state"
    key      = "bulletin-board/dev/terraform.tfstate"
    region   = "ru-central1"
    # access_key и secret_key через env vars
  }
}
```

---

## На собеседовании спросят

**Q: Что такое Terraform State и зачем он нужен?**
A: JSON-файл где Terraform хранит информацию о созданных ресурсах. Без state Terraform не знает что уже создано и будет пытаться создать всё заново. В команде хранится в удалённом backend (S3, GCS) с locking чтобы не было конфликтов.

**Q: В чём разница terraform plan и terraform apply?**
A: plan — dry run, показывает что изменится без применения. apply — применяет изменения. В prod: plan запускают в CI для ревью, apply — только после approve.

**Q: Что такое idempotency в Terraform?**
A: Можно запустить apply 100 раз — если код не изменился, ничего не произойдёт. Terraform сравнивает state с реальностью и делает только нужные изменения.

**Q: Чем Terraform отличается от Ansible?**
A: Terraform — для создания инфраструктуры (VM, сети, storage). Ansible — для конфигурирования существующих серверов (установка пакетов, настройка сервисов). Используются вместе: Terraform создаёт VM, Ansible её настраивает.

**Q: Что такое Terraform modules?**
A: Переиспользуемые блоки конфигурации. Как функция в программировании — выносишь общую логику (например "создать VM с Nginx") в модуль, используешь в разных окружениях с разными параметрами.

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
