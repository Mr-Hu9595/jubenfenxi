# 通用版打包与使用说明（简版）

## 环境准备
- 安装 Python 3.9+。
- 安装依赖：
  - `pip install -r requirements.txt`

## 使用（脚本版）
- 命令示例：
  - `python tools/universal_cli.py --input ./scripts --excel "/Users/mr.hu/Desktop/爆款排名/剧本评估表.xlsx" --sheet "通用导入"`
- 参数说明：
  - `--input`：输入路径（文件或目录），支持 `.txt/.docx/.pdf`。
  - `--excel`：目标评估表 Excel 路径，默认已指向桌面路径。
  - `--sheet`：目标工作表名，不存在则自动创建并复制模板表头。

## 打包为单文件可执行程序
- 安装打包工具：
  - `pip install pyinstaller`
- macOS：
  - `pyinstaller -F tools/universal_cli.py -n ScriptEvaluator`
  - 生成文件在 `dist/ScriptEvaluator`。
- Windows：
  - `pyinstaller -F tools\universal_cli.py -n ScriptEvaluator`
  - 生成文件在 `dist/ScriptEvaluator.exe`。

### Web 界面打包（含模板）
- macOS：
  - `pyinstaller -F tools/web_app.py -n ScriptEvaluatorWeb --add-data "tools/templates:tools/templates"`
  - 运行：`./dist/ScriptEvaluatorWeb`，打开浏览器访问 `http://127.0.0.1:5000/`。
- Windows：
  - `pyinstaller -F tools\web_app.py -n ScriptEvaluatorWeb --add-data "tools\templates;tools\templates"`
  - 运行：`dist\ScriptEvaluatorWeb.exe`，浏览器访问 `http://127.0.0.1:5000/`。

> 说明：已在代码中加入 `sys._MEIPASS` 路径解析，确保模板在打包后能被找到。

## Android 打包建议（两种路径）
- 方案 A：WebView 封装（推荐）
  - 使用 Android Studio 新建空白 Activity，内嵌 WebView 加载本地或远程服务地址（如 `http://<局域网IP>:5000/`）。
  - 优点：开发量最小；复用现有 Web 界面；适合企业内网或服务器部署。
  - 缺点：需有运行中的服务端（本机或远程）。
- 方案 B：Python 原生打包（Kivy/Buildozer 或 BeeWare Briefcase）
  - 将评分与解析逻辑以 Python 保留，使用 Kivy 或 BeeWare 做移动端 UI。
  - 复杂度高：需解决 `openpyxl/pdfminer/PyMuPDF` 在 Android 的编译与权限适配。
  - 适合离线使用场景，但需要较长工程周期与 Android 编译环境配置。

> 若希望完全离线运行于手机端，建议选用方案 B，并分阶段实现：UI 原型 -> 文本解析 -> Excel 写入 -> 文件权限与下载。

## 常见问题
- PDF 无法解析：
  - 已内置多种解析库（pdfminer/PyMuPDF/pdfplumber），若仍失败，请提供 txt/docx 文本版本。
- 表头缺失：
  - 若目标工作表不存在，将尝试复制“评估输入”的表头；否则写入最小表头并依赖公式与评分逻辑自动填充。
- 评分联动：
  - 脚本会自动写入建议集数与分项汇总、人物饱满度、商业价值指数、总分与评分等级公式。