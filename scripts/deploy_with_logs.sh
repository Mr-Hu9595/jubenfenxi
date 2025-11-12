#!/usr/bin/env bash
# 部署脚本：变更检查 + 依赖更新 + 服务重启 + 部署日志
# 要求：本地已配置到云服务器的免密或秘钥；远程安装了 docker 与 docker compose
# 环境变量：
#   SERVER         服务器地址（必填），例：user@host
#   REMOTE_DIR     远程目录（必填），例：/opt/nebula
#   SSH_KEY        SSH私钥路径（可选）
#   PORT           SSH端口（默认22）
#   RSYNC_EXCLUDES rsync排除（可选，空格分隔）
# 使用示例：
#   SERVER=user@host REMOTE_DIR=/opt/nebula ./scripts/deploy_with_logs.sh

set -euo pipefail

PORT=${PORT:-22}
SSH_OPTS=(-p "$PORT")
[[ -n "${SSH_KEY:-}" ]] && SSH_OPTS+=( -i "$SSH_KEY" )

if [[ -z "${SERVER:-}" || -z "${REMOTE_DIR:-}" ]]; then
  echo "[错误] 必须设置 SERVER 与 REMOTE_DIR 环境变量" >&2
  exit 1
fi

TS=$(date +%Y%m%d_%H%M%S)
REMOTE_LOG_DIR="$REMOTE_DIR/logs"
REMOTE_LOG_FILE="$REMOTE_LOG_DIR/deploy_$TS.log"

echo "[1/4] 代码变更检查与推送（rsync）"
EXCLUDES=(".git" ".venv" "__pycache__" ".DS_Store" "node_modules" "*.pyc" "*.pyo" "部署排障脚本.txt")
for e in ${RSYNC_EXCLUDES:-}; do EXCLUDES+=("$e"); done

RSYNC_EXCLUDE_ARGS=()
for e in "${EXCLUDES[@]}"; do RSYNC_EXCLUDE_ARGS+=(--exclude "$e"); done

rsync -avz --delete "${RSYNC_EXCLUDE_ARGS[@]}" -e "ssh ${SSH_OPTS[*]}" ./ "$SERVER:$REMOTE_DIR/" | tee /tmp/deploy_rsync_$TS.log

echo "[2/4] 远程日志目录初始化：$REMOTE_LOG_DIR"
ssh "${SSH_OPTS[@]}" "$SERVER" "mkdir -p '$REMOTE_LOG_DIR' && echo '[deploy] start $TS' | tee -a '$REMOTE_LOG_FILE'"

echo "[3/4] 依赖更新与服务重启（Docker Compose）"
ssh "${SSH_OPTS[@]}" "$SERVER" bash -lc "\
  set -euo pipefail; \
  cd '$REMOTE_DIR'; \
  if command -v docker compose >/dev/null 2>&1; then DC='docker compose'; else DC='docker-compose'; fi; \
  echo '[remote] 使用 Compose 命令:' \$DC | tee -a '$REMOTE_LOG_FILE'; \
  \$DC pull |& tee -a '$REMOTE_LOG_FILE'; \
  \$DC build |& tee -a '$REMOTE_LOG_FILE'; \
  \$DC up -d |& tee -a '$REMOTE_LOG_FILE'; \
  # 依赖更新（容器内）
  (\$DC exec -T app pip install -r requirements.txt |& tee -a '$REMOTE_LOG_FILE') || true; \
  (\$DC exec -T nebula-app pip install -r requirements.txt |& tee -a '$REMOTE_LOG_FILE') || true; \
  # 数据库迁移
  (\$DC exec -T app python scripts/db_migrate.py |& tee -a '$REMOTE_LOG_FILE') || \
  (\$DC exec -T nebula-app python scripts/db_migrate.py |& tee -a '$REMOTE_LOG_FILE') || true; \
  echo '[remote] 服务状态：' | tee -a '$REMOTE_LOG_FILE'; \
  \$DC ps | tee -a '$REMOTE_LOG_FILE'; \
"

echo "[4/4] 部署完成，日志位于：$SERVER:$REMOTE_LOG_FILE"
echo "本地 rsync 列表：/tmp/deploy_rsync_$TS.log"