# 国内镜像部署与智能解析指引（轻量服务器 + 分流）

本指南帮助你在国内轻量服务器上镜像部署，并通过智能 DNS 将中国大陆用户分流到国内镜像、其他用户走 Render 默认域名，从而实现更快更稳的访问体验。

---

## 一、准备工作

- 服务器：腾讯云轻量/阿里云 ECS/华为云，最低 1C2G/20G，Ubuntu 22.04 更佳。
- 域名：已备案更优（HTTP 可用，HTTPS 建议备案 + 申请证书）。
- 端口：开放 `80/443`（安全组 + 服务器防火墙）。
- 依赖：Docker 与 Compose 插件。

```bash
# Ubuntu 一键安装 Docker（官方脚本）
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker

# 验证
docker --version && docker compose version || echo "注意：新版本 Compose 是 docker 的插件形式"
```

---

## 二、拉取并启动（HTTP 版）

```bash
# 克隆仓库
cd ~ && git clone <你的Git仓库URL> jubenfenxi && cd jubenfenxi

# 启动（包含 app + nginx）
docker compose up -d

# 查看运行状态
docker compose ps
```

- 访问：`http://<服务器IP>/` 或绑定域名后 `http://<你的域名>/`
- 目录持久化：容器挂载了名为 `data` 的卷，应用将使用：
  - `EXCEL_PATH=/data/剧本评估表.xlsx`
  - `UPLOAD_DIR=/data/uploads`
- 首次运行若 `/data/剧本评估表.xlsx` 不存在，应用会自动复制模板到该位置。

---

## 三、启用 HTTPS（可选）

1) 使用 `certbot` 在宿主机申请证书（以 Nginx 为例）：

```bash
sudo apt update && sudo apt install -y certbot
# 使用 DNS 或临时 webroot 申请证书（需域名解析已指向服务器）
# 示例（将 Nginx 暂停并使用 standalone 模式）：
docker compose down
sudo certbot certonly --standalone -d example.com -d www.example.com

# 证书位置通常为：/etc/letsencrypt/live/example.com/
# 将证书拷贝到仓库中的 nginx/certs 目录（新建该目录）
mkdir -p nginx/certs
sudo cp /etc/letsencrypt/live/example.com/fullchain.pem nginx/certs/
sudo cp /etc/letsencrypt/live/example.com/privkey.pem  nginx/certs/
```

2) 将 `nginx/conf.d/se-ssl.conf.example` 重命名为 `se-ssl.conf` 并修改 `server_name`：

```bash
sed -i 's/example.com/你的域名/g' nginx/conf.d/se-ssl.conf.example
mv nginx/conf.d/se-ssl.conf.example nginx/conf.d/se-ssl.conf
```

3) 重启：

```bash
docker compose up -d
```

- 成功后：`https://你的域名/` 生效，`http` 自动 301 到 `https`。

---

## 四、智能解析分流（中国大陆 → 国内镜像，默认 → Render）

以阿里云云解析 / 腾讯云 DNSPod 为例（两者都支持“线路”/智能解析）：

- 目标：
  - `中国大陆` 线路：A 记录 → 你的国内服务器 IP
  - `默认` 线路：CNAME → `jubenfenxi.onrender.com`

- 步骤：
  1. 在“解析设置”中新建两条记录，主机记录均为 `@`（或你的二级域名）：
     - 记录 1：类型 `A`，值 `你的国内服务器IP`，线路/分组选择 `中国大陆`
     - 记录 2：类型 `CNAME`，值 `jubenfenxi.onrender.com`，线路选择 `默认`
  2. 保存并等待生效（通常 5–10 分钟）。

- 兼容性提示：
  - 个别 DNS 服务商可能要求同一主机记录的类型保持一致。若不支持混合类型，可采用“分域名”策略：
    - `cn.yourdomain.com` → A 记录指向国内服务器；
    - `global.yourdomain.com` → CNAME 指向 `jubenfenxi.onrender.com`；
    - 主域名 `yourdomain.com` 选择指向其中一个，并在前端做引导或自动跳转（可选）。

---

## 五、运维与调优

- 并发：默认 `gunicorn` 使用 `3 workers × 2 threads`，评分任务较重时可提升 workers（CPU 核心数的 1–2 倍）。
- 超时：Nginx `proxy_read_timeout 120s`，可根据文档长度与 PDF 解析时间调整。
- 存储：需要长期保存结果时，备份 Docker 卷 `data`（`docker run --rm -v data:/data busybox tar -cvf - /data > backup.tar`）。
- 日志：`docker compose logs -f app` 与 `docker compose logs -f nginx`。

---

## 六、常见问题

- 访问 Render 失败或慢：确认智能解析的“默认线路”是否为 CNAME 指向 Render 默认域名。
- HTTPS 证书加载失败：检查证书路径与权限，确保容器挂载目录与 Nginx 配置一致。
- 上传体积限制：修改 `nginx/conf.d/se.conf` 的 `client_max_body_size` 并重启。
- PDF 无法解析：界面允许提示并建议上传 `txt/docx` 可解析版本（功能已内置）。

---

## 七、回滚与更新

- 更新镜像：`git pull && docker compose up -d --build`
- 回滚：保留旧镜像标签或使用 Git 历史回退后重新构建。

---

如需我远程协助在你的国内服务器上执行上述步骤（SSH 登录），我可以代为完成安装、配置与上线验证，并设置智能解析分流。