"""Vercel Serverless 入口 — 加载配置并暴露 FastAPI app。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from deepseek_all_in_one.api import create_app
from deepseek_all_in_one.config import load_config

# Vercel 环境变量覆盖
config = load_config("config.toml")
if os.environ.get("PROXY_URL"):
    config.proxy_url = os.environ["PROXY_URL"]

app = create_app(config)
