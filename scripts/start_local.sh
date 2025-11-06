#!/usr/bin/env bash
set -euo pipefail

# 启动本地 Flask 服务并打印预览地址
cd "$(dirname "$0")/.."

export FLASK_APP=tools/web_app.py
export FLASK_ENV=production

echo "[INFO] Starting Nebula web app at http://127.0.0.1:5000/"
python3 tools/web_app.py