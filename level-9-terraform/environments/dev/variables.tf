variable "env" {
  description = "Название окружения (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "db_name" {
  description = "Имя базы данных"
  type        = string
  default     = "bulletin_board"
}

variable "db_user" {
  description = "Пользователь PostgreSQL"
  type        = string
  default     = "postgres"
}

variable "db_password" {
  description = "Пароль PostgreSQL. В prod передавать через TF_VAR_db_password, не хардкодить!"
  type        = string
  sensitive   = true  # Не выводить в terraform plan/apply
  default     = "postgres-dev-only"
}

variable "secret_key" {
  description = "JWT secret key. В prod — из secrets manager."
  type        = string
  sensitive   = true
  default     = "dev-secret-key-change-in-prod"
}

variable "backend_version" {
  description = "Версия образа бэкенда (git tag или commit SHA)"
  type        = string
  default     = "latest"
}

variable "nginx_port" {
  description = "Внешний порт Nginx"
  type        = number
  default     = 8088
}
