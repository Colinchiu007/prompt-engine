# 构建视频知识库（一次性脚本，产出 keywords_video.json + seed_video_prompts.json）
import json
import re
from pathlib import Path

IMG_PROMPT = Path("C:/tmp/img-prompt-repo/src/app/data/prompt/prompt-zh.json")
AWESOME_VIDEO = Path("C:/tmp/awesome-video-prompts/README.md")
OUT = Path("video_prompt_engine/knowledge")

# 1) img-prompt 视频维度关键词
DIMENSION_MAP = {
    "动作": "action",
    "摄影": "camera",
    "光影效果": "lighting",
    "色彩氛围": "color",
    "艺术风格": "style",
    "环境": "scene",
    "素材": "material",
}
keywords = {}
if IMG_PROMPT.exists():
    items = json.loads(IMG_PROMPT.read_text(encoding="utf-8"))
    for item in items:
        obj = item.get("object", "")
        dim = DIMENSION_MAP.get(obj)
        if not dim:
            continue
        entry = {"zh": item.get("langName", ""), "en": item.get("displayName", "")}
        if not entry["zh"] and not entry["en"]:
            continue
        keywords.setdefault(dim, []).append(entry)
    print("img-prompt keywords by dimension:", {k: len(v) for k, v in keywords.items()})

# 2) awesome-video-prompts 结构化 JSON 种子
seeds = []
if AWESOME_VIDEO.exists():
    text = AWESOME_VIDEO.read_text(encoding="utf-8")
    # 提取 ```json ... ``` 块
    blocks = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    for i, block in enumerate(blocks):
        try:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("prompt") or (data.get("shot") or data.get("subject")):
                seeds.append({
                    "id": f"awv-{i:03d}",
                    "title": str(data.get("prompt", ""))[:60] or f"案例 {i}",
                    "description": "awesome-video-prompts 精选视频提示词",
                    "prompt_text": json.dumps(data, ensure_ascii=False),
                    "language": "en",
                    "platform": "generic_video",
                    "style": "video",
                    "categories": ["video", "cinematic"],
                    "quality_score": 8,
                    "source": "awesome-video-prompts",
                })
        except json.JSONDecodeError:
            continue
    print("awesome-video seeds:", len(seeds))

OUT.mkdir(parents=True, exist_ok=True)
(OUT / "keywords_video.json").write_text(json.dumps(keywords, ensure_ascii=False, indent=2), encoding="utf-8")
(OUT / "seed_video_prompts.json").write_text(json.dumps(seeds, ensure_ascii=False, indent=2), encoding="utf-8")
print("written:", OUT / "keywords_video.json", OUT / "seed_video_prompts.json")
