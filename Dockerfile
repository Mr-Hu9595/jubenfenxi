FROM python:3.10-slim

# 可选：设置国内镜像以加速构建（在 docker compose build 时通过 --build-arg 覆盖）
ARG APT_MIRROR=deb.debian.org
ARG SECURITY_MIRROR=security.debian.org
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TIMEOUT=60

# 环境准备：安装 Tesseract 及中文语言包
RUN set -eux; \
    # 加速与稳健：根据系统 sources 文件类型替换镜像源，并增加重试与超时配置
    SRC_LIST="/etc/apt/sources.list"; \
    SRC_DEB822="/etc/apt/sources.list.d/debian.sources"; \
    if [ -f "$SRC_LIST" ]; then \
        sed -i "s|deb.debian.org|${APT_MIRROR}|g" "$SRC_LIST"; \
        sed -i "s|security.debian.org|${SECURITY_MIRROR}|g" "$SRC_LIST"; \
    elif [ -f "$SRC_DEB822" ]; then \
        sed -i "s|deb.debian.org|${APT_MIRROR}|g" "$SRC_DEB822"; \
        sed -i "s|security.debian.org|${SECURITY_MIRROR}|g" "$SRC_DEB822"; \
    fi; \
    printf 'Acquire::Retries "5";\nAcquire::http::Timeout "20";\nAcquire::https::Timeout "20";\n' > /etc/apt/apt.conf.d/99retry; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-chi-sim; \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 安装依赖
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip \
    && pip install --no-cache-dir -i ${PIP_INDEX_URL} --default-timeout ${PIP_TIMEOUT} -r requirements.txt

# 复制项目代码
COPY . /app

# 运行时配置
ENV DATA_DIR=/data \
    UPLOAD_DIR=/data/uploads \
    HOST=0.0.0.0 \
    PORT=8080

EXPOSE 8080

# 使用 Gunicorn 启动 Flask 应用
CMD ["gunicorn", "-c", "gunicorn.conf.py", "tools.web_app:app"]