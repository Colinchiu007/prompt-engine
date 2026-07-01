"""启动 MCP Server"""
import asyncio
from prompt_engine.api.mcp_server import main


if __name__ == "__main__":
    asyncio.run(main())