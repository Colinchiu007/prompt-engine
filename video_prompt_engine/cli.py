"""CLI：python -m video_prompt_engine 启动独立服务（默认 8020）。"""
from __future__ import annotations

import argparse

from video_prompt_engine.config import load_config


def main():
    parser = argparse.ArgumentParser(description="独立视频提示词优化引擎")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--build-kb", action="store_true", help="构建视频知识库索引")
    args = parser.parse_args()

    if args.build_kb:
        from video_prompt_engine.knowledge.build import build_knowledge_base
        n = build_knowledge_base()
        print(f"video knowledge base built: {n} entries")
        return

    cfg = load_config()
    host = args.host or cfg["server"]["host"]
    port = args.port or cfg["server"]["port"]
    import uvicorn
    uvicorn.run("video_prompt_engine.api.rest:app", host=host, port=port)


if __name__ == "__main__":
    main()
