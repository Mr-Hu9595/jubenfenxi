#!/usr/bin/env bash
set -euo pipefail

# 用法：
#   配置环境变量后直接执行：
#   REMOTE_HOST=60.205.161.135 REMOTE_USER=root REMOTE_DIR=/opt/nebula SERVICE_RESTART_CMD="systemctl restart nebula" ./scripts/deploy.sh
#
# 说明：
# - 部署前本地执行摘要质量单元测试；
# - 通过 rsync 同步改动到云服务器；
# - 远端执行测试；
# - 远端按命令重启服务（命令可按环境调整为 docker compose 或 supervisor）。

REMOTE_HOST=${REMOTE_HOST:-}
REMOTE_USER=${REMOTE_USER:-}
REMOTE_DIR=${REMOTE_DIR:-/opt/nebula}
# 默认使用 Docker Compose 作为远端重启方式（可通过 SERVICE_RESTART_CMD 覆盖）
# 说明：在远端检测 docker compose / docker-compose，执行 pull/build/up -d 与状态查看
DEFAULT_COMPOSE_RESTART="bash -lc \"set -euo pipefail; if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC='docker-compose'; fi; \\\$DC pull || true; \\\$DC build || true; \\\$DC up -d; \\\$DC ps\""
SERVICE_RESTART_CMD=${SERVICE_RESTART_CMD:-$DEFAULT_COMPOSE_RESTART}
PYTEST_CMD_LOCAL=${PYTEST_CMD_LOCAL:-"pytest -q tests/test_summary_quality.py"}
PYTEST_CMD_REMOTE=${PYTEST_CMD_REMOTE:-"pytest -q tests/test_summary_quality.py"}

if [[ -z "$REMOTE_HOST" || -z "$REMOTE_USER" ]]; then
  echo "[错误] 请设置 REMOTE_HOST 与 REMOTE_USER 环境变量。" >&2
  exit 1
fi

echo "[步骤1] 本地运行单元测试：$PYTEST_CMD_LOCAL"
eval "$PYTEST_CMD_LOCAL"

echo "[步骤2] 代码同步到远程：$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR"
rsync -avz --delete \
  --exclude '.git' --exclude '__pycache__' --exclude 'uploads' --exclude '部署排障脚本.txt' \
  ./ "$REMOTE_USER@$REMOTE_HOST:$REMOTE_DIR/"

echo "[步骤3] 远程运行单元测试"
ssh "$REMOTE_USER@$REMOTE_HOST" "cd '$REMOTE_DIR' && $PYTEST_CMD_REMOTE"

if [[ -n "$SERVICE_RESTART_CMD" ]];
then
  echo "[步骤4] 重启远程服务：$SERVICE_RESTART_CMD"
  ssh "$REMOTE_USER@$REMOTE_HOST" "cd '$REMOTE_DIR' && $SERVICE_RESTART_CMD"
else
  echo "[提示] 未设置 SERVICE_RESTART_CMD，跳过服务重启。"
fi

echo "[完成] 部署流程执行成功。"