FROM python:3.13-slim

WORKDIR /app

# 安装系统依赖（curl-cffi 需要 libcurl）
RUN apt-get update && apt-get install -y --no-install-recommends libcurl4-openssl-dev && rm -rf /var/lib/apt/lists/*

# 复制源码
COPY pyproject.toml uv.lock* ./
COPY plugins/ plugins/
COPY deepseek_all_in_one/ deepseek_all_in_one/
COPY main.py config.toml ./

# 安装 uv 并同步依赖
RUN pip install --no-cache-dir uv && uv sync --frozen --no-dev

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["uv", "run", "python", "main.py"]
