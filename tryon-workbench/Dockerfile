# node:22-alpine, same base as the main application.
FROM node:22-alpine@sha256:76789712cd1ae89a1225eac9077010d68987a423588042dac30446f502f1858c AS realtime-builder
WORKDIR /build
COPY package.json package-lock.json ./
COPY scripts ./scripts
RUN npm ci --no-audit --no-fund && npm run build

# python:3.11-slim (reviewed 2026-08-12; linux/amd64 digest)
FROM python:3.11-slim@sha256:78b39ef14d8e2b4d71f8dc304f1328c37df95fe0ef99477c2ae6bd3d03784553

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装系统依赖 (Pillow 需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libjpeg-dev \
    zlib1g-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制并安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .
COPY --from=realtime-builder /build/static/vendor/decart-sdk.js ./static/vendor/decart-sdk.js
COPY --from=realtime-builder /build/static/vendor/xmax-sdk ./static/vendor/xmax-sdk
COPY --from=realtime-builder /build/static/vendor/reactor-sdk.js ./static/vendor/reactor-sdk.js

# 创建必要目录
RUN mkdir -p uploads assets history

# 启动命令
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips=* --ws-max-size 524288
