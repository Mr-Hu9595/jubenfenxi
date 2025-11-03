@echo off
setlocal

python --version
pip show pyinstaller >nul 2>&1 || pip install pyinstaller

rem 构建通用 CLI 二进制
pyinstaller -F tools\universal_cli.py -n ScriptEvaluator

rem 构建 Web 版（含模板）
pyinstaller -F tools\web_app.py -n ScriptEvaluatorWeb --add-data "tools\templates;tools\templates"

echo 构建完成：请查看 dist\ScriptEvaluator.exe 与 dist\ScriptEvaluatorWeb.exe
endlocal