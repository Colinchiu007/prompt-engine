"""Prompt Disturb — 借鉴 Infinity BSC 的扰动增强思路

Infinity BSC (Bitwise Self-Correction):
- 训练时随机翻转比特引入噪声
- 让模型学会自修正，缓解 train-test discrepancy

本项目将这一思路应用于 prompt 层面：
- 对 prompt 做同义词替换、句式打乱等扰动
- 生成增强样本提升优化器鲁棒性
- 支持可控的扰动强度
"""
import logging
import random
import re
from typing import Optional

logger = logging.getLogger(__name__)

# 常用英文同义词映射（简化版，实际可扩展）
EN_SYNONYMS = {
    "beautiful": ["stunning", "gorgeous", "magnificent", "lovely", "exquisite"],
    "big": ["large", "huge", "massive", "enormous", "immense"],
    "small": ["tiny", "little", "miniature", "petite", "compact"],
    "old": ["ancient", "vintage", "aged", "antique", "historic"],
    "new": ["modern", "contemporary", "fresh", "latest", "novel"],
    "happy": ["joyful", "cheerful", "delighted", "content", "blissful"],
    "sad": ["unhappy", "melancholy", "sorrowful", "gloomy", "somber"],
    "fast": ["quick", "rapid", "swift", "speedy", "fleet"],
    "slow": ["gradual", "leisurely", "unhurried", "lazy", "sluggish"],
    "bright": ["vivid", "radiant", "brilliant", "luminous", "glowing"],
    "dark": ["shadowy", "dim", "gloomy", "murky", "dimmed"],
    "hot": ["scorching", "burning", "sweltering", "toasty", "searing"],
    "cold": ["freezing", "chilly", "icy", "frigid", "frosty"],
    "good": ["excellent", "wonderful", "great", "fine", "superb"],
    "bad": ["terrible", "awful", "poor", "dreadful", "horrible"],
    "beautiful": ["beautiful", "stunning", "gorgeous", "magnificent", "lovely", "exquisite", "handsome"],
    "cute": ["adorable", "charming", "sweet", "endearing", "precious", "delightful"],
    "elegant": ["graceful", "refined", "sophisticated", "stylish", "classy"],
    "simple": ["simple", "basic", "clean", "minimal", "uncluttered"],
    "colorful": ["vibrant", "colorful", "brilliant", "rainbow", "multi-hued"],
    "mountain": ["mountain", "peak", "summit", "highland", "ridge"],
    "river": ["river", "stream", "creek", "brook", "waterway"],
    "forest": ["forest", "woods", "woodland", "grove", "jungle", "thicket"],
    "sun": ["sun", "sunlight", "sunbeam", "daylight", "radiance"],
    "moon": ["moon", "moonlight", "lunar", "silver moon"],
    "water": ["water", "liquid", "aqua", "clear water"],
    "flower": ["flower", "blossom", "bloom", "floret", "blossoms"],
    "tree": ["tree", "oak", "pine", "cedar", "maple"],
    "sky": ["sky", "heaven", "firmament", "blue sky"],
    "cloud": ["cloud", "clouds", "cumulus", "cirrus", "cloud formations"],
    "night": ["night", "nighttime", "darkness", "evening", "twilight"],
    "morning": ["morning", "dawn", "sunrise", "early morning", "daybreak"],
    "evening": ["evening", "dusk", "sunset", "twilight", "nightfall"],
}


def disturb_prompt(
    prompt: str,
    strength: float = 0.3,
    lang: str = "en",
    max_retries: int = 10,
) -> str:
    """对 prompt 进行可控扰动增强

    Args:
        prompt: 原始 prompt
        strength: 扰动强度 0.0-1.0，越大扰动越剧烈
        lang: 语言 "en" 或 "zh"
        max_retries: 同义词替换失败重试次数

    Returns:
        扰动后的 prompt（与原 prompt 不同）
    """
    prompt = prompt.strip()
    if not prompt:
        return prompt

    words = prompt.split()
    disturbed_words = list(words)
    num_to_change = max(1, int(len(words) * strength))

    # 随机选择要扰动的词
    change_indices = random.sample(range(len(words)), min(num_to_change, len(words)))

    for idx in change_indices:
        original = words[idx].lower()
        for _ in range(max_retries):
            if original in EN_SYNONYMS:
                synonyms = EN_SYNONYMS[original]
                candidate = random.choice([s for s in synonyms if s != original])
                # 保留原词的大小写风格
                if prompt[idx].isupper():
                    candidate = candidate.upper()
                elif prompt[idx].islower():
                    candidate = candidate.lower()
                disturbed_words[idx] = candidate
                break

    result = " ".join(disturbed_words)
    # 确保扰动后的结果与原 prompt 不同
    if result == prompt and strength > 0:
        # 如果没变化，随机调整词序
        shuffled = list(words)
        random.shuffle(shuffled)
        result = " ".join(shuffled)
        if result == prompt:
            result = prompt  # 万一 shuffle 也没变

    return result


class PromptDisturber:
    """Prompt 扰动器：生成增强 prompt 样本

    Args:
        strength: 基础扰动强度
        strategies: 启用的扰动策略列表
    """

    def __init__(
        self,
        strength: float = 0.3,
        strategies: Optional[list[str]] = None,
    ):
        self.strength = strength
        self.strategies = strategies or ["synonym", "shuffle"]

    def perturb(self, prompt: str) -> str:
        """对单个 prompt 应用扰动"""
        result = prompt
        if "synonym" in self.strategies:
            result = disturb_prompt(result, self.strength, max_retries=10)
        if "shuffle" in self.strategies and random.random() < 0.3:
            words = result.split()
            if len(words) > 3:
                random.shuffle(words)
                result = " ".join(words)
        return result

    def perturb_batch(
        self, prompts: list[str], num_augmented: int = 3
    ) -> dict[str, list[str]]:
        """对一批 prompt 生成增强样本

        Args:
            prompts: 原始 prompt 列表
            num_augmented: 每个 prompt 生成的增强版本数

        Returns:
            {original_prompt: [augmented_1, augmented_2, ...]}
        """
        results = {}
        for prompt in prompts:
            augmented = [self.perturb(prompt) for _ in range(num_augmented)]
            # 去重：确保增强样本不与原版和彼此重复
            augmented = list(dict.fromkeys(a for a in augmented if a != prompt))
            results[prompt] = augmented
        return results
