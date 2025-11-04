#!/usr/bin/env bash
set -euo pipefail

# 一键部署（阿里云轻量服务器），支持HTTP，若域名已解析到本机则自动申请HTTPS。
# 用法示例：
# curl -fsSL https://raw.githubusercontent.com/Mr-Hu9595/jubenfenxi/main/scripts/setup_cn_mirror.sh | bash -s -- -d cn.jubenfenxi.com -e admin@jubenfenxi.com

DOMAIN=""
EMAIL=""
REPO_URL="https://github.com/Mr-Hu9595/jubenfenxi.git"
BRANCH="main"

while [[ $# -gt 0 ]]; do
  case "$1" in
    -d|--domain)
      DOMAIN="$2"; shift 2;;
    -e|--email)
      EMAIL="$2"; shift 2;;
    -r|--repo)
      REPO_URL="$2"; shift 2;;
    -b|--branch)
      BRANCH="$2"; shift 2;;
    *)
      echo "未知参数: $1"; exit 1;;
  esac
done

SUDO=""
if [[ $EUID -ne 0 ]]; then
  SUDO="sudo"
fi

log(){ echo -e "\033[32m[INFO]\033[0m $*"; }
warn(){ echo -e "\033[33m[WARN]\033[0m $*"; }
err(){ echo -e "\033[31m[ERR ]\033[0m $*"; }

server_ip(){ curl -fsSL http://ipinfo.io/ip || curl -fsSL https://api.ip.sb/ip || hostname -I | awk '{print $1}'; }
resolve_ip(){ getent ahostsv4 "$1" | awk 'NR==1{print $1}'; }

log "检测系统并安装依赖..."
# 选择包管理器：apt/dnf/yum/apk
PKG=""
if command -v apt-get >/dev/null 2>&1; then
  PKG="apt"
elif command -v dnf >/dev/null 2>&1; then
  PKG="dnf"
elif command -v yum >/dev/null 2>&1; then
  PKG="yum"
elif command -v apk >/dev/null 2>&1; then
  PKG="apk"
else
  err "未找到常见包管理器（apt/dnf/yum/apk）。请手动安装 git/curl/certbot 后重试。"
  exit 1
fi

case "$PKG" in
  apt)
    $SUDO apt-get update -y
    $SUDO apt-get install -y git curl ca-certificates lsb-release software-properties-common certbot
    ;;
  dnf)
    $SUDO dnf -y install git curl ca-certificates
    # certbot 在部分发行版为 python3-certbot
    ($SUDO dnf -y install certbot || $SUDO dnf -y install python3-certbot) || true
    ;;
  yum)
    $SUDO yum -y install git curl ca-certificates
    # CentOS7 常见：先安装 epel，再装 certbot
    ($SUDO yum -y install epel-release && $SUDO yum -y install certbot) || true
    ;;
  apk)
    $SUDO apk update
    $SUDO apk add --no-cache git curl ca-certificates openssl
    # Alpine 的 certbot 可能为 py3-certbot
    ($SUDO apk add --no-cache certbot || $SUDO apk add --no-cache py3-certbot) || true
    ;;
esac

if ! command -v docker >/dev/null 2>&1; then
  log "安装 Docker..."
  curl -fsSL https://get.docker.com | $SUDO sh
fi

if [[ "$PKG" == "apt" ]]; then
  log "安装 Docker Compose 插件..."
  $SUDO apt-get install -y docker-compose-plugin || true
fi

# 降低OOM风险：创建2G交换区（若不存在）
if ! $SUDO swapon --show | grep -q .; then
  log "创建2G交换区..."
  $SUDO fallocate -l 2G /swapfile || $SUDO dd if=/dev/zero of=/swapfile bs=1M count=2048
  $SUDO chmod 600 /swapfile
  $SUDO mkswap /swapfile
  $SUDO swapon /swapfile
  if ! grep -q "/swapfile" /etc/fstab; then
    echo "/swapfile none swap sw 0 0" | $SUDO tee -a /etc/fstab >/dev/null
  fi
fi

# 拉取或更新仓库
if [[ -d jubenfenxi/.git ]]; then
  log "更新仓库..."
  (cd jubenfenxi && git fetch --all && git checkout "$BRANCH" && git pull --ff-only)
else
  log "克隆仓库..."
  git clone -b "$BRANCH" "$REPO_URL" jubenfenxi
fi

cd jubenfenxi

# 预创建证书目录
mkdir -p nginx/certs

SERVER_IP=$(server_ip)
log "服务器公网IP：$SERVER_IP"

# 如果域名与邮箱都提供且已解析到本机，则申请证书并启用HTTPS模板
ENABLE_HTTPS=false
if [[ -n "$DOMAIN" && -n "$EMAIL" ]]; then
  RESOLVED_IP=$(resolve_ip "$DOMAIN" || true)
  if [[ "$RESOLVED_IP" == "$SERVER_IP" ]]; then
    ENABLE_HTTPS=true
  else
    warn "域名($DOMAIN)当前解析IP=$RESOLVED_IP，与本机IP=$SERVER_IP不匹配，暂启用HTTP。DNS指向正确后再运行本脚本或手动申请证书。"
  fi
fi

if [[ "$ENABLE_HTTPS" == true ]]; then
  log "申请Let’s Encrypt证书（standalone）..."
  # 确保80端口空闲
  docker compose down || true
  $SUDO systemctl stop nginx || true
  # 同时覆盖根域与www子域
  ALT_NAMES=()
  if [[ "$DOMAIN" == www.* ]]; then
    BASE_DOMAIN=${DOMAIN#www.}
    ALT_NAMES=("-d" "$DOMAIN" "-d" "$BASE_DOMAIN")
  else
    ALT_NAMES=("-d" "$DOMAIN" "-d" "www.$DOMAIN")
  fi
  $SUDO certbot certonly --standalone -n --agree-tos -m "$EMAIL" "${ALT_NAMES[@]}"

  log "拷贝证书到Nginx挂载目录..."
  $SUDO cp -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" nginx/certs/fullchain.pem
  $SUDO cp -f "/etc/letsencrypt/live/$DOMAIN/privkey.pem" nginx/certs/privkey.pem

  # 启用HTTPS模板
  if [[ -f nginx/conf.d/se-ssl.conf.example ]]; then
    sed -i "s/example.com/$DOMAIN/g" nginx/conf.d/se-ssl.conf.example
    mv -f nginx/conf.d/se-ssl.conf.example nginx/conf.d/se-ssl.conf
  fi
fi

log "启动服务（Docker Compose）..."
docker compose up -d

log "启动完成。访问方式："
if [[ "$ENABLE_HTTPS" == true ]]; then
  echo " - https://$DOMAIN/"
else
  echo " - http://$SERVER_IP/"
  if [[ -n "$DOMAIN" ]]; then
    echo " - 域名尚未指向本机：$DOMAIN -> $SERVER_IP；指向后可重跑脚本启用HTTPS。"
  fi
fi

log "日志查看： docker compose logs -f"
log "如需重启： docker compose restart"