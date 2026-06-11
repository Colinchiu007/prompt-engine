"""MCP Server — 通过 Model Context Protocol 暴露提示词优化工具"""
from functools import lru_cache
from typing import Optional
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from prompt_engine.models import OptimizeRequest, PlatformType, StyleType
from prompt_engine.optimizer import Optimizer

server = Server("prompt-engine")


@lru_cache
def get_optimizer() -> Optimizer:
    return Optimizer()


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """注册 MCP Tool"""
    return [
        types.Tool(
            name="optimize_prompt",
            description="优化图片生成提示词。输入用户原始提示词，输出适用于目标平台的优化版提示词。",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "原始提示词（中文/英文）",
                    },
                    "platform": {
                        "type": "string",
                        "description": "目标平台: midjourney, stable_diffusion, dalle, tongyi, yizhang, jimeng, generic",
                        "default": "generic",
                    },
                    "style": {
                        "type": "string",
                        "description": "艺术风格: realistic, cartoon, anime, oil_painting, watercolor, cyberpunk, fantasy, photography",
                        "default": None,
                    },
                    "creative_level": {
                        "type": "integer",
                        "description": "创意程度 1-10",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                    },
                    "negative_prompt": {
                        "type": "string",
                        "description": "负面提示词，避免的元素（可选）",
                        "default": None,
                    },
                },
                "required": ["prompt"],
            },
        )
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict
) -> list[types.TextContent]:
    """执行 MCP Tool 调用"""
    if name != "optimize_prompt":
        raise ValueError(f"Unknown tool: {name}")

    prompt = arguments.get("prompt", "")
    platform_str = arguments.get("platform", "generic")
    style_str = arguments.get("style")
    creative_level = arguments.get("creative_level", 5)
    negative_prompt = arguments.get("negative_prompt")

    try:
        platform = PlatformType(platform_str)
    except ValueError:
        platform = PlatformType.GENERIC

    style = None
    if style_str:
        try:
            style = StyleType(style_str)
        except ValueError:
            pass

    request = OptimizeRequest(
        prompt=prompt,
        platform=platform,
        style=style,
        creative_level=creative_level,
        negative_prompt=negative_prompt,
    )

    optimizer = get_optimizer()
    result = optimizer.optimize(request)

    if result.error:
        return [types.TextContent(
            type="text",
            text=f"优化失败: {result.error}\n原始提示词: {result.optimized_prompt}",
        )]

    return [types.TextContent(
        type="text",
        text=result.optimized_prompt,
    )]


async def main():
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="prompt-engine",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )