# 云端部署指南（Nebula OCR + 剧本评估）

本项目提供 Flask Web 应用与 OCR API，可直接在云服务器部署并通过浏览器与 HTTP 接口使用，无需在本地安装。

## 一、准备服务器

- 操作系统：Linux x86_64（Ubuntu/Debian 推荐）
- 预装 Docker（v20+）
- 开放端口：`8080`（可按需修改）

## 二、构建镜像

```bash
docker build -t nebula-ocr:latest .
```

可选（国内镜像加速）：
- 使用 Compose 传入构建参数（APT/PyPI 镜像与超时）：

```bash
docker compose build \
  --build-arg APT_MIRROR=mirrors.aliyun.com \
  --build-arg SECURITY_MIRROR=mirrors.aliyun.com \
  --build-arg PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  --build-arg PIP_TIMEOUT=600 app
```

也可在仓库根目录创建 `.env`（持久化），例如：

```
APT_MIRROR=mirrors.aliyun.com
SECURITY_MIRROR=mirrors.aliyun.com
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
PIP_TIMEOUT=600
PORT=5000
```

镜像包含：
- Python 3.10 与项目依赖（Flask、openpyxl、PyMuPDF、pytesseract、Pillow、psutil 等）
- Tesseract OCR 与中文语言包（`chi_sim`）

## 三、运行容器

```bash
docker run -d \
  --name nebula-ocr \
  -p 8080:8080 \
  -e HOST=0.0.0.0 \
  -e PORT=8080 \
  -e API_KEY="<可选：自定义API密钥>" \
  -v /srv/nebula-data:/data \
  nebula-ocr:latest
```

- 数据持久化：容器内应用会将会话/账号数据写入 `/data`（Excel、上传与 OCR 输出），请将宿主机目录挂载到此路径。
- API 保护：若设置 `API_KEY`，所有 `/api/*` 需在请求头传递 `X-API-Key: <值>`。

## 四、服务访问

- Web 界面（登录/上传/预览）：`http://<服务器IP或域名>:8080/`
- OCR 健康检查：`GET /api/health`（需 `X-API-Key`，若启用）
- OCR 上传处理：`POST /api/ocr/upload`
  - `form-data`：`files[]`（可多个，支持 PDF/JPG/PNG/TIFF/BMP）
  - 可选参数：`lang`（默认 `chi_sim+eng`）、`threshold`（默认 `0.95`）、`workers`（默认自动）
  - 响应包含：每个文件的 `status/accuracy/text_output_path/page_count/duration_seconds/errors` 与输出目录位置
- OCR 汇总：`GET /api/ocr/summary`
  - 返回最近一次 OCR 批处理汇总（当前账号/会话隔离）

## 五、环境变量说明

- `DATA_DIR`：默认 `/data`；应用数据根目录
- `UPLOAD_DIR`：默认 `/data/uploads`；上传根目录
- `HOST`/`PORT`：Flask/Gunicorn 绑定地址与端口（默认 `0.0.0.0:8080`）
- `API_KEY`：开启后要求全部 `/api/*` 请求传 `X-API-Key`

## 六、性能与准确率

- OCR 管线支持多线程并发（Gunicorn 多进程 + 线程），单页处理目标不超过 5 秒，具体依赖服务器性能与输入清晰度
- HOCR 输出保留页面布局；文本输出统一为 UTF-8，并在报告中给出平均准确率（基于 Tesseract 置信度）

## 七、故障排查

- 检查容器日志：`docker logs -f nebula-ocr`
- 确认 `reports/ocr_run_summary.json` 是否生成（在挂载的 `/srv/nebula-data/user_data/<会话或账号ID>/ocr/reports/` 下）
- 若提示 `OCR 模块不可用`，请确认镜像构建成功且 `pytesseract/PyMuPDF/Pillow` 安装正确

## 八、Nginx 与应用一键重启/验证

- 推送脚本与自动更新脚本已集成：重建后会 `up -d nginx` 并打印 `app/nginx` 最近日志，便于快速验证上线状态。

---

如需接入平台域名与 HTTPS，建议在服务器上配置 Nginx 反向代理并开启 TLS。