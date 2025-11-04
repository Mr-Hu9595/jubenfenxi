#!/usr/bin/env bash
set -euo pipefail

# 简洁版：从仓库更新并在云服务器重启（Git 拉取 + Compose 构建）
# 用法（本机执行）：
#   bash scripts/update_from_repo.sh
# 可通过环境变量覆盖：
#   SERVER=root@60.205.161.135 REMOTE_DIR=/opt/nebula BRANCH=main PORT=5000 SECRET_KEY=$(openssl rand -hex 32) bash scripts/update_from_repo.sh

SERVER=${SERVER:-root@60.205.161.135}
REMOTE_DIR=${REMOTE_DIR:-/opt/nebula}
BRANCH=${BRANCH:-main}
PORT=${PORT:-5000}
SECRET_KEY=${SECRET_KEY:-}
DOMAIN=${DOMAIN:-nebula.org.cn}

BLUE="\033[0;34m"; RESET="\033[0m"; RED="\033[0;31m"; YELLOW="\033[1;33m"
log() { printf "%b[INFO]%b %s\n" "$BLUE" "$RESET" "$*"; }
warn() { printf "%b[WARN]%b %s\n" "$YELLOW" "$RESET" "$*"; }
err() { printf "%b[ERROR]%b %s\n" "$RED" "$RESET" "$*"; }

command -v ssh >/dev/null || { err "本机缺少 ssh"; exit 1; }

log "目标：$SERVER，目录：$REMOTE_DIR，分支：$BRANCH，端口：$PORT"

ssh "$SERVER" bash -lc "set -euo pipefail; \
  if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC='docker-compose'; fi; \
  SUDO=''; if [ \"\$(id -u)\" -ne 0 ]; then SUDO='sudo'; fi; \
  echo '[INFO] 准备目录'; \
  \$SUDO mkdir -p '$REMOTE_DIR'; \
  if [ ! -d '$REMOTE_DIR/.git' ]; then \
    echo '[INFO] 远程未发现仓库，尝试克隆（HTTPS优先）'; \
    \$SUDO git clone --depth=1 https://github.com/Mr-Hu9595/jubenfenxi.git '$REMOTE_DIR' || \$SUDO git clone --depth=1 git@github.com:Mr-Hu9595/jubenfenxi.git '$REMOTE_DIR'; \
  fi; \
  cd '$REMOTE_DIR'; \
  echo '[INFO] 拉取最新代码'; \
  \$SUDO git fetch --all; \$SUDO git reset --hard origin/$BRANCH; \
  echo '[INFO] 写入 .env'; \
  [ -f .env ] || \$SUDO touch .env; \
  if ! grep -q '^PORT=' .env; then echo PORT=$PORT | \$SUDO tee -a .env >/dev/null; else \$SUDO sed -i.bak -E 's/^PORT=.*/PORT=$PORT/g' .env; fi; \
  if [ -n '$SECRET_KEY' ]; then \
    if ! grep -q '^SECRET_KEY=' .env; then echo SECRET_KEY=$SECRET_KEY | \$SUDO tee -a .env >/dev/null; else \$SUDO sed -i.bak -E 's/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/g' .env; fi; \
  fi; \
  echo '[INFO] 重建并启动 app（保留 nginx）'; \
  \$SUDO \$DC up -d --build app; \$SUDO \$DC up -d nginx || true; \
  echo '[INFO] 状态'; \$SUDO \$DC ps; \
  echo '[INFO] 应用日志'; \$SUDO \$DC logs -n 120 app || true; \
  echo '[INFO] 数据库检查'; \$SUDO \$DC exec app sh -lc 'ls -l /data/system || true; test -f /data/system/nebula.db && echo DB=OK || echo DB=MISSING'"

log "完成部署：访问 http://$DOMAIN/ 或 http://$DOMAIN/login"