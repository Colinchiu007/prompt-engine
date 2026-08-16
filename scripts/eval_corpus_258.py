#!/usr/bin/env python
"""258 语料哨兵门禁（Round3 P0-3）：seed_higgsfield_prompts.json 全量复测，防评估器回归。

用法：
    python scripts/eval_corpus_258.py [--json]
退出码：0=通过 / 1=门禁失败 / 2=输入错误

口径（与 scripts/eval_golden_set.py 同风格）：
- 固定路径读种子文件（断言 total==258），不读 corpus_index.json——「基线所测即所守」
- auto tier、length_strict=False；三路语言判定（CJK→zh / 西里尔→ru / else en），
  修复旧 retest 脚本把 3 条 ru 当 en 按词数刻度评分的已知缺陷

首版门禁阈值（宽带宽）：
- round3 前基线（2026-08-16 实测）：n=258 mean=92.3 ge90=213 ge80=221 lt60=20 missing_audio=25
- round3 重定基（v0.12 实测）：mean=91.0 ge90=216 ge80=225 lt60=20 missing_audio=20
  （mean -1.3 为无 source 缩放封顶的设计意图；ge90/ge80 上行来自 zh 长度兜底修复；
  missing_audio -5 来自 refined 中文音频意图词修复）
- 门禁：mean>=88.0 / ge90>=190 / lt60<=30 / missing_audio<=40（后续收紧需以重定基值写死）
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_prompt_engine.evaluator import evaluate, detect_lang

# 首版门禁阈值（先宽后紧：挡住真实回归，不拦合法分数重构）
_GATE = {"mean_min": 88.0, "ge90_min": 190, "lt60_max": 30, "missing_audio_max": 40}
_EXPECT_TOTAL = 258


def pick_text(item) -> str:
    if isinstance(item, dict):
        return item.get("prompt_text") or item.get("prompt") or ""
    return str(item)


def compute_metrics(items: list, evaluate_fn=evaluate) -> dict:
    """对语料逐条 evaluate（auto tier, length_strict=False），聚合哨兵指标。"""
    scores: list[float] = []
    missing_audio = 0
    for item in items:
        text = pick_text(item)
        if not text:
            continue
        result = evaluate_fn(
            text, {}, source_prompt="",
            language=detect_lang(text), tier=None, length_strict=False,
        )
        scores.append(float(result["score"]))
        if "missing_audio" in result["violations"]:
            missing_audio += 1
    n = len(scores)
    if n == 0:
        return {"n": 0, "error": "no samples"}
    return {
        "n": n,
        "mean": round(sum(scores) / n, 1),
        "median": round(statistics.median(scores), 1),
        "ge90": sum(1 for s in scores if s >= 90),
        "ge80": sum(1 for s in scores if s >= 80),
        "lt60": sum(1 for s in scores if s < 60),
        "missing_audio": missing_audio,
    }


def check_gate(metrics: dict, gate: dict | None = None) -> list[str]:
    """门禁判定：返回失败清单（空 = 通过）。total==258 为硬断言（语料被误改即基线漂移）。"""
    gate = gate or _GATE
    failures: list[str] = []
    if metrics.get("n", 0) != _EXPECT_TOTAL:
        failures.append(f"n={metrics.get('n')} != {_EXPECT_TOTAL}")
    if metrics.get("mean", 0) < gate["mean_min"]:
        failures.append(f"mean={metrics.get('mean')} < {gate['mean_min']}")
    if metrics.get("ge90", 0) < gate["ge90_min"]:
        failures.append(f"ge90={metrics.get('ge90')} < {gate['ge90_min']}")
    if metrics.get("lt60", 0) > gate["lt60_max"]:
        failures.append(f"lt60={metrics.get('lt60')} > {gate['lt60_max']}")
    if metrics.get("missing_audio", 0) > gate["missing_audio_max"]:
        failures.append(f"missing_audio={metrics.get('missing_audio')} > {gate['missing_audio_max']}")
    return failures


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    corpus = root / "video_prompt_engine" / "knowledge" / "seed_higgsfield_prompts.json"
    try:
        data = json.loads(corpus.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        # 评审 I1：语料损坏（JSON 语法/编码错误）同样按输入错误返回 2，而非裸 traceback
        print(f"input error: cannot read {corpus}: {exc}", file=sys.stderr)
        return 2
    items = data if isinstance(data, list) else data.get("seeds", data.get("items", []))
    metrics = compute_metrics(items)
    failures = check_gate(metrics)
    ok = not failures
    if "--json" in argv:
        print(json.dumps({"ok": ok, "metrics": metrics, "failures": failures}, ensure_ascii=False, indent=2))
    else:
        print(
            f"n={metrics['n']} mean={metrics['mean']} median={metrics['median']} "
            f"ge90={metrics['ge90']} ge80={metrics['ge80']} lt60={metrics['lt60']} "
            f"missing_audio={metrics['missing_audio']}"
        )
        if failures:
            print("GATE FAILED:")
            for item in failures:
                print(f"  - {item}")
        else:
            print("corpus-258 sentinel OK")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
