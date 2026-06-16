# Значения переменных для DEV окружения.
# Для prod создай environments/prod/terraform.tfvars с другими значениями.
# НЕ коммить файлы с паролями в Git! Добавь в .gitignore.

env            = "dev"
nginx_port     = 8088
backend_version = "latest"
