#!/usr/bin/env bash
set -euo pipefail

# 星河无限 · Nebula — 一键同步到云服务器（打包上传 + Compose重启）
# 用法示例：
#   bash scripts/deploy_oneclick.sh -s root@60.205.161.135 -r /opt/nebula -p 5000 -k "$(openssl rand -hex 32)"
# 可选参数：
#   -s, --server       服务器 SSH 目标，格式 user@host（默认：root@60.205.161.135）
#   -r, --remote-dir   远程项目目录（默认：/opt/nebula）
#   -p, --port         应用端口（默认：5000）
#   -k, --secret-key   Flask 会话密钥（默认：空，不改动）
#   -m, --mode         同步模式：tar 或 git（默认：tar）
#   -b, --branch       git 模式使用的分支（默认：main）
#   -d, --domain       域名（可选，仅用于提示与健康检查输出）
#
# 说明：
# - tar 模式：本地打包当前目录（排除 .git/uploads/user_data 等），上传到服务器并覆盖远程目录，再重建 app 服务。
# - git 模式：服务器上已有仓库与 origin 时，拉取指定分支并重建 app 服务（无需上传）。

RED="\033[0;31m"; GREEN="\033[0;32m"; YELLOW="\033[1;33m"; BLUE="\033[0;34m"; RESET="\033[0m"
log() { printf "%b[INFO]%b %s\n" "$BLUE" "$RESET" "$*"; }
warn() { printf "%b[WARN]%b %s\n" "$YELLOW" "$RESET" "$*"; }
err() { printf "%b[ERROR]%b %s\n" "$RED" "$RESET" "$*"; }

SERVER="root@60.205.161.135"
REMOTE_DIR="/opt/nebula"
PORT="5000"
SECRET_KEY=""
MODE="tar" # tar | git
BRANCH="main"
DOMAIN="nebula.org.cn"

usage() {
  cat <<USAGE
用法：bash scripts/deploy_oneclick.sh [选项]
  -s, --server       SSH 目标（user@host），默认：$SERVER
  -r, --remote-dir   远程目录，默认：$REMOTE_DIR
  -p, --port         应用端口，默认：$PORT
  -k, --secret-key   SECRET_KEY（可选）
  -m, --mode         同步模式：tar 或 git，默认：$MODE
  -b, --branch       git 分支（git 模式），默认：$BRANCH
  -d, --domain       域名（用于提示），默认：$DOMAIN
示例：
  bash scripts/deploy_oneclick.sh -s root@60.205.161.135 -r /opt/nebula -p 5000 -k "$(openssl rand -hex 32)"
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -s|--server) SERVER="$2"; shift 2;;
    -r|--remote-dir) REMOTE_DIR="$2"; shift 2;;
    -p|--port) PORT="$2"; shift 2;;
    -k|--secret-key) SECRET_KEY="$2"; shift 2;;
    -m|--mode) MODE="$2"; shift 2;;
    -b|--branch) BRANCH="$2"; shift 2;;
    -d|--domain) DOMAIN="$2"; shift 2;;
    -h|--help) usage; exit 0;;
    *) err "未知参数：$1"; usage; exit 1;;
  esac
done

# 依赖检查
for cmd in ssh scp tar; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    err "本机缺少命令：$cmd"; exit 1
  fi
done

if [[ "$MODE" != "tar" && "$MODE" != "git" ]]; then
  err "--mode 仅支持 tar 或 git"; exit 1
fi

log "目标：$SERVER，远程目录：$REMOTE_DIR，模式：$MODE，端口：$PORT"

if [[ "$MODE" == "git" ]]; then
  log "在服务器上使用 git 拉取分支：$BRANCH"
  ssh "$SERVER" bash -lc "set -euo pipefail; \
    if docker compose version >/dev/null 2>&1; then DC='docker compose'; else DC='docker-compose'; fi; \
    SUDO=''; if [ \"\$(id -u)\" -ne 0 ]; then SUDO='sudo'; fi; \
    $SUDO mkdir -p '$REMOTE_DIR'; cd '$REMOTE_DIR'; \
    if [ ! -d .git ]; then echo '远程目录不存在 .git，无法 git 同步'; exit 1; fi; \
    $SUDO git fetch --all; $SUDO git reset --hard origin/$BRANCH; \
    # 更新 .env 中的 PORT 与 SECRET_KEY
    [ -f .env ] || touch .env; \
    if ! grep -q '^PORT=' .env; then echo PORT=$PORT | $SUDO tee -a .env >/dev/null; else $SUDO sed -i.bak -E 's/^PORT=.*/PORT=$PORT/g' .env; fi; \
    if [ -n '$SECRET_KEY' ]; then \
      if ! grep -q '^SECRET_KEY=' .env; then echo SECRET_KEY=$SECRET_KEY | $SUDO tee -a .env >/dev/null; else $SUDO sed -i.bak -E 's/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/g' .env; fi; \
    fi; \
    $SUDO $DC up -d --build app; $SUDO $DC up -d nginx || true; \
    $SUDO $DC ps; $SUDO $DC logs -n 100 app || true; \
    $SUDO $DC exec app sh -lc 'ls -l /data/system || true; test -f /data/system/nebula.db && echo DB=OK || echo DB=MISSING'"
  log "完成 git 同步与重启。请访问：http://$DOMAIN/ 或 http://$DOMAIN/login"
  exit 0
fi

# tar 模式：本地打包并上传到服务器
TS=$(date +%Y%m%d-%H%M%S)
TARBALL="nebula-$TS.tar.gz"
log "开始打包：$TARBALL"

tar -czf "$TARBALL" \
  --exclude=".git" \
  --exclude=".trae" \
  --exclude="uploads" \
  --exclude="user_data" \
  --exclude="*.pyc" \
  --exclude="__pycache__" \
  .

log "上传到服务器临时目录：/tmp/$TARBALL"
scp "$TARBALL" "$SERVER:/tmp/$TARBALL"

log "远程解包并重启 app 服务"
ssh "$SERVER" bash -s -- "/tmp/$TARBALL" "$REMOTE_DIR" "$PORT" "$SECRET_KEY" <<'REMOTE_CMDS'
set -euo pipefail
TARBALL="$1"; REMOTE_DIR="$2"; PORT="$3"; SECRET_KEY="$4"

if docker compose version >/dev/null 2>&1; then DC="docker compose"; else DC="docker-compose"; fi
SUDO=""; if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

$SUDO mkdir -p "$REMOTE_DIR"
$SUDO tar xzf "$TARBALL" -C "$REMOTE_DIR"
cd "$REMOTE_DIR"

[ -f .env ] || touch .env
if ! grep -q "^PORT=" .env; then echo "PORT=$PORT" | $SUDO tee -a .env >/dev/null; else $SUDO sed -i.bak -E "s/^PORT=.*/PORT=$PORT/g" .env; fi
if [ -n "$SECRET_KEY" ]; then
  if ! grep -q "^SECRET_KEY=" .env; then echo "SECRET_KEY=$SECRET_KEY" | $SUDO tee -a .env >/dev/null; else $SUDO sed -i.bak -E "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/g" .env; fi
fi

$SUDO $DC up -d --build app
$SUDO $DC up -d nginx || true

$SUDO $DC ps
$SUDO $DC logs -n 100 app || true
$SUDO $DC exec app sh -lc 'ls -l /data/system || true; test -f /data/system/nebula.db && echo DB=OK || echo DB=MISSING'
REMOTE_CMDS

log "完成部署。建议访问：http://$DOMAIN/ 或 http://$DOMAIN/login"
log "如需回滚，可保留上一版本的压缩包并按需覆盖远程目录。"

# 清理本地包
rm -f "$TARBALL" || true
log "本地临时包已删除：$TARBALL"