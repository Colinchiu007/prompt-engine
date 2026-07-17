"""允许 python -m prompt_engine.api.rest 启动 REST 服务器"""
import uvicorn
from prompt_engine.config import load_config
from prompt_engine.api.rest import app


def main():
    config = load_config()
    server_config = config.get("server", {})
    host = server_config.get("host", "0.0.0.0")
    port = server_config.get("port", 8013)
    log_level = server_config.get("log_level", "info")

    uvicorn.run(app, host=host, port=port, log_level=log_level)


if __name__ == "__main__":
    main()
