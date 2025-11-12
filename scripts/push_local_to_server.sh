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
#   APT_MIRROR=mirrors.aliyun.com
#   SECURITY_MIRROR=mirrors.aliyun.com
#   PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
#   PIP_TIMEOUT=600

SERVER=${SERVER:-root@60.205.161.135}
REMOTE_DIR=${REMOTE_DIR:-/opt/nebula}
PORT=${PORT:-5000}
SECRET_KEY=${SECRET_KEY:-}
PIP_INDEX_URL=${PIP_INDEX_URL:-https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple}
PIP_TIMEOUT=${PIP_TIMEOUT:-180}
APT_MIRROR=${APT_MIRROR:-mirrors.aliyun.com}
SECURITY_MIRROR=${SECURITY_MIRROR:-mirrors.aliyun.com}
SSH_OPTS=${SSH_OPTS:-"-o BatchMode=yes -o ConnectTimeout=8"}

BLUE="\033[0;34m"; RESET="\033[0m"; RED="\033[0;31m"; YELLOW="\033[1;33m"
log(){ printf "%b[INFO]%b %s\n" "$BLUE" "$RESET" "$*"; }
warn(){ printf "%b[WARN]%b %s\n" "$YELLOW" "$RESET" "$*"; }
err(){ printf "%b[ERROR]%b %s\n" "$RED" "$RESET" "$*"; }

# 计算本地项目根目录（脚本所在目录的上级）
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
LOCAL_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

log "本地：$LOCAL_ROOT -> 远端：$SERVER:$REMOTE_DIR，端口：$PORT"
log "SSH 选项：$SSH_OPTS"

# 仅允许公钥认证（客户端拒绝密码），提升安全性
SSH_BIN="ssh -o PreferredAuthentications=publickey -o PasswordAuthentication=no $SSH_OPTS"
log "SSH 认证方式：仅公钥登录"

# 确认 rsync 在远端可用，如无则安装（覆盖常见发行版）
$SSH_BIN "$SERVER" bash -lc "set -euo pipefail; \
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
  --exclude "部署排障脚本.txt"
)

log "推送文件（rsync）..."
rsync -avz --delete -e "$SSH_BIN" "${RSYNC_EXCLUDES[@]}" "$LOCAL_ROOT/" "$SERVER:$REMOTE_DIR/"

# 远端触发重建（跳过 Git 拉取）
log "远端重建服务..."
$SSH_BIN "$SERVER" bash -lc "set -euo pipefail; \
  if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC='docker-compose'; fi; \
  cd '$REMOTE_DIR'; \
  # 加载已有 .env 以复用持久化默认值 \
  if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
  [ -f .env ] || sudo touch .env; \
  # 持久化镜像参数（若不存在则追加；已有值不覆盖） \
  grep -q '^APT_MIRROR=' .env 2>/dev/null || echo APT_MIRROR='$APT_MIRROR' | sudo tee -a .env >/dev/null; \
  grep -q '^SECURITY_MIRROR=' .env 2>/dev/null || echo SECURITY_MIRROR='$SECURITY_MIRROR' | sudo tee -a .env >/dev/null; \
  grep -q '^PIP_INDEX_URL=' .env 2>/dev/null || echo PIP_INDEX_URL='$PIP_INDEX_URL' | sudo tee -a .env >/dev/null; \
  grep -q '^PIP_TIMEOUT=' .env 2>/dev/null || echo PIP_TIMEOUT='$PIP_TIMEOUT' | sudo tee -a .env >/dev/null; \
  # 确保自动更新脚本位于根目录，避免被 rsync --delete 清理 \
  if ! grep -q '^PORT=' .env; then echo PORT=$PORT | sudo tee -a .env >/dev/null; else sudo sed -i.bak -E 's/^PORT=.*/PORT=$PORT/g' .env; fi; \
  if [ -n '$SECRET_KEY' ]; then \
    if ! grep -q '^SECRET_KEY=' .env; then echo SECRET_KEY=$SECRET_KEY | sudo tee -a .env >/dev/null; else sudo sed -i.bak -E 's/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/g' .env; fi; \
  fi; \
  # 兼容脚本路径：优先使用根目录 auto_update.sh，其次 scripts/auto_update.sh \
  AU_SCRIPT='./auto_update.sh'; \
  if [ ! -f "$AU_SCRIPT" ]; then \
    if [ -f './scripts/auto_update.sh' ]; then \
      sudo cp ./scripts/auto_update.sh ./auto_update.sh || true; \
      sudo chmod +x ./auto_update.sh || true; \
    else \
      echo 'auto_update.sh 未找到（期待 ./auto_update.sh 或 ./scripts/auto_update.sh）' && exit 1; \
    fi; \
  fi; \
  DISABLE_GIT_PULL=true APT_MIRROR='$APT_MIRROR' SECURITY_MIRROR='$SECURITY_MIRROR' PIP_INDEX_URL='$PIP_INDEX_URL' PIP_TIMEOUT='$PIP_TIMEOUT' PORT='$PORT' SECRET_KEY='$SECRET_KEY' bash "$AU_SCRIPT""

log "完成推送与重建。你可以运行：ssh $SERVER 'docker compose ps' 查看状态"