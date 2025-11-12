import multiprocessing

bind = "0.0.0.0:8080"
workers = max(2, multiprocessing.cpu_count() // 2)
threads = 4
timeout = 180
keepalive = 2
graceful_timeout = 30
loglevel = "info"
accesslog = "-"
errorlog = "-"

# 兼容容器内路径与挂载目录，确保文件上传与数据持久化
raw_env = [
    "DATA_DIR=/data",
    "UPLOAD_DIR=/data/uploads",
]