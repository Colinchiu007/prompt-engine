"""Prompt Rewriter — 扩写短提示词为详细描述（灵感来自 Infinity 项目）

借鉴 Infinity 的 prompt_rewriter.py 设计：
- LLM 将简短 prompt 扩写为详细、具体的图像生成描述
- 支持 <prompt:xxx><cfg:xxx> 格式输出
- cfg 参数启发式判断（人脸类 vs 非人脸类）
- Few-shot history 模板引导风格
"""
import logging
import time
from typing import Optional

from prompt_engine.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are part of a team of bots that creates images. You work with an assistant bot that will draw anything you say. "
    "For example, outputting the prompt and parameters like \"<prompt:a beautiful morning in the woods with the sun peaking through the trees><cfg:3>\" "
    "will trigger your partner bot to output an image of a forest morning, as described. "
    "You will be prompted by users looking to create detailed, amazing images. The way to accomplish this is to refine their short prompts and make them extremely detailed and descriptive.\n"
    "- You will only ever output a single image description sentence per user request.\n"
    "- Each image description sentence should be consist of \"<prompt:xxx><cfg:xxx>\", where <prompt:xxx> is the image description, <cfg:xxx> is the parameter that control the image generation.\n"
    "Here are the guidelines to generate image description <prompt:xxx> :\n"
    "- Refine users' prompts and make them extremely detailed and descriptive but keep the meaning unchanged (very important).\n"
    "- For particularly long users' prompts (>50 words), they can be outputted directly without refining. Image descriptions must be between 8-512 words. Extra words will be ignored.\n"
    "- If the user's prompt requires rendering text, enclose the text with single quotation marks and prefix it with \"the text\".\n"
    "Here are the guidelines to set <cfg:xxx> :\n"
    "- Please first determine whether the image to be generated based on the user prompt is likely to contain a clear face. If it does, set <cfg:1>; if not, set <cfg:3>."
)

FEW_SHOT_HISTORY = [
    {"role": "user", "content": "a tree"},
    {"role": "assistant", "content": "<prompt:A photo of a majestic oak tree stands proudly in the middle of a sunlit meadow, its branches stretching out like welcoming arms. The leaves shimmer in shades of vibrant green, casting dappled shadows on the soft grass below.><cfg:3>"},
    {"role": "user", "content": "a young girl with red hair"},
    {"role": "assistant", "content": "<prompt:A young girl with vibrant red hair, close-up face, in the style of hyper-realistic portraiture, warm and inviting atmosphere, soft lighting, freckles, vintage effect><cfg:1>"},
    {"role": "user", "content": "a man, close-up"},
    {"role": "assistant", "content": "<prompt:close-up portrait of a young man with freckles and curly hair, in the style of chiaroscuro, strong light and shadow contrast, intense gaze, background fades into darkness><cfg:1>"},
    {"role": "user", "content": "Generate Never Stop Learning"},
    {"role": "assistant", "content": "<prompt:Generate an image with the text 'Never Stop Learning' in chalkboard style.><cfg:3>"},
]


class PromptRewriter:
    """Prompt 扩写器：将简短描述扩展为详细图像生成提示词"""

    def __init__(self, provider: BaseLLMProvider, max_retries: int = 3):
        self._provider = provider
        self._max_retries = max_retries
        self._system = SYSTEM_PROMPT
        self._few_shot = FEW_SHOT_HISTORY

    def rewrite(self, prompt: str) -> str:
        """扩写 prompt，返回 <prompt:xxx><cfg:xxx> 格式
        
        Args:
            prompt: 原始简短提示词
            
        Returns:
            扩写后的详细 prompt（带 cfg 参数），出错时返回原始 prompt
        """
        messages = (
            [{"role": "system", "content": self._system}]
            + self._few_shot
            + [{"role": "user", "content": prompt}]
        )

        for attempt in range(self._max_retries):
            try:
                response, _ = self._provider.chat(messages)
                result = response.strip()
                # 验证输出格式
                if "<prompt:" in result and "<cfg:" in result:
                    return result
                logger.warning("Rewriter output missing format tags (attempt %d): %s", attempt + 1, result[:100])
            except Exception as e:
                logger.error("Rewriter call failed (attempt %d/%d): %s", attempt + 1, self._max_retries, e)
                if attempt < self._max_retries - 1:
                    time.sleep(1)
                continue

        logger.error("Rewriter failed after %d attempts, returning original prompt", self._max_retries)
        return prompt

    def rewrite_raw(self, prompt: str) -> str:
        """扩写 prompt，返回纯文本描述（去掉 <prompt:>/<cfg:> 标签）
        
        Args:
            prompt: 原始简短提示词
            
        Returns:
            扩写后的纯文本描述
        """
        formatted = self.rewrite(prompt)
        # 提取 <prompt:xxx> 中的内容
        start = formatted.find("<prompt:") + len("<prompt:")
        end = formatted.find(">", start)
        if start > 0 and end > start:
            return formatted[start:end]
        return formatted
