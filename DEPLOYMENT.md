# 云部署指南（ScriptEvaluatorWeb）

本项目已添加 Docker 化与 Render 配置，支持快速在云端运行 Flask Web 应用。以下给出多平台部署方案与操作步骤。

## 一、准备工作
- 推送代码到 GitHub（已完成）。
- 确保依赖齐全：`requirements.txt` 已包含 `Flask` 与 `gunicorn`。
- 容器化：根目录包含 `Dockerfile` 与 `.dockerignore`。

## 二、Render（推荐，免服务器）
两种路径均可：

### 方式 A：Docker 运行（与仓库中 render.yaml 对齐）
- 登录 https://render.com 并选择 New + → Web Service。
- 连接 GitHub 仓库 `Mr-Hu9595/jubenfenxi`。
- 选择“Runtime: Docker”，Render 会自动使用仓库中的 `Dockerfile`。
- 环境变量：`FLASK_ENV=production`（可选），`PORT=5000`（Render 会注入实际端口变量）。
- 部署后访问 Render 提供的域名，例如 `https://script-evaluator-web.onrender.com/`。

### 方式 B：Python 原生运行（不使用 Docker）
- 依次设置：
  - Build Command: `pip install -r requirements.txt`
  - Start Command: `gunicorn --bind 0.0.0.0:$PORT tools.web_app:app`
- 环境变量：`FLASK_ENV=production`（可选）。
- 优点：镜像更小；注意：依赖需 Render 提供兼容环境。

## 三、Railway（免服务器，简洁）
- 登录 https://railway.app，New Project → Deploy from GitHub。
- 服务类型选择 "Docker"，Railway 会读取 `Dockerfile` 构建。
- 若使用 Python 运行：设置 Start Command 为 `gunicorn --bind 0.0.0.0:$PORT tools.web_app:app`。
- 访问项目生成的域名测试上传与下载功能。

## 四、Fly.io（适合容器服务，全球加速）
- 安装 CLI：`brew install flyctl`。
- 在项目根目录执行：
  - `fly launch`（选择 Docker，生成 `fly.toml`，应用名与区域可选）
  - `fly deploy`
- 访问 `https://<app-name>.fly.dev/` 测试。

## 五、Cloud Run（GCP，按调用付费）
- 本地构建镜像：`docker build -t gcr.io/<PROJECT_ID>/script-evaluator-web:latest .`
- 推送：`gcloud auth configure-docker` → `docker push gcr.io/<PROJECT_ID>/script-evaluator-web:latest`
- 部署：`gcloud run deploy script-evaluator-web --image gcr.io/<PROJECT_ID>/script-evaluator-web:latest --platform managed --region <region> --allow-unauthenticated`
- 访问 Cloud Run 分配的 HTTPS URL。

## 六、AWS Lightsail / EC2（自管服务器）
- 安装 Docker：`sudo apt update && sudo apt install -y docker.io`。
- 拉取并运行：
  - `docker build -t script-evaluator-web .`
  - `docker run -d -p 80:5000 --name se-web script-evaluator-web`
- 绑定域名与 HTTPS（Nginx/ALB/Cloudflare 均可）。

## 七、运维要点与存储
- 文件存储：默认容器写入为临时存储。若需持久化，选择：
  - Render Disks / Railway Volumes / Fly.io Volumes；或挂载云盘（AWS EBS/GCP PD）。
  - 将生成的 Excel/可视化文件写入挂载目录（例如 `/data`）。
- 大文件上传：视平台限制调节 Nginx/服务层大小限制；`gunicorn` 超时已设为 120s，可根据文件处理耗时调整。
- 并发与伸缩：平台支持自动扩容，CPU/内存建议起始 `512MB/1 vCPU`，视并发与处理复杂度提升。
- 监控与日志：平台内置基础监控；可接入 Sentry/Prometheus（可选）。

## 八、常见问题
- 模板与静态资源：本项目使用 `tools/templates`，容器内相对路径已通过 `resource_path` 适配，无需额外配置。
- 端口：云平台通常注入 `PORT` 环境变量，Docker CMD 使用 `${PORT:-5000}` 兼容本地与云端。
- HTTPS：平台默认提供 HTTPS；自管服务器需自行配置证书（建议使用 Cloudflare/Let’s Encrypt）。

## 九、本地验证（可选）
- 构建镜像：`docker build -t script-evaluator-web .`
- 运行容器：`docker run -it --rm -p 5000:5000 script-evaluator-web`
- 访问本地：`http://127.0.0.1:5000/`