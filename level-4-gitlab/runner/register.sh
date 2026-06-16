#!/bin/bash
# Скрипт для регистрации GitLab Runner.
# Запусти ПОСЛЕ того как получишь токен в GitLab UI.
#
# Где взять токен:
# GitLab → твой проект → Settings → CI/CD → Runners → New project runner

set -e

GITLAB_URL="http://localhost:8929"
RUNNER_TOKEN="${1:?Укажи токен: ./register.sh <RUNNER_TOKEN>}"

docker compose exec gitlab-runner gitlab-runner register \
  --non-interactive \
  --url "$GITLAB_URL" \
  --token "$RUNNER_TOKEN" \
  --executor "docker" \
  --docker-image "alpine:latest" \
  --docker-volumes "/var/run/docker.sock:/var/run/docker.sock" \
  --docker-privileged \
  --description "docker-runner" \
  --tag-list "docker,linux"

echo "Runner зарегистрирован. Проверь: $GITLAB_URL/admin/runners"
