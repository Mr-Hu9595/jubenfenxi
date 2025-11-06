#!/usr/bin/env bash
set -euo pipefail

# 服务器同步示例脚本（需替换为你的服务器账号）
# 示例：将当前项目同步到阿里云服务器并重启服务

SERVER_HOST=${SERVER_HOST:-"60.205.161.135"}
SERVER_USER=${SERVER_USER:-"root"}
SERVER_DIR=${SERVER_DIR:-"/opt/nebula-app"}

echo "[INFO] Syncing project to $SERVER_USER@$SERVER_HOST:$SERVER_DIR"
rsync -av --delete \
  --exclude ".git" \
  --exclude "__pycache__" \
  --exclude "*.pyc" \
  ./ ${SERVER_USER}@${SERVER_HOST}:${SERVER_DIR}/

echo "[INFO] Restarting service via systemd (if configured)"
ssh ${SERVER_USER}@${SERVER_HOST} "\
  if systemctl list-units --type=service | grep -q nebula.service; then \
    sudo systemctl restart nebula.service; \
  else \
    echo 'nebula.service not found, starting python directly'; \
    nohup python3 ${SERVER_DIR}/tools/web_app.py >/var/log/nebula.log 2>&1 & \
  fi"

echo "[DONE] Deploy completed."