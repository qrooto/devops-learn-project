# Terraform конфигурация для DEV окружения.
# Использует модули из ../../modules/
#
# Provider: docker (для локальной практики без облака).
# В prod замени на aws / google / yandexcloud.

terraform {
  required_version = ">= 1.9"

  required_providers {
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
  }

  # В prod backend хранит state в S3/GCS/Terraform Cloud.
  # Для учёбы используем локальный файл.
  # НИКОГДА не коммить terraform.tfstate в Git — там могут быть секреты!
  backend "local" {
    path = "terraform.tfstate"
  }
}

provider "docker" {}

# ── Модуль: сеть ──────────────────────────────────────────────────────────────

resource "docker_network" "app" {
  name   = "${var.env}-bulletin-board"
  driver = "bridge"
}

# ── Модуль: PostgreSQL ────────────────────────────────────────────────────────

resource "docker_image" "postgres" {
  name = "postgres:16-alpine"
}

resource "docker_container" "postgres" {
  name  = "${var.env}-postgres"
  image = docker_image.postgres.image_id

  env = [
    "POSTGRES_DB=${var.db_name}",
    "POSTGRES_USER=${var.db_user}",
    "POSTGRES_PASSWORD=${var.db_password}",
  ]

  networks_advanced {
    name = docker_network.app.name
  }

  volumes {
    volume_name    = docker_volume.postgres_data.name
    container_path = "/var/lib/postgresql/data"
  }

  healthcheck {
    test         = ["CMD-SHELL", "pg_isready -U ${var.db_user}"]
    interval     = "5s"
    timeout      = "5s"
    retries      = 5
    start_period = "10s"
  }
}

resource "docker_volume" "postgres_data" {
  name = "${var.env}-postgres-data"
}

# ── Модуль: бэкенд ────────────────────────────────────────────────────────────

resource "docker_image" "backend" {
  name = "bulletin-board-backend:${var.backend_version}"
  build {
    context    = "${path.root}/../../level-1-monolith/backend"
    dockerfile = "Dockerfile"
  }

  # Пересобирать образ при изменении версии
  triggers = {
    version = var.backend_version
  }
}

resource "docker_container" "backend" {
  name  = "${var.env}-backend"
  image = docker_image.backend.image_id

  env = [
    "DATABASE_URL=postgresql://${var.db_user}:${var.db_password}@${var.env}-postgres:5432/${var.db_name}",
    "SECRET_KEY=${var.secret_key}",
  ]

  networks_advanced {
    name = docker_network.app.name
  }

  depends_on = [docker_container.postgres]
}

# ── Модуль: Nginx ─────────────────────────────────────────────────────────────

resource "docker_image" "nginx" {
  name = "nginx:alpine"
}

resource "docker_container" "nginx" {
  name  = "${var.env}-nginx"
  image = docker_image.nginx.image_id

  ports {
    internal = 80
    external = var.nginx_port
  }

  networks_advanced {
    name = docker_network.app.name
  }

  depends_on = [docker_container.backend]
}
