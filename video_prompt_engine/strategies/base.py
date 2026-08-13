"""视频策略基类 — 每个视频平台继承此类（独立实现，机制与图片引擎一致）。

职责：
- build_system_prompt：平台指令（含 Fact-Fidelity 与镜头语言）
- post_process_video：LLM 结构化输出 → (渲染单串, 结构化字段 dict)
- extract_video_meta / render：结构化字段提取与单串渲染
- @register 自动注册 + get_strategy 查询
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from video_prompt_engine.models import VideoPlatformType

_REGISTRY: dict[str, type["BaseVideoStrategy"]] = {}


def register(platform: str):
    """策略注册装饰器。"""
    def decorator(cls):
        _REGISTRY[platform] = cls
        return cls
    return decorator


def get_strategy(platform: str) -> type["BaseVideoStrategy"] | None:
    return _REGISTRY.get(str(platform or "").lower())


def list_strategies() -> list[str]:
    return sorted(_REGISTRY.keys())


def _clamp_int(value: Any, lo: int = 1, hi: int = 10, default: int = 5) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(lo, min(hi, n))


class BaseVideoStrategy(ABC):
    """视频策略基类。"""

    domain = "video"
    platform: VideoPlatformType = VideoPlatformType.GENERIC_VIDEO

    @classmethod
    @abstractmethod
    def build_system_prompt(
        cls,
        style: Optional[str] = None,
        creative_level: int = 5,
        max_length: int = 500,
        negative_prompt: Optional[str] = None,
        keywords_hint: str = "",
        output_language: str = "en",
    ) -> str:
        raise NotImplementedError

    @classmethod
    def build_language_section(cls, output_language: str = "en") -> str:
        """输出语言指令段：zh=中文主体 + 镜头术语双语；en=英文 prose。"""
        if str(output_language or "en").lower().startswith("zh"):
            return (
                "\n## Output Language (MANDATORY)\n"
                "- The `prompt` field MUST be written primarily in Chinese (中文) flowing prose, rich and detailed (equivalent to 150-300 English words).\n"
                "- Camera/shot/lighting terms MAY be bilingual (e.g. 中景 medium shot, 推镜 dolly-in, 金色时刻 golden hour).\n"
                "- Structured fields `shot` / `camera` / `scene_transition` MUST remain English enum values; `prompt` is the only Chinese field."
            )
        return (
            "\n## Output Language (MANDATORY)\n"
            "- The `prompt` field MUST be written in English flowing prose.\n"
            "- Structured fields `shot` / `camera` / `scene_transition` MUST remain English enum values."
        )

    @classmethod
    def build_negative_section(cls, negative_prompt: Optional[str]) -> str:
        if not negative_prompt:
            return ""
        return f"\n## Avoid these elements / 避免元素\n- {negative_prompt}\n生成内容不得包含这些元素。"

    @classmethod
    def parse_video_json(cls, raw_output: str) -> dict[str, Any] | None:
        import json
        import re
        text = str(raw_output or "").strip()
        if not text:
            return None
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return None
        return data if isinstance(data, dict) else None

    @classmethod
    def render(cls, data: dict[str, Any]) -> str:
        prompt = str(data.get("prompt") or "").strip()
        if prompt:
            return prompt
        parts = []
        for key in ("subject", "action", "environment", "colors", "lighting", "style"):
            val = str(data.get(key) or "").strip()
            if val:
                parts.append(val)
        return " ".join(parts)

    @classmethod
    def extract_video_meta(cls, raw_output: str) -> dict[str, Any] | None:
        data = cls.parse_video_json(raw_output)
        if data is None:
            return None
        duration = data.get("duration_hint")
        try:
            duration_f = float(duration) if duration is not None and str(duration).strip() != "" else None
        except (TypeError, ValueError):
            duration_f = None
        constraints = cls._coerce_constraints(data.get("positive_constraints"))
        return {
            "shot": str(data.get("shot") or "").strip(),
            "camera": str(data.get("camera") or "").strip(),
            "motion_intensity": _clamp_int(data.get("motion_intensity")),
            "scene_transition": str(data.get("scene_transition") or "").strip(),
            "continuity_token": str(data.get("continuity_token") or "").strip(),
            "duration_hint": duration_f,
            "positive_constraints": constraints,
            "final_frame": str(data.get("final_frame") or "").strip()[:500],
        }

    @staticmethod
    def _coerce_constraints(value: Any) -> list[str]:
        """positive_constraints 双形态兼容：数组透传；字符串按换行/分号拆分。上限 10 条。"""
        if isinstance(value, list):
            items = [str(c).strip() for c in value if str(c).strip()]
        elif isinstance(value, str):
            import re
            items = [c.strip() for c in re.split(r"[\n;]+", value) if c.strip()]
        else:
            items = []
        return items[:10]

    @classmethod
    def build_lens_discipline_section(cls, character_count: Optional[int] = None) -> str:
        """镜头纪律公共模板（六平台共用）：角色数锁定/单镜单运镜/三角色上限/正负向分块/最终画面/负面 plausible-only。"""
        count_line = ""
        if character_count is not None and character_count > 0:
            count_line = f'- Open with "EXACT {character_count} CHARACTERS — ..." to lock the on-screen character count (N = {character_count} from provided context).\n'
        return (
            "\n## Lens Discipline (MANDATORY)\n"
            + count_line
            + "- One primary camera move per shot; add \"slow\" unless the action demands speed; never stack multiple camera moves in one clip.\n"
            "- At most 3 recognizable characters across cuts; describe extras as generic background figures.\n"
            "- Positive constraints (STRICT block: what MUST happen) and negative constraints (what must NOT happen) MUST be written in separate blocks.\n"
            "- Every clip ends with an explicit FINAL FRAME: subject position, pose, lighting state, whether the camera rests, and a no-text statement.\n"
            "## Negative Prompt Discipline (MANDATORY)\n"
            "- List only plausible failure classes: identity/costume drift, duplicate characters, anatomy errors, reference background bleed, location/lighting shifts, unwanted text/logos/subtitles/watermarks, unwanted style.\n"
            "- Never pile up absolute negations the model ignores; if a failure is not plausible for this shot, omit it."
        )

    @classmethod
    def post_process_video(cls, raw_output: str, creative_level: int = 5) -> tuple[str, dict[str, Any]]:
        data = cls.parse_video_json(raw_output)
        if data is None:
            rendered = str(raw_output or "").strip().strip('"').strip()
            return rendered, {}
        rendered = cls.render(data)
        meta = cls.extract_video_meta(raw_output) or {}
        return rendered, meta
