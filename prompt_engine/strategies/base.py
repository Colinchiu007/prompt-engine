"""平台策略基类 + 注册表（复用共享内核注册器）"""
from abc import ABC, abstractmethod
from prompt_engine.models import PlatformType, StyleType
from prompt_engine_core.registry import StrategyRegistry

# 策略注册表（共享内核泛型注册器；_strategies 为兼容别名，供既有测试直读内部存储）
_registry: StrategyRegistry[type["BaseStrategy"]] = StrategyRegistry()
_strategies = _registry._registry


def register(platform: str):
    """装饰器：注册平台策略"""
    return _registry.register(platform)


def get_strategy(platform: str) -> type["BaseStrategy"] | None:
    """获取已注册的策略类"""
    return _registry.get(platform)


def list_strategies(domain: str | None = None) -> list[str]:
    """列出已注册的平台；缺省按图片领域过滤（保持历史行为），domain='video' 列出视频平台。

    按注册（插入）顺序返回，与旧实现 _strategies.items() 一致（core items() 保序）。
    """
    return [name for name, cls in _registry.items() if getattr(cls, "domain", "image") == (domain or "image")]


class BaseStrategy(ABC):
    """策略基类 — 每个平台继承此类"""

    platform: PlatformType = PlatformType.GENERIC
    domain: str = "image"  # 优化领域：image（默认）/ video

    @classmethod
    def post_process_video(cls, raw_output: str, creative_level: int = 5) -> tuple[str, dict]:
        """视频领域专用后处理：返回 (渲染单串, 结构化字段 dict)。

        图片策略默认回退 post_process（兼容）；视频策略应覆盖此方法。
        """
        rendered = cls.post_process(raw_output, creative_level=creative_level)
        return rendered, {}

    @classmethod
    @abstractmethod
    def build_system_prompt(
        cls,
        style: StyleType | None = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: str | None = None,
    ) -> str:
        """构建系统提示词，指导 LLM 按照平台规则输出"""
        raise NotImplementedError

    @classmethod
    def build_negative_section(cls, negative_prompt: str | None) -> str:
        """构建负面提示词段落"""
        if not negative_prompt:
            return ""
        return f"\n9. **避免以下元素**：{negative_prompt}。生成的内容中不得包含这些元素。"

    @classmethod
    @abstractmethod
    def post_process(cls, raw_output: str, creative_level: int = 5,
                     preferred_categories: list[str] | None = None) -> str:
        """后处理：清理、格式化 LLM 原始输出。

        Args:
            raw_output: LLM 原始输出
            creative_level: 创意等级 (1-10)，用于控制风格关键词注入强度
            preferred_categories: 可选，MJ 风格类别列表（风格感知注入用）
        """
        raise NotImplementedError