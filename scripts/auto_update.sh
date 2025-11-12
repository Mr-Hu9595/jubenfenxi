#!/usr/bin/env bash
set -euo pipefail

# 星河无限 · Nebula — 服务器自动更新脚本（方案A）
# 作用：定时从远端仓库拉取指定分支，重建 app 服务并保持 nginx 运行。
# 使用：
#   - 将本脚本放到服务器：/opt/nebula/auto_update.sh
#   - 赋权：sudo chmod +x /opt/nebula/auto_update.sh
#   - 先手动运行一次：sudo /opt/nebula/auto_update.sh
#   - 加入 crontab：*/5 * * * * /opt/nebula/auto_update.sh >> /opt/nebula/update.log 2>&1
# 可配置环境变量（可在 crontab 前加，或写入 /opt/nebula/.env）：
#   BRANCH=main
#   PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
#   PIP_TIMEOUT=180
#   PORT=5000
#   SECRET_KEY=<your-secret>

BRANCH=${BRANCH:-main}
# 构建镜像源参数（默认使用阿里云）
APT_MIRROR=${APT_MIRROR:-mirrors.aliyun.com}
SECURITY_MIRROR=${SECURITY_MIRROR:-mirrors.aliyun.com}
PIP_INDEX_URL=${PIP_INDEX_URL:-https://mirrors.aliyun.com/pypi/simple/}
PIP_TIMEOUT=${PIP_TIMEOUT:-600}
PORT=${PORT:-5000}
SECRET_KEY=${SECRET_KEY:-}
REPO_DIR=${REPO_DIR:-/opt/nebula}
SKIP_GIT_PULL=${DISABLE_GIT_PULL:-${SKIP_GIT_PULL:-false}}

BLUE="\033[0;34m"; RESET="\033[0m"; YELLOW="\033[1;33m"; RED="\033[0;31m"
log(){ printf "%b[INFO]%b %s\n" "$BLUE" "$RESET" "$*"; }
warn(){ printf "%b[WARN]%b %s\n" "$YELLOW" "$RESET" "$*"; }
err(){ printf "%b[ERROR]%b %s\n" "$RED" "$RESET" "$*"; }

# 选择 docker compose 命令
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
else
  DC="docker-compose"
fi

SUDO=""; if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

log "目录：$REPO_DIR，分支：$BRANCH，端口：$PORT"

$SUDO mkdir -p "$REPO_DIR"

if [ -d "$REPO_DIR/.git" ] && [ "$SKIP_GIT_PULL" != "true" ]; then
  log "拉取最新代码..."
  cd "$REPO_DIR"
  # 在网络不稳定时，允许 Git 失败但继续后续构建
  $SUDO git fetch --all || warn "git fetch 失败，继续构建"
  $SUDO git reset --hard "origin/$BRANCH" || warn "git reset 失败，继续构建"
else
  if [ "$SKIP_GIT_PULL" = "true" ]; then
    warn "已设置跳过 Git 拉取（DISABLE_GIT_PULL=true）。"
  elif [ ! -d "$REPO_DIR/.git" ]; then
    warn "未发现 .git，跳过 git 拉取。请在 $REPO_DIR 初始化仓库并设置 origin 以启用自动拉取。"
  fi
  cd "$REPO_DIR"
  # 若存在 .env，先加载以提供持久化默认值（调用时传入的环境变量仍可覆盖）
  if [ -f .env ]; then
    set -a
    . ./.env
    set +a
  fi
fi

# 写入/更新 .env（PORT 与 SECRET_KEY）
[ -f .env ] || $SUDO touch .env
if ! grep -q '^PORT=' .env; then
  echo "PORT=$PORT" | $SUDO tee -a .env >/dev/null
else
  $SUDO sed -i.bak -E "s/^PORT=.*/PORT=$PORT/g" .env
fi
if [ -n "$SECRET_KEY" ]; then
  if ! grep -q '^SECRET_KEY=' .env; then
    echo "SECRET_KEY=$SECRET_KEY" | $SUDO tee -a .env >/dev/null
  else
    $SUDO sed -i.bak -E "s/^SECRET_KEY=.*/SECRET_KEY=$SECRET_KEY/g" .env
  fi
fi
 # 持久化镜像参数（如传入，则写入 .env；若已有则不覆盖）
 for kv in "APT_MIRROR=$APT_MIRROR" "SECURITY_MIRROR=$SECURITY_MIRROR" "PIP_INDEX_URL=$PIP_INDEX_URL" "PIP_TIMEOUT=$PIP_TIMEOUT"; do
   key=${kv%%=*}; val=${kv#*=}
   if ! grep -q "^${key}=" .env; then
     echo "$key=$val" | $SUDO tee -a .env >/dev/null
   fi
 done

log "重建 app（使用 APT/PyPI 镜像与延长超时）..."
$SUDO $DC build --progress=plain \
  --build-arg APT_MIRROR="$APT_MIRROR" \
  --build-arg SECURITY_MIRROR="$SECURITY_MIRROR" \
  --build-arg PIP_INDEX_URL="$PIP_INDEX_URL" \
  --build-arg PIP_TIMEOUT="$PIP_TIMEOUT" app

log "启动/更新服务..."
$SUDO $DC up -d app
$SUDO $DC up -d nginx || true

log "检查状态..."
$SUDO $DC ps || true

log "应用日志 (最近120行)..."
$SUDO $DC logs -n 120 app || true

log "Nginx 日志 (最近60行)..."
$SUDO $DC logs -n 60 nginx || true

# 轻量健康检查（本机）
if command -v curl >/dev/null 2>&1; then
  log "HTTP 健康检查..."
  (curl -fsSI http://127.0.0.1/ || curl -fsSI http://localhost/) || true
fi

log "自动更新完成。"