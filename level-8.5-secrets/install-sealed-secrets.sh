#!/bin/bash
# Устанавливает sealed-secrets контроллер в кластер и CLI kubeseal.
# Запускай из папки level-8.5-secrets/

set -e

VERSION="0.27.1"   # https://github.com/bitnami-labs/sealed-secrets/releases

echo "=== Убеждаемся что minikube запущен ==="
minikube status || minikube start --driver=docker --memory=4096 --cpus=2

echo "=== Устанавливаем sealed-secrets контроллер (в kube-system) ==="
kubectl apply -f "https://github.com/bitnami-labs/sealed-secrets/releases/download/v${VERSION}/controller.yaml"

echo "=== Ждём готовности контроллера ==="
kubectl wait --for=condition=available deployment/sealed-secrets-controller \
  -n kube-system --timeout=120s

echo "=== Устанавливаем kubeseal CLI ==="
curl -sSL -o /tmp/kubeseal.tar.gz \
  "https://github.com/bitnami-labs/sealed-secrets/releases/download/v${VERSION}/kubeseal-${VERSION}-linux-amd64.tar.gz"
tar -xzf /tmp/kubeseal.tar.gz -C /tmp kubeseal
sudo install -m 755 /tmp/kubeseal /usr/local/bin/kubeseal
rm /tmp/kubeseal.tar.gz /tmp/kubeseal

echo "=== Проверка ==="
kubeseal --version
kubectl get pods -n kube-system -l name=sealed-secrets-controller

echo ""
echo "Готово. Публичный ключ кластера kubeseal заберёт сам при первом запуске."
echo "🔒 Не забудь про бэкап приватного ключа (см. README, раздел 'сломай намеренно' п.3):"
echo "kubectl get secret -n kube-system -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml > /секретное/место/sealed-secrets-key.yaml"
