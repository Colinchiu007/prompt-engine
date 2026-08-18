"""允许 python -m prompt_engine.api.rest 启动 REST 服务器"""
import os

import logging
import uvicorn
from prompt_engine.config import load_config
from prompt_engine.api.rest import app


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    config = load_config()
    server_config = config.get("server", {})
    host = server_config.get("host", "0.0.0.0")
    # PORT 环境变量优先（BasePythonBridge 以 PORT 下发端口，与 splitter/server.py 约定一致），
    # 其次 config.yaml server.port，最后默认 8013
    port = int(os.environ.get("PORT", server_config.get("port", 8013)))
    log_level = server_config.get("log_level", "info")

    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
