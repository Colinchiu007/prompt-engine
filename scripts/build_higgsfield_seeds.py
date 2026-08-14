"""Higgsfield 公开语料 → 视频引擎 few-shot 种子库生成（DEEP P2.9 语料资产化）。

从 D:/Temp/hg-corpus/*.json（Higgsfield 公开文件夹 API 抓取，598 条有效提示词）
提取视频相关语料，按视频引擎种子格式生成 seed_higgsfield_prompts.json 并提交入库。

用法：
    python scripts/build_higgsfield_seeds.py [corpus_dir] [out_path]

- 幂等：覆盖式写目标文件；产物确定性（按文件夹+序号排序）
- 平台映射：seedance_2_0 → seedance；其余视频模型 → generic_video；纯图像模型剔除
- 层级标签：按文件夹分桶（Scene_74/74C/15-16/Orphanage=精修，Scene_17/13/14/18=批量，
  Cinema_Bomb/Credits/Cold_Open=变体，Assets=资产卡），未知文件夹按长度兜底
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

IMAGE_MODELS = ("imagegen_2_0", "gpt_image_2", "text2image_soul_v2")
VIDEO_MODELS = {"seedance_2_0": "seedance"}  # 其余视频模型映射 generic_video

TIER_FOLDERS = {
    "Scene_74": "refined", "Scene_74C": "refined", "Scene_15-16": "refined",
    "Scene_Orphanage": "refined",
    "Scene_17": "batch", "Scene_13": "batch", "Scene_14": "batch", "Scene_18": "batch",
    "Cinema_Bomb": "variant", "Credits": "variant", "1._COLD_OPEN": "variant",
    "Assets": "asset",
}
QUALITY_BY_TIER = {"refined": 8, "batch": 7, "variant": 7, "asset": 8}
MIN_PROMPT_LEN = 50


def folder_name(filename: str) -> str:
    """文件名 → 文件夹名（剥离 8 位 hex 前缀，如 34c88b2f_Assets.json → Assets）。"""
    stem = Path(filename).stem
    return re.sub(r"^[0-9a-f]{8}_", "", stem)


def tier_for(folder: str, length: int) -> str:
    if folder in TIER_FOLDERS:
        return TIER_FOLDERS[folder]
    if length > 10000:
        return "refined"
    if length > 2000:
        return "batch"
    return "asset"


def extract(corpus_dir: Path) -> list[dict]:
    """抓取产物 → 原始条目（剔除纯图像模型与过短文本）。"""
    extracted = []
    for f in sorted(glob.glob(str(corpus_dir / "*.json"))):
        folder = folder_name(os.path.basename(f))
        data = json.loads(Path(f).read_text(encoding="utf-8"))
        for item in data.get("items") or []:
            job = item.get("job") or {}
            params = job.get("params") or {}
            prompt = params.get("prompt") or ""
            job_type = job.get("job_set_type") or ""
            if len(prompt) <= MIN_PROMPT_LEN or job_type in IMAGE_MODELS:
                continue
            slug = re.sub(r"[^a-z0-9_]+", "_", folder.lower()).strip("_") or "folder"
            extracted.append({
                "folder": folder,
                "slug": slug,
                "tier": tier_for(folder, len(prompt)),
                "platform": VIDEO_MODELS.get(job_type, "generic_video"),
                "model": job_type,
                "prompt": prompt,
            })
    return extracted


def build_entries(extracted: list[dict]) -> list[dict]:
    """原始条目 → 种子格式（id=hg-<slug>-<seq>，title=<folder> #<seq>，确定性排序）。

    prompt_text 去重（W5）：同 prompt 不同 job 参数的变体对 few-shot/向量检索无增量价值，
    反而稀释 IDF、膨胀体积；保留首条，seq 仍按文件夹计数保持确定性。
    """
    per_folder: Counter = Counter()
    entries = []
    seen_prompts: set[str] = set()
    for x in extracted:
        if x["prompt"] in seen_prompts:
            continue
        seen_prompts.add(x["prompt"])
        per_folder[x["folder"]] += 1
        seq = per_folder[x["folder"]]
        entries.append({
            "id": f"hg-{x['slug']}-{seq:03d}",
            "title": f"{x['folder']} #{seq}",
            "description": "higgsfield-corpus",
            "prompt_text": x["prompt"],
            "language": "en",
            "platform": x["platform"],
            "style": "",
            "categories": ["higgsfield", f"tier:{x['tier']}", f"model:{x['model']}", x["slug"]],
            "quality_score": QUALITY_BY_TIER[x["tier"]],
            "source": "higgsfield-corpus",
        })
    return entries


def main(argv: list[str]) -> int:
    corpus_dir = Path(argv[1]) if len(argv) > 1 else Path(r"D:\Temp\hg-corpus")
    out_path = Path(argv[2]) if len(argv) > 2 else (
        Path(__file__).resolve().parent.parent / "video_prompt_engine" / "knowledge" / "seed_higgsfield_prompts.json"
    )
    if not corpus_dir.exists():
        print(f"corpus dir not found: {corpus_dir}", file=sys.stderr)
        return 1
    extracted = extract(corpus_dir)
    entries = build_entries(extracted)
    out_path.write_text(
        json.dumps(entries, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    tiers = Counter(e["categories"][1] for e in entries)
    models = Counter(e["categories"][2] for e in entries)
    total = sum(len(e["prompt_text"]) for e in entries)
    print(f"corpus: {len(extracted)} prompts → seeds: {len(entries)} → {out_path}")
    print("tiers:", dict(tiers))
    print("models:", dict(models))
    print(f"total chars: {total:,}  file size: {out_path.stat().st_size / 1024 / 1024:.1f}MB")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))