# Outputs — значения которые Terraform выводит после apply.
# Полезны для автоматизации: другие скрипты могут читать IP, порты и т.д.

output "app_url" {
  description = "URL приложения"
  value       = "http://localhost:${var.nginx_port}"
}

output "postgres_container_id" {
  description = "ID PostgreSQL контейнера"
  value       = docker_container.postgres.id
}

output "network_name" {
  description = "Имя Docker-сети"
  value       = docker_network.app.name
}
