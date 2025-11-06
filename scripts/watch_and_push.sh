#!/usr/bin/env bash
set -eo pipefail

# 自动监控本地代码变更并执行 rsync 推送到服务器
# 用法（在本地项目根目录执行）：
#   bash scripts/watch_and_push.sh
# 可覆盖的环境变量：
#   SERVER=root@60.205.161.135
#   REMOTE_DIR=/opt/nebula
#   PORT=5000
#   SECRET_KEY=
#   WATCH_PATH=<默认为项目根>
#   EXTS=py,html,css,js,json,yml,yaml,conf,sh,Dockerfile
#   MIN_INTERVAL=3   # 变更防抖（秒）

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
WATCH_PATH=${WATCH_PATH:-"$PROJECT_ROOT"}
EXTS=${EXTS:-py,html,css,js,json,yml,yaml,conf,sh,Dockerfile}
MIN_INTERVAL=${MIN_INTERVAL:-3}
USE_LAUNCHD_WATCH=${USE_LAUNCHD_WATCH:-false}

BLUE="\033[0;34m"; RESET="\033[0m"; YELLOW="\033[1;33m"; RED="\033[0;31m"
log(){ printf "%b[INFO]%b %s\n" "$BLUE" "$RESET" "$*"; }
warn(){ printf "%b[WARN]%b %s\n" "$YELLOW" "$RESET" "$*"; }
err(){ printf "%b[ERROR]%b %s\n" "$RED" "$RESET" "$*"; }

# 忽略目录（避免无关变更触发）
IGNORE_PATTERNS=(
  ".git/"
  ".trae/"
  "venv/"
  "__pycache__/"
  "uploads/"
  "user_data/"
  "tmp/"
)

LAST_PUSH=0

# 本地 GitHub 同步：将变更提交并 push 到远端（默认 origin 当前分支）
git_sync(){
  if [ "${GIT_ENABLE:-true}" != "true" ]; then
    log "Git 同步已禁用（GIT_ENABLE=false）"
    return 0
  fi
  if [ ! -d "$PROJECT_ROOT/.git" ]; then
    warn "未发现 .git，跳过 Git 同步"
    return 0
  fi
  local BRANCH REMOTE MSG STATUS
  BRANCH=$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "${GIT_BRANCH:-main}")
  REMOTE=${GIT_REMOTE:-origin}
  MSG=${GIT_COMMIT_MSG:-"chore(auto): sync via watch_and_push.sh $(date '+%Y-%m-%d %H:%M:%S')"}
  
  # 添加变更（遵循 .gitignore）
  git -C "$PROJECT_ROOT" add -A
  STATUS=$(git -C "$PROJECT_ROOT" status --porcelain)
  if [ -n "$STATUS" ]; then
    git -C "$PROJECT_ROOT" commit -m "$MSG" || warn "git commit 失败"
  else
    log "无代码变更，跳过 commit"
  fi
  # 推送到远端；失败不阻断后续 rsync
  git -C "$PROJECT_ROOT" push "$REMOTE" "$BRANCH" && \
    log "已推送到 $REMOTE/$BRANCH" || \
    warn "git push 失败（可能未配置凭证或网络问题），继续执行 rsync"
}
run_push(){
  local now; now=$(date +%s)
  if [ $(( now - LAST_PUSH )) -lt "$MIN_INTERVAL" ]; then
    return 0
  fi
  LAST_PUSH=$now
  log "检测到变更，执行推送…"
  git_sync
  SERVER="${SERVER:-root@60.205.161.135}" \
  REMOTE_DIR="${REMOTE_DIR:-/opt/nebula}" \
  PORT="${PORT:-5000}" \
  SECRET_KEY="${SECRET_KEY:-}" \
  PIP_INDEX_URL="${PIP_INDEX_URL:-https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple}" \
  PIP_TIMEOUT="${PIP_TIMEOUT:-180}" \
  bash "$SCRIPT_DIR/push_local_to_server.sh" || warn "推送执行失败（将等待下一次变更）"
}

# 若由 launchd 的 WatchPaths 触发，则只执行一次推送后退出（不依赖 fswatch/entr）
if [ "$USE_LAUNCHD_WATCH" = "true" ]; then
  log "LAUNCHD WatchPaths 模式触发：执行一次推送后退出"
  run_push
  exit 0
fi

# 选择监控工具：优先 fswatch，其次 entr
if command -v fswatch >/dev/null 2>&1; then
  log "使用 fswatch 监控：$WATCH_PATH"
  EXCLUDES=()
  for p in "${IGNORE_PATTERNS[@]}"; do
    EXCLUDES+=(--exclude ".*${p}.*")
  done
  fswatch -or ${EXCLUDES[@]} "$WATCH_PATH" | while read -r _; do
    run_push
  done
elif command -v entr >/dev/null 2>&1; then
  log "使用 entr 监控：$WATCH_PATH（扩展：$EXTS）"
  IFS=',' read -r -a exts_arr <<< "$EXTS"
  # 构造 find 的扩展名过滤
  set +e
  FIND_EXPR=("$WATCH_PATH" -type f)
  if [ ${#exts_arr[@]} -gt 0 ]; then
    FIND_EXPR+=(\( -name "*.${exts_arr[0]}" )
    for i in "${exts_arr[@]:1}"; do
      FIND_EXPR+=( -o -name "*.${i}" )
    done
    FIND_EXPR+=( \))
  fi
  # 忽略目录
  for p in "${IGNORE_PATTERNS[@]}"; do
    FIND_EXPR+=( ! -path "*/${p}*" )
  done
  # shellcheck disable=SC2068
  find ${FIND_EXPR[@]} | entr -r sh -c 'bash '"$SCRIPT_DIR"'/push_local_to_server.sh'
else
  warn "未检测到 fswatch 或 entr。请安装其一："
  echo "  brew install fswatch    或    brew install entr"
  exit 1
fi