"""Higgsfield 语料分析（Round3 C 前置）：分族统计 12 块频率 / lock 词否定出现率，产出 refined_blocks.json。

用法：python scripts/analyze_hg_corpus.py [corpus_dir] [output_path]
- corpus_dir 默认 D:\\Temp\\hg-corpus（只读，永不写入）
- output_path 默认 video_prompt_engine/knowledge/refined_blocks.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BLOCKS = (
    "SCENE NOTE", "SPATIAL LAYOUT", "LIGHTING", "COLOR", "CAMERA",
    "ENVIRONMENT", "CONTINUITY", "CHARACTERS", "SKIN", "ACTING",
    "STILLNESS LOCK", "FINAL FRAME",
)

# 统一块检测正则：行首大写标题+冒号（引擎渲染形态）；🔥 导演族 emoji 变体（语料形态）
BLOCK_RE = re.compile(r"(?m)^\s*(?:🔥\s*)?([A-Z][A-Z ]{2,30}?)(?:\s*🔥)?\s*:")
BLOCK_EMOJI_RE = re.compile(r"🔥\s*([A-Z][A-Z ]{2,30}?)\s*🔥")

# 引擎渲染形态判定：行首标题+冒号（覆盖度口径）
RENDER_BLOCK_RE = re.compile(r"(?m)^([A-Z][A-Z ]{2,30}):\s*")

LOCK_TRIGGERS = {
    "warm_light_leak": {"locks": ["cold", "cool palette", "冷色"], "forbidden": ["warm", "amber", "golden", "暖色"]},
    "dead_center": {"locks": ["rule of thirds", "golden ratio", "三分法"], "forbidden": ["center of frame", "dead center"]},
    "exposure_break": {"locks": ["low-key", "low light", "dark", "低光"], "forbidden": ["bright daylight", "overexposed", "high-key"]},
    "silhouette_break": {"locks": ["silhouette", "剪影"], "forbidden": ["well-lit face", "clear facial detail"]},
    "style_contamination": {"locks": ["hyper-realistic", "photorealistic detail", "写实"], "forbidden": ["anime", "cartoon", "3d render", "动漫"]},
    "skin_guard": {"locks": ["pore-level", "skin", "皮肤"], "forbidden": ["plastic skin", "waxy", "塑料"]},
    "eye_line": {"locks": ["eye-line", "eye line", "视线"], "forbidden": ["looking at camera", "breaking the fourth wall"]},
}

NEGATION = re.compile(r"(?i)(?:no|not|without|never|avoid|无|不|禁止|切勿)")


def iter_prompts(corpus_dir: Path):
    for path in sorted(corpus_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[skip] {path.name}: {e}", file=sys.stderr)
            continue
        for item in data.get("items", []):
            prompt = (item.get("job") or {}).get("params") or {}
            text = prompt.get("prompt")
            if isinstance(text, str) and text.strip():
                yield path.stem, text


def detect_blocks(text: str) -> set[str]:
    """块标题提取：行首冒号形态 + 🔥 emoji 形态合并。"""
    found = {m.group(1).strip() for m in BLOCK_RE.finditer(text)}
    found |= {m.group(1).strip() for m in BLOCK_EMOJI_RE.finditer(text)}
    return {b for b in found if b in BLOCKS}


def main() -> int:
    corpus_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"D:\Temp\hg-corpus")
    out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else (
        Path(__file__).resolve().parent.parent / "video_prompt_engine" / "knowledge" / "refined_blocks.json"
    )
    if not corpus_dir.exists():
        print(f"corpus dir not found: {corpus_dir}", file=sys.stderr)
        return 1

    prompts = list(iter_prompts(corpus_dir))
    print(f"corpus: {len(prompts)} prompts from {corpus_dir}")

    family_director = 0
    family_inline = 0
    block_freq = Counter()
    block_hits_dist = Counter()
    render_hits_dist = Counter()
    forbidden_negation: dict[str, Counter] = defaultdict(Counter)
    forbidden_pos: dict[str, Counter] = defaultdict(Counter)
    lock_stat: dict[str, Counter] = defaultdict(Counter)

    for stem, text in prompts:
        blocks = detect_blocks(text)
        if any(b in blocks for b in ("SCENE NOTE", "STILLNESS LOCK", "CHARACTERS", "ACTING")):
            family_director += 1
        else:
            family_inline += 1
        block_freq.update(blocks)
        block_hits_dist[len(blocks)] += 1
        render_hits = {m.group(1).strip() for m in RENDER_BLOCK_RE.finditer(text)} & set(BLOCKS)
        render_hits_dist[len(render_hits)] += 1

        low = text.lower()
        for name, rule in LOCK_TRIGGERS.items():
            for lock in rule["locks"]:
                if lock.lower() in low:
                    lock_stat[name]["lock"] += 1
                    break
            for forbidden in rule["forbidden"]:
                count = low.count(forbidden.lower())
                if count:
                    forbidden_pos[name][forbidden] += count
                    # 否定感知：统计该 forbidden 在否定上下文中的出现次数（前后 16 字符窗口）
                    for m in re.finditer(re.escape(forbidden), low, flags=re.IGNORECASE):
                        window = low[max(0, m.start() - 16):m.end()]
                        if NEGATION.search(window):
                            forbidden_negation[name][forbidden] += 1

    total = len(prompts)
    block_freq_pct = {b: round(block_freq[b] / total * 100, 1) for b in BLOCKS} if total else {}
    print("\n== block frequency (% of prompts) ==")
    for b in BLOCKS:
        print(f"  {b:16s} {block_freq_pct[b]:5.1f}%")
    print(f"\nfamilies: director(🔥)={family_director} inline={family_inline}")
    print("block count distribution:", dict(sorted(block_hits_dist.items())))
    print("render-form count distribution:", dict(sorted(render_hits_dist.items())))

    print("\n== forbidden negation stats (positive vs negated) ==")
    coverage_notes: dict[str, dict] = {}
    for name, rule in LOCK_TRIGGERS.items():
        pos = dict(forbidden_pos[name])
        neg = dict(forbidden_negation[name])
        coverage_notes[name] = {"positive": pos, "negated": neg, "lock_seen": lock_stat[name].get("lock", 0)}
        print(f"  {name}: {coverage_notes[name]}")

    asset = {
        "version": 2,
        "source": "higgsfield hell-grind public corpus (read-only)",
        "corpus_prompts": total,
        "family": {"director": family_director, "inline": family_inline},
        "blocks": list(BLOCKS),
        "block_pattern": "^([A-Z][A-Z ]+):\\s*",
        "block_frequency_pct": block_freq_pct,
        "coverage": {"min_blocks": 10, "min_ratio": 0.8},
        "enabled_rules": ["dead_center", "exposure_break", "eye_line"],
        "lock_triggers": LOCK_TRIGGERS,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(asset, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nwritten: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())