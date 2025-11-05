FROM python:3.10-slim

# 国内网络加速：为 pip 指定镜像与更长超时，降低构建失败率
# 可通过 --build-arg 覆盖 PIP_INDEX_URL/PIP_TIMEOUT
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple
ARG PIP_TIMEOUT=180

# 环境设置：更快、更稳定的 Python 运行
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=5000

WORKDIR /app

# 仅复制依赖文件以利用 Docker 层缓存
COPY requirements.txt /app/requirements.txt
# 先升级 pip/setuptools/wheel，确保尽可能使用预编译二进制轮子
RUN pip install --no-cache-dir -U pip setuptools wheel \
 && pip install --no-cache-dir --prefer-binary --default-timeout=${PIP_TIMEOUT} -i ${PIP_INDEX_URL} --extra-index-url https://pypi.org/simple -r /app/requirements.txt

# 复制应用源码
COPY . /app

# 可选：预创建临时目录（上传/生成文件使用）
RUN mkdir -p /app/tmp

# 暴露默认端口（实际运行由平台传入 $PORT）
EXPOSE 5000

# 使用 gunicorn 启动 Flask 应用，兼容云平台注入的 $PORT
CMD ["sh", "-c", "gunicorn --workers 3 --timeout 120 --bind 0.0.0.0:${PORT:-5000} tools.web_app:app"]