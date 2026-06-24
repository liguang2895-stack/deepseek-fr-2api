import argparse
import sys

import uvicorn

from deepseek_all_in_one.api import create_app
from deepseek_all_in_one.config import load_config
from deepseek_all_in_one.logging import configure_logging


def main():
    parser = argparse.ArgumentParser(description="DeepSeek de/es/fr OpenAI-compatible proxy")
    parser.add_argument("--config", "-c", default="config.toml", help="Path to config.toml")
    parser.add_argument("--host", help="Override bind host")
    parser.add_argument("--port", type=int, help="Override bind port")
    args = parser.parse_args()

    config = load_config(args.config)
    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    configure_logging(config.log_level)
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_config=None)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
