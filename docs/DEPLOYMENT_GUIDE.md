# 部署指南（剧本分析系统）
> 重要说明：本项目已不再使用 Vercel，默认采用 Docker/Render/Railway 或自建容器服务进行部署；如需恢复 Vercel，请在仓库外部维护配置并自行适配流程。

## 运行环境
- Python 3.10+
- 依赖：`pip install -r requirements.txt`
- 前端模板在 `tools/templates/`，Flask 应用入口为 `tools/web_app.py`

## 本地启动
- `python tools/web_app.py`
- 浏览器访问 `http://localhost:5000/`

### 可选：macOS 本地自动推送到服务器（Launchd）
- 适用：本地开发频繁变更，希望自动 rsync 到远端并触发重建。
- 模板与说明：见 `docs/scripts/launchd_watchpush.plist.example` 与 `docs/scripts/README.md`。
- 要点：将模板中的 `{{PROJECT_ROOT}}` 替换为你的本地项目绝对路径；根据需要设置 `SERVER`、`REMOTE_DIR`、`PORT`、`GIT_ENABLE`。

## 容器化部署
- 构建镜像：`docker build -t script-analyzer:latest .`
- 运行容器：`docker run -p 5000:5000 -e FLASK_ENV=production script-analyzer:latest`

## 云部署（示例流程）
- 将镜像推送到云端镜像仓库（阿里云/腾讯云/华为云均可）
- 使用云主机或容器服务（ACK/TKE/CCE）拉取镜像并运行
- 配置域名与反向代理（Nginx）指向容器的 8000 端口
- 配置持久化存储挂载以保存上传的剧本与生成的 Excel

## 自动部署建议
- 使用 GitHub Actions 或 GitLab CI 在 push 时构建镜像并推送
- 云端使用镜像拉取触发（Webhook）自动滚动更新
- 保留滚动窗口与健康检查（/health 路由）

## 生产注意事项
- 限制文件上传大小与类型（txt/docx/pdf）
- PDF 无法解析时引导上传可解析文本版本
- 开启访问日志与错误监控，定期清理临时文件夹