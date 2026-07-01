"""Prompt 数据模型"""
from dataclasses import dataclass, field


@dataclass
class PromptEntry:
    """单条 prompt 记录"""
    id: str
    title: str
    description: str
    prompt_text: str
    language: str = "en"           # en / zh
    categories: list[str] = field(default_factory=list)
    platform: str = "generic"      # midjourney / sd / dalle / ...
    style: str = ""                # realistic / anime / ...
    quality_score: int = 5         # 1-10 质量评分