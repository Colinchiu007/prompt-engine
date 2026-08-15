#!/usr/bin/env python
"""Golden set 校准（P2-5）：评估器分 vs 人工分 — MAE / RMSE / Pearson r + 逐条对比表。

用法：
    python scripts/eval_golden_set.py [--json]
退出码 0（可跑通即通过；分数是校准信息不是门禁）。
"""
import json
import math
import sys
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from video_prompt_engine.evaluator import evaluate


def pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    vx = sum((x - mx) ** 2 for x in xs)
    vy = sum((y - my) ** 2 for y in ys)
    if vx == 0 or vy == 0:
        return float("nan")
    return cov / math.sqrt(vx * vy)


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    gpath = root / "video_prompt_engine" / "knowledge" / "golden_set.json"
    data = json.loads(gpath.read_text(encoding="utf-8"))
    samples = data["samples"]

    rows = []
    for s in samples:
        info = evaluate(
            s["prompt_text"], {},
            source_prompt="", language=s.get("language", "en"),
            tier=s.get("tier"), length_strict=False,
        )
        human = float(s["human_score"])
        engine = float(info["score"])
        rows.append({
            "id": s["id"], "tier": s.get("tier"), "lang": s.get("language"),
            "words": s.get("words"), "human": human, "engine": engine,
            "delta": round(engine - human, 1),
        })

    deltas = [r["delta"] for r in rows]
    mae = sum(abs(d) for d in deltas) / len(deltas)
    rmse = math.sqrt(sum(d * d for d in deltas) / len(deltas))
    r_pearson = pearson([r["human"] for r in rows], [r["engine"] for r in rows])

    if "--json" in argv:
        print(json.dumps({
            "n": len(rows), "mae": round(mae, 2), "rmse": round(rmse, 2),
            "pearson": round(r_pearson, 3), "rows": rows,
        }, ensure_ascii=False, indent=2))
    else:
        print(f"{'id':<28}{'tier':<9}{'lang':<5}{'words':>6}{'human':>7}{'engine':>8}{'delta':>8}")
        for r in rows:
            print(f"{r['id']:<28}{r['tier']:<9}{r['lang']:<5}{r['words']:>6}{r['human']:>7.0f}{r['engine']:>8.1f}{r['delta']:>+8.1f}")
        print()
        print(f"n={len(rows)}  MAE={mae:.2f}  RMSE={rmse:.2f}  Pearson r={r_pearson:.3f}")
        print("golden set OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
