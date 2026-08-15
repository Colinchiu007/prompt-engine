"""语料目录合并 + 校验门禁（video-corpus-expansion 组2）。

用法：
  python scripts/build_corpus_index.py [--corpus-dir DIR ...] [--output FILE] [--strict]

- glob 合并 corpus 目录下全部 *.json（支持多目录），统一去重（prompt_text 保留首条）
- 校验：必填 id/prompt_text/language/tier；prompt_text >= 50 字符；tier 白名单；
  quality_score 0-10；corpus_type/applicable_to 白名单（缺失按 positive/few-shot 归一）
- 默认模式：违规条目跳过 + 汇总 warning，仍产出归一化合并产物
- --strict：任一 error fail-closed，不产出（exit 1）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

DEFAULT_CORPUS_DIRS = ["video_prompt_engine/knowledge/corpus"]
DEFAULT_OUTPUT = "video_prompt_engine/knowledge/corpus_index.json"

TIER_WHITELIST = {"refined", "batch", "variant", "asset"}
CORPUS_TYPE_WHITELIST = {"positive", "negative"}
APPLICABLE_WHITELIST = {"few-shot", "eval", "both"}

OUTPUT_FIELDS = [
    "id", "title", "description", "prompt_text", "language", "platform", "style",
    "categories", "quality_score", "source", "corpus_type", "failure_tags",
    "applicable_to", "tier", "meta",
]


def _validate(item: dict, idx: int, path: str, errors: list[str]) -> bool:
    """单条目校验；违规写入 errors 并返回 False（默认模式跳过该条目，--strict 直接失败）。"""
    def _err(msg: str) -> None:
        errors.append(f"{path}#{idx} ({item.get('id', '?')}): {msg}")
    ok = True

    for field in ("id", "prompt_text", "language", "tier"):
        if not str(item.get(field) or "").strip():
            _err(f"missing required field: {field}")
            ok = False
    text = str(item.get("prompt_text") or "")
    if len(text.strip()) < 50:
        _err(f"prompt_text too short ({len(text.strip())} < 50 chars)")
        ok = False
    tier = str(item.get("tier") or "")
    if tier not in TIER_WHITELIST:
        _err(f"tier '{tier}' not in {sorted(TIER_WHITELIST)}")
        ok = False
    qs = item.get("quality_score", 5)
    if qs is not None and not (isinstance(qs, (int, float)) and 0 <= float(qs) <= 10):
        _err(f"quality_score out of range 0-10: {qs!r}")
        ok = False
    ctype = item.get("corpus_type", "positive")
    if ctype not in CORPUS_TYPE_WHITELIST:
        _err(f"corpus_type '{ctype}' not in {sorted(CORPUS_TYPE_WHITELIST)}")
        ok = False
    applicable = item.get("applicable_to", "few-shot")
    if applicable not in APPLICABLE_WHITELIST:
        _err(f"applicable_to '{applicable}' not in {sorted(APPLICABLE_WHITELIST)}")
        ok = False
    return ok


def _normalize(item: dict) -> dict:
    """归一输出：补齐默认字段 + 仅保留白名单字段（未知字段不流入引擎）。"""
    out = {f: item.get(f) for f in OUTPUT_FIELDS if f in item}
    out.setdefault("title", "")
    out.setdefault("description", "")
    out.setdefault("language", "en")
    out.setdefault("platform", "generic_video")
    out.setdefault("style", "")
    out.setdefault("categories", [])
    out.setdefault("quality_score", 5)
    out.setdefault("source", "")
    out.setdefault("corpus_type", "positive")
    out.setdefault("failure_tags", [])
    out.setdefault("applicable_to", "few-shot")
    out.setdefault("tier", "")
    # 只有显式 negative 才是负样本；applicable_to 非法值按 few-shot 归一（loader 同规则）
    if out["corpus_type"] not in CORPUS_TYPE_WHITELIST:
        out["corpus_type"] = "positive"
    if out["applicable_to"] not in APPLICABLE_WHITELIST:
        out["applicable_to"] = "few-shot"
    if not isinstance(out["failure_tags"], list):
        out["failure_tags"] = [str(out["failure_tags"])] if out["failure_tags"] else []
    meta = out.get("meta")
    if meta is not None and not isinstance(meta, dict):
        out["meta"] = {}
    return out


def build(corpus_dirs: list[Path], output: Path, strict: bool = False) -> int:
    errors: list[str] = []
    seen: dict[str, dict] = {}
    per_file: dict[str, int] = {}

    for base in corpus_dirs:
        if not base.exists():
            if strict:
                errors.append(f"corpus dir not found: {base}")
            else:
                print(f"[warn] corpus dir not found, skipped: {base}")
            continue
        for path in sorted(base.rglob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError) as e:
                errors.append(f"{path}: unreadable JSON ({e})")
                continue
            items = raw if isinstance(raw, list) else [raw]
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    errors.append(f"{path}#{idx}: not an object")
                    continue
                if not _validate(item, idx, str(path), errors):
                    continue  # 违规条目默认模式跳过（--strict 时整体失败不产出）
                key = str(item.get("prompt_text") or "").strip()
                if not key:
                    continue  # 必填校验已报
                if key not in seen:
                    seen[key] = _normalize(item)
            per_file[str(path)] = len(items)

    n_raw = sum(per_file.values())
    n_out = len(seen)
    tier_dist: dict[str, int] = {}
    neg_count = 0
    for item in seen.values():
        tier_dist[item["tier"]] = tier_dist.get(item["tier"], 0) + 1
        if item["corpus_type"] == "negative":
            neg_count += 1

    if errors and strict:
        print(f"[strict] {len(errors)} validation error(s), no output written:")
        for e in errors:
            print(f"  - {e}")
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(list(seen.values()), ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"corpus index written: {output} ({n_out} entries, {n_raw - n_out} duplicates dropped)")
    print(f"  tier dist: {tier_dist}")
    print(f"  negative samples: {neg_count}")
    if errors:
        print(f"[warn] {len(errors)} entry error(s) skipped (use --strict to fail):")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="语料目录合并 + 校验门禁")
    ap.add_argument("--corpus-dir", action="append", default=[], help="corpus 目录（可重复/逗号分隔）")
    ap.add_argument("--output", default=DEFAULT_OUTPUT)
    ap.add_argument("--strict", action="store_true", help="fail-closed：任一校验错误即不产出")
    args = ap.parse_args(argv)

    dirs: list[Path] = []
    for raw in args.corpus_dir or DEFAULT_CORPUS_DIRS:
        for part in raw.split(","):
            part = part.strip()
            if part:
                dirs.append(Path(part))
    return build(dirs, Path(args.output), strict=args.strict)


if __name__ == "__main__":
    sys.exit(main())
