#!/usr/bin/env bash
set -eo pipefail

# 本地推送部署脚本：使用 rsync 将当前项目推送到服务器并触发重建
# 用法（在本地项目根目录执行）：
#   bash scripts/push_local_to_server.sh
# 可覆盖的环境变量：
#   SERVER=root@60.205.161.135
#   REMOTE_DIR=/opt/nebula
#   PORT=5000
#   SECRET_KEY= # 可留空，首次写入后不再覆盖
#   PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
#   PIP_TIMEOUT=180

SERVER=${SERVER:-root@60.205.161.135}
REMOTE_DIR=${REMOTE_DIR:-/opt/nebula}
PORT=${PORT:-5000}
SECRET_KEY=${SECRET_KEY:-}
PIP_INDEX_URL=${PIP_INDEX_URL:-https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple}
PIP_TIMEOUT=${PIP_TIMEOUT:-180}

BLUE="\033[0;34m"; RESET="\033[0m"; RED="\033[0;31m"; YELLOW="\033[1;33m"
log(){ printf "%b[INFO]%b %s\n" "$BLUE" "$RESET" "$*"; }
warn(){ printf "%b[WARN]%b %s\n" "$YELLOW" "$RESET" "$*"; }
err(){ printf "%b[ERROR]%b %s\n" "$RED" "$RESET" "$*"; }

# 计算本地项目根目录（脚本所在目录的上级）
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
LOCAL_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

log "本地：$LOCAL_ROOT -> 远端：$SERVER:$REMOTE_DIR，端口：$PORT"

# 确认 rsync 在远端可用，如无则安装（覆盖常见发行版）
ssh "$SERVER" bash -lc "set -euo pipefail; \
  if ! command -v rsync >/dev/null 2>&1; then \
    if command -v apt-get >/dev/null 2>&1; then sudo apt-get update -y && sudo apt-get install -y rsync; \
    elif command -v dnf >/dev/null 2>&1; then sudo dnf -y install rsync; \
    elif command -v yum >/dev/null 2>&1; then sudo yum -y install rsync; \
    elif command -v apk >/dev/null 2>&1; then sudo apk add --no-cache rsync; \
    else echo '无法自动安装 rsync，请手动安装后重试' && exit 1; fi; \
  fi; \
  sudo mkdir -p '$REMOTE_DIR'"

# 推送代码（排除不必要文件/目录）
RSYNC_EXCLUDES=(
  --exclude ".git/"
  --exclude ".trae/"
  --exclude "venv/"
  --exclude "__pycache__/"
  --exclude "*.pyc"
  --exclude "uploads/"
  --exclude "*.log"
  --exclude "nebula.db"
)

log "推送文件（rsync）..."
rsync -avz --delete "${RSYNC_EXCLUDES[@]}" "$LOCAL_ROOT/" "$SERVER:$REMOTE_DIR/"

# 远端触发重建（跳过 Git 拉取）
log "远端重建服务..."
ssh "$SERVER" bash -lc "set -euo pipefail; \
  if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC='docker-compose'; fi; \
  cd '$REMOTE_DIR'; \
  [ -f .env ] || sudo touch .env; \
  # 确保自动更新脚本位于根目录，避免被 rsync --delete 清理 \
  if ! grep -q '^PORT=' .env; then echo PORT=$PORT | sudo tee -a .env >/dev/null; else sudo sed -i.bak -E 's/^PORT=.*/PORT=$PORT/g' .env; fi; \
  if [ -n '$SECRET_KEY' ]; then \
    if ! grep -q '^SECRET_KEY=' .env; then echo SECRET_KEY=$SECRET_KEY | sudo tee -a .env >/dev/null; else sudo sed -i.bak -E 's/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/g' .env; fi; \
  fi; \
  DISABLE_GIT_PULL=true PIP_INDEX_URL='$PIP_INDEX_URL' PIP_TIMEOUT='$PIP_TIMEOUT' PORT='$PORT' SECRET_KEY='$SECRET_KEY' '$REMOTE_DIR/auto_update.sh'"

log "完成推送与重建。你可以运行：ssh $SERVER 'docker compose ps' 查看状态"