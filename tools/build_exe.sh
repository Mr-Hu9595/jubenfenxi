#!/usr/bin/env bash
set -euo pipefail

python --version
pip show pyinstaller >/dev/null 2>&1 || pip install pyinstaller

# 构建通用 CLI 二进制
pyinstaller -F tools/universal_cli.py -n ScriptEvaluator

# 构建 Web 版（含模板）
pyinstaller -F tools/web_app.py -n ScriptEvaluatorWeb --add-data "tools/templates:tools/templates"

echo "构建完成：dist/ScriptEvaluator 与 dist/ScriptEvaluatorWeb"