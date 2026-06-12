"""MCP Server — 通过 Model Context Protocol 暴露提示词优化 + 风格分类工具"""
from functools import lru_cache
from typing import Optional
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
from prompt_engine.models import OptimizeRequest, PlatformType, StyleType, ReverseRequest, AutoStyleRequest
from prompt_engine.optimizer import Optimizer
from prompt_engine.classifier import StyleCategoryClassifier

server = Server("prompt-engine")


@lru_cache
def get_optimizer() -> Optimizer:
    return Optimizer()


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="optimize_prompt",
            description="优化图片生成提示词。输入用户原始提示词，输出适用于目标平台的优化版提示词。自动检测风格类别。",
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
                        "description": "艺术风格（可选，留空则自动检测）: realistic, cartoon, anime, oil_painting, watercolor, cyberpunk, fantasy, photography",
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
                    "num_candidates": {
                        "type": "integer",
                        "description": "候选版本数量 1-5（A/B 测试）",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="reverse_prompt",
            description="从图片 URL 逆向生成提示词。分析图片内容，生成适用于目标平台的提示词。（需视觉模型支持）",
            inputSchema={
                "type": "object",
                "properties": {
                    "image_url": {
                        "type": "string",
                        "description": "图片 URL",
                    },
                    "platform": {
                        "type": "string",
                        "description": "目标平台: midjourney, stable_diffusion, dalle, tongyi, yizhang, jimeng, generic",
                        "default": "generic",
                    },
                    "style": {
                        "type": "string",
                        "description": "艺术风格（可选）",
                        "default": None,
                    },
                },
                "required": ["image_url"],
            },
        ),
        types.Tool(
            name="classify_style",
            description="MJ 风格分类：将提示词自动分配到 27 个风格维度（光照/材质/色彩/镜头/构图/自然/艺术媒介/文化风格等）。零样本，无需训练。",
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "待分析的提示词文本",
                    },
                    "max_categories": {
                        "type": "integer",
                        "description": "最多返回几个风格类别（1-10）",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                    },
                },
                "required": ["prompt"],
            },
        ),
        types.Tool(
            name="list_style_categories",
            description="列出所有可用的 MJ 风格分类维度（27 个）及其中文描述",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    """执行 MCP Tool 调用"""
    if name == "optimize_prompt":
        return await _handle_optimize(arguments)
    elif name == "reverse_prompt":
        return await _handle_reverse(arguments)
    elif name == "classify_style":
        return await _handle_classify(arguments)
    elif name == "list_style_categories":
        return await _handle_list_categories()
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _handle_optimize(arguments: dict) -> list[types.TextContent]:
    prompt = arguments.get("prompt", "")
    platform_str = arguments.get("platform", "generic")
    style_str = arguments.get("style")
    creative_level = arguments.get("creative_level", 5)
    negative_prompt = arguments.get("negative_prompt")
    num_candidates = arguments.get("num_candidates", 1)

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
        negative_prompt=negative_prompt or "",
        num_candidates=num_candidates,
        auto_detect_style=True,
    )

    optimizer = get_optimizer()
    result = optimizer.optimize(request)

    if result.error:
        return [types.TextContent(
            type="text",
            text=f"优化失败: {result.error}\n原始提示词: {result.optimized_prompt}",
        )]

    parts = [result.optimized_prompt]
    if result.detected_categories and result.detected_categories.categories:
        cats = ", ".join(c.value for c in result.detected_categories.categories)
        parts.append(f"\n\n[检测到的风格维度: {cats}, 置信度: {result.detected_categories.confidence:.2f}]")

    return [types.TextContent(type="text", text="".join(parts))]


async def _handle_reverse(arguments: dict) -> list[types.TextContent]:
    image_url = arguments.get("image_url", "")
    platform_str = arguments.get("platform", "generic")
    style_str = arguments.get("style")

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

    request = ReverseRequest(
        image_url=image_url,
        platform=platform,
        style=style,
    )

    optimizer = get_optimizer()
    result = optimizer.reverse_engineer(request)

    if result.error:
        return [types.TextContent(type="text", text=f"逆向失败: {result.error}")]

    return [types.TextContent(type="text", text=result.prompt)]


async def _handle_classify(arguments: dict) -> list[types.TextContent]:
    prompt = arguments.get("prompt", "")
    max_categories = arguments.get("max_categories", 5)

    classifier = StyleCategoryClassifier()
    result = classifier.classify(prompt=prompt, max_categories=max_categories)

    if not result.categories:
        return [types.TextContent(
            type="text",
            text=f"未识别到明显的风格维度。\n方法: {result.method}",
        )]

    lines = [
        f"风格分类结果 — 方法: {result.method}, 置信度: {result.confidence:.2f}",
        "",
    ]
    for cat in result.categories:
        kws = result.keywords_found.get(cat.value, [])
        kw_str = f" (关键词: {', '.join(kws)})" if kws else ""
        lines.append(f"  • {cat.value}{kw_str}")

    lines.append(f"\n共 {len(result.categories)} 个风格维度")
    return [types.TextContent(type="text", text="\n".join(lines))]


async def _handle_list_categories() -> list[types.TextContent]:
    from prompt_engine.models import StyleCategory
    names = {
        "lighting": "光照效果",
        "material_properties": "材质属性",
        "materials": "材料",
        "dimensionality": "维度感",
        "colors_and_palettes": "色彩与调色板",
        "combinations": "色彩组合",
        "camera": "相机/镜头",
        "perspective": "视角/透视",
        "structural_modification": "结构变形",
        "nature_and_animals": "自然与动物",
        "objects": "物体",
        "outer_space": "太空",
        "geometry": "几何形状",
        "geography_and_culture": "地理与文化",
        "drawing_and_art_mediums": "绘画与艺术媒介",
        "sfx_and_shaders": "特效与着色器",
        "themes": "主题/氛围",
        "intangibles": "抽象概念",
        "tv_and_movies": "影视参考",
        "song_lyrics": "歌词风格",
        "design_styles": "设计风格",
        "digital": "数字艺术",
        "experimental": "实验风格",
        "emojis": "Emoji 风格",
        "miscellaneous": "杂项",
    }
    lines = [f"MJ 风格分类维度（共 {len(StyleCategory)} 个）:", ""]
    for cat in sorted(StyleCategory, key=lambda c: c.value):
        cn = names.get(cat.value, "")
        lines.append(f"  • {cat.value:35s} {cn}")
    return [types.TextContent(type="text", text="\n".join(lines))]


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
