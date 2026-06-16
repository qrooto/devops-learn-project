#!/bin/bash
# Устанавливает ArgoCD в minikube.
# Запускай из папки level-8-gitops/

set -e

echo "=== Убеждаемся что minikube запущен ==="
minikube status || minikube start --driver=docker --memory=4096 --cpus=2

echo "=== Устанавливаем ArgoCD ==="
kubectl create namespace argocd --dry-run=client -o yaml | kubectl apply -f -
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml

echo "=== Ждём готовности ArgoCD (до 3 минут) ==="
kubectl wait --for=condition=available deployment/argocd-server -n argocd --timeout=180s

echo "=== Устанавливаем argocd CLI ==="
VERSION=$(curl -L -s https://raw.githubusercontent.com/argoproj/argo-cd/stable/VERSION)
curl -sSL -o /usr/local/bin/argocd \
  "https://github.com/argoproj/argo-cd/releases/download/v${VERSION}/argocd-linux-amd64"
chmod +x /usr/local/bin/argocd

echo "=== Получаем начальный пароль ==="
ARGOCD_PASS=$(kubectl -n argocd get secret argocd-initial-admin-secret \
  -o jsonpath="{.data.password}" | base64 -d)
echo "Пароль ArgoCD: $ARGOCD_PASS"

echo "=== Пробрасываем порт (ctrl+c чтобы остановить) ==="
echo "Открой: https://localhost:8443"
kubectl port-forward svc/argocd-server -n argocd 8443:443
