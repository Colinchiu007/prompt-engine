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

from video_prompt_engine.models import VideoPlatformType, VIDEO_DIRECTOR_LIMITS

_DIRECTOR_LIMITS = VIDEO_DIRECTOR_LIMITS

# 镜头字段 camera/shot 长度对齐模型层（VideoBeat/VideoShot max_length=50），与契约 VIDEO_ENGINE_LIMITS 无对应上限
_CAMERA_MAX = 50

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


def _clean_aspect(value: Any) -> str:
    """画面比例归一：数字:数字(可选:数字)，非法或超长（>10 字符超出 VideoPromptMeta.aspect max_length）回退默认 16:9。"""
    import re
    raw = str(value or "").strip()
    if re.fullmatch(r"\d+:\d+(?::\d+)?", raw) and len(raw) <= 10:
        return raw
    return "16:9"


def _clean_audio(value: Any) -> str:
    """音频提示归一：strip 截断 50，空回退默认 SFX（对齐契约 appendVideoTrailer）。"""
    cleaned = str(value or "").strip()[:50]
    return cleaned or "SFX"


def _clean_str_list(value: Any, limit: int) -> list[str]:
    """字符串列表清洗：仅保留 strip 后非空项，截断到 limit。"""
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v or "").strip()][:limit]


def _clean_swap_pairs(value: Any, limit: int) -> list[dict]:
    """禁止替换对清洗：兼容对象 {"from","to"} 与二元组 [from, to]（契约规范形态）；
    两端均须为 strip 后非空字符串（数字等非字符串丢弃，对齐契约 _normalizeNoSwapPairs），截断到 limit。"""
    if not isinstance(value, list):
        return []
    pairs: list[dict] = []
    for item in value:
        if isinstance(item, dict):
            src_raw, dst_raw = item.get("from"), item.get("to")
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            src_raw, dst_raw = item[0], item[1]
        else:
            continue
        src = str(src_raw).strip() if isinstance(src_raw, str) else ""
        dst = str(dst_raw).strip() if isinstance(dst_raw, str) else ""
        if src and dst:
            pairs.append({"from": src, "to": dst})
        if len(pairs) >= limit:
            break
    return pairs


def _clean_color_ratio(value: Any) -> str:
    """色彩配比归一：三段 1-999 正整数（对齐契约格式），非法或超长（>20 字符超出 VideoPromptMeta.color_ratio max_length）回退默认 60:30:10。"""
    import re
    raw = str(value or "").strip()
    if re.fullmatch(r"\d{1,3}:\d{1,3}:\d{1,3}", raw) and len(raw) <= 20:
        return raw
    return "60:30:10"


def _clean_shots(value: Any) -> list[dict]:
    """镜头单元清洗：≤3 镜头，duration 钳 1-15，beats ≤6 且 time/action/camera 清洗。"""
    if not isinstance(value, list):
        return []
    shots: list[dict] = []
    for item in value[: _DIRECTOR_LIMITS["shots_max"]]:
        if not isinstance(item, dict):
            continue
        beats: list[dict] = []
        for beat in (item.get("beats") or [])[: _DIRECTOR_LIMITS["beats_per_shot_max"]]:
            if not isinstance(beat, dict):
                continue
            b = {
                "time": str(beat.get("time") or "").strip()[:_DIRECTOR_LIMITS["beat_time_max"]],
                "action": str(beat.get("action") or "").strip()[:_DIRECTOR_LIMITS["beat_action_max"]],
                "camera": str(beat.get("camera") or "").strip()[:_CAMERA_MAX],  # 对齐 VideoBeat.camera max_length=50，防止 pydantic 炸
            }
            if b["time"] and b["action"]:
                beats.append(b)
        duration = item.get("duration")
        try:
            duration_f = float(duration) if duration is not None and str(duration).strip() != "" else 5.0
        except (TypeError, ValueError):
            duration_f = 5.0
        shot = {
            "shot": str(item.get("shot") or "").strip()[:_CAMERA_MAX],  # 对齐 VideoShot.shot max_length=50
            "camera": str(item.get("camera") or "").strip()[:_CAMERA_MAX],  # 对齐 VideoShot.camera max_length=50
            "duration": max(1.0, min(_DIRECTOR_LIMITS["shot_duration_max"], duration_f)),
            "beats": beats,
        }
        if shot["shot"]:
            shots.append(shot)
    return shots


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
        tier: str = "batch",
    ) -> str:
        raise NotImplementedError

    @classmethod
    def build_language_section(cls, output_language: str = "en", tier: str = "batch") -> str:
        """输出语言指令段：zh=中文主体 + 镜头术语双语；en=英文 prose。

        refined 层长度口径与 Director Workflow 一致（500-5000 中文字符），避免与 batch 的 150-300 词冲突（W8）。
        """
        if str(output_language or "en").lower().startswith("zh"):
            length_note = (
                "equivalent to 500+ English words (500-5000 Chinese chars)"
                if tier == "refined"
                else "equivalent to 150-300 English words"
            )
            return (
                "\n## Output Language (MANDATORY)\n"
                f"- The `prompt` field MUST be written primarily in Chinese (中文) flowing prose, rich and detailed ({length_note}).\n"
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
            # --- Higgsfield 导演维度：全字段钳制/裁剪/清洗，非法值回退默认（C3）---
            "aspect": _clean_aspect(data.get("aspect")),
            "audio": _clean_audio(data.get("audio")),
            "excluded_characters": _clean_str_list(data.get("excluded_characters"), _DIRECTOR_LIMITS["excluded_characters_max"]),
            "no_swap_pairs": _clean_swap_pairs(data.get("no_swap_pairs"), _DIRECTOR_LIMITS["no_swap_pairs_max"]),
            "color_ratio": _clean_color_ratio(data.get("color_ratio")),
            "shots": _clean_shots(data.get("shots")),
            "positive_constraints": constraints,
            "final_frame": str(data.get("final_frame") or "").strip()[:500],  # 对齐 VideoPromptMeta.final_frame max_length=500
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
    def build_tail(cls, meta: dict[str, Any]) -> str:
        """refined 收尾行模板（与契约层 appendVideoTrailer 一致）：
        `Photoreal. NON-IP. {aspect}. {duration}s. {audio} only.`"""
        aspect = _clean_aspect((meta or {}).get("aspect"))
        audio = _clean_audio((meta or {}).get("audio"))
        duration = (meta or {}).get("duration_hint")
        try:
            # 默认 15 对齐契约 appendVideoTrailer（duration 缺失时同一兜底值，防跨仓漂移）
            dur = int(float(duration)) if duration is not None and str(duration).strip() != "" else 15
        except (TypeError, ValueError):
            dur = 15
        return f"Photoreal. NON-IP. {aspect}. {dur}s. {audio} only."

    @classmethod
    def append_trailer(cls, rendered: str, meta: dict[str, Any], tier: str = "batch") -> str:
        """refined 层追加收尾行；幂等：body 已含 NON-IP 标记（LLM 直出或契约层已 append）则不重复。"""
        text = str(rendered or "").rstrip()
        if tier != "refined" or not text:
            return text
        # 幂等：body 已含 NON-IP 标记（LLM 直出或契约层已 append）；词边界整名匹配 + 大小写不敏感，防双写
        import re
        if re.search(r"(?<![A-Za-z0-9])non-ip", text, flags=re.IGNORECASE):
            return text
        return f"{text} {cls.build_tail(meta)}"

    @classmethod
    def build_higgsfield_section(cls, tier: str = "batch") -> str:
        """Higgsfield 导演工作流指令段：refined 层多镜头/禁止项/尾行；batch 层允许空并禁止尾行。"""
        if tier == "refined":
            return (
                "\n## Director Workflow (Higgsfield-style, MANDATORY for refined)\n"
                "- `excluded_characters`: array of ≤10 characters/elements that MUST NOT appear in the video (e.g. [\"background crowd\"]); empty array if none.\n"
                "- `no_swap_pairs`: array of ≤5 pairs {\"from\": ..., \"to\": ...} — the `to` character MUST replace `from` and `from` MUST NEVER appear (identity-swap guard).\n"
                "- `color_ratio`: color proportion as \"60:30:10\" (three integer parts) matching the dominant palette.\n"
                "- `shots`: array of ≤3 shot units; each shot has `shot` (id), `camera` (one of the camera motions), `duration` (1-15 seconds), and `beats` (≤6 timed blocks {\"time\": \"0:00-0:04\", \"action\": ..., \"camera\": ...}).\n"
                "- The rendered `prompt` MUST be a long, detailed single-string description (500+ English words / 500-5000 Chinese chars) covering ALL shots.\n"
                "- Reference protocol (MANDATORY): whenever `excluded_characters` or `no_swap_pairs` is non-empty, the rendered `prompt` body MUST embed at least one reference marker `[ABSENT] <name>` (or `<<<...>>>`) so the ban is visibly enforced — e.g. `hero walks. [ABSENT] JAX stays off-frame` or `crowd removed [ABSENT] background crowd`. Never declare a ban without marking it in the text.\n"
                "- The rendered `prompt` MUST end with the exact trailer line: `Photoreal. NON-IP. {aspect}. {duration}s. {audio} only.` (fill from `aspect` / `duration_hint` / `audio` fields).\n"
                "- Keep the trailer EXACTLY as specified; do not append anything after it."
            )
        return (
            "\n## Director Workflow (batch mode)\n"
            "- Multi-shot planning is NOT required: `shots` may be an empty array unless the input explicitly describes multiple scenes.\n"
            "- `excluded_characters` / `no_swap_pairs` / `color_ratio` are optional; use empty array / default \"60:30:10\" when not applicable.\n"
            "- Reference protocol (MANDATORY): if `excluded_characters` / `no_swap_pairs` is non-empty, the rendered `prompt` body MUST embed at least one reference marker `[ABSENT] <name>` (or `<<<...>>>`) — declared bans must be visibly enforced in the text.\n"
            "- Do NOT append any trailer line in batch mode."
        )

    @classmethod
    def post_process_video(cls, raw_output: str, creative_level: int = 5, tier: str = "batch") -> tuple[str, dict[str, Any]]:
        data = cls.parse_video_json(raw_output)
        if data is None:
            rendered = str(raw_output or "").strip().strip('"').strip()
            return rendered, {}
        rendered = cls.render(data)
        meta = cls.extract_video_meta(raw_output) or {}
        # C6 生命周期：render body → append 尾行 → 再交 optimizer 按预算截断（tail 永不截断）
        rendered = cls.append_trailer(rendered, meta, tier)
        return rendered, meta
