#!/usr/bin/env bash
set -euo pipefail

# 推送到 GitHub 的快捷脚本
# 使用前需在仓库已设置远程：git remote add origin <your-repo-url>

cd "$(dirname "$0")/.."

BRANCH=${BRANCH:-"main"}
MSG=${MSG:-"chore: update UI and upload handling for analysis"}

git add -A
git commit -m "$MSG" || echo "[INFO] Nothing to commit"
git push origin "$BRANCH"

echo "[DONE] Pushed to GitHub on branch $BRANCH."