"""评估器 P0-P2 优化回归（2026-08-15）：tier 兜底/form 形态/英文保真/运镜拆分/部分命中/长度梯度/词表资产化/FP 去重/advice。"""
import pytest

from video_prompt_engine.evaluator import (
    evaluate, select_best, evaluate_negatives, detect_tier,
)
from prompt_engine_core.knowledge import load_element_keywords


# ─────────────────────────── 组1：tier/form（P0-1 + P2-1） ───────────────────────────

class TestTierForm:
    def test_auto_tier_long_prompt_refined(self):
        # >833 词且无引擎标记 → 长度兜底 refined（P0-2 遗留项）
        long = " ".join(f"word{i}" for i in range(900))
        assert detect_tier(long, None) == "refined"

    def test_auto_tier_short_prompt_batch(self):
        assert detect_tier("A man walks in the city. " * 4, None) == "batch"

    def test_auto_tier_marker_still_refined(self):
        assert detect_tier("word " * 200 + " Photoreal. NON-IP. 16:9.", None) == "refined"

    def test_short_prompt_form_asset_no_length_fail(self):
        # <100 词 → form=asset，评测口径长度不判失败（length_strict=False）
        r = evaluate("A documentary photo of a war memorial. " * 3, {}, "", "en", tier=None)
        assert r["checks"]["form"] == "asset"
        assert r["tier"] == "batch"
        assert r["checks"]["length"] is False          # 真实判定保留
        assert "length" not in r["violations"]          # 评测口径不扣分

    def test_explicit_tier_asset_length_ok(self):
        r = evaluate("A tiny asset card prompt. " * 4, {}, "", "en", tier="asset")
        assert r["tier"] == "asset"
        assert r["checks"]["length"] is True

    def test_explicit_tier_variant_length_ok(self):
        r = evaluate("A variant with more detail and color. " * 8, {}, "", "en", tier="variant")
        assert r["tier"] == "variant"
        assert r["checks"]["length"] is True

    def test_invalid_tier_falls_back_auto(self):
        assert detect_tier("A man walks. " * 4, None, explicit_tier="bogus") == "batch"

    def test_regular_form_normal_batch(self):
        r = evaluate("A man walks in a neon city at night. " * 15, {}, "", "en")
        assert r["checks"]["form"] == "regular"


# ─────────────────────────── 组3：英文保真 + 运镜拆分（P0-3 + P0-4） ───────────────────────────

class TestFidelityAndMotion:
    def test_en_fidelity_entities_hit(self):
        src = "The white robot mech stands in the snow, holding a rifle."
        kept = "The white robot mech stands in the snow, holding a rifle. " + "detail " * 20
        r = evaluate(kept, {}, src, "en", tier="batch")
        assert r["checks"]["fidelity"] >= 0.8

    def test_en_fidelity_entities_miss(self):
        src = "The white robot mech stands in the snow."
        unrelated = "A red car drives on a highway. " * 8
        r = evaluate(unrelated, {}, src, "en", tier="batch")
        assert r["checks"]["fidelity"] <= 0.4

    def test_en_fidelity_no_entities_no_penalty(self):
        src = "the and of in on a an"  # 全停用词 → 无实体 → 不扣分
        r = evaluate("A random scene description. " * 5, {}, src, "en", tier="batch")
        assert r["checks"]["fidelity"] == 1.0

    def test_motion_not_from_subject_action(self):
        # 主体运动不算镜头运动（P0-4：walking/running/moving 移出运镜词表）
        r = evaluate("A man walking and running through the city, moving fast. " * 3,
                     {}, "", "en", tier="batch")
        assert r["checks"]["has_motion"] is False

    def test_motion_from_camera_terms(self):
        r = evaluate("A slow tracking dolly shot following the hero, camera pans. " * 3,
                     {}, "", "en", tier="batch")
        assert r["checks"]["has_motion"] is True


# ─────────────────────────── 组4：区分度（P1-1 + P1-2） ───────────────────────────

class TestDiscrimination:
    def test_element_partial_hit_score(self):
        # 单要素 1 词命中 → 部分命中 score≈0.333
        r = evaluate("A robot stands here. " * 4, {}, "", "en", tier="batch")
        d = r["checks"]["elements_detail"]
        assert d["subject"]["score"] == pytest.approx(1 / 3, abs=0.01)
        assert d["subject"]["hit"]            # 布尔语义保留
        assert r["checks"]["elements"]["subject"] is True

    def test_element_full_hit_score(self):
        r = evaluate("A heroic warrior robot in the ruined city, neon light, red and gold palette, cinematic style. " * 2,
                     {}, "", "en", tier="batch")
        d = r["checks"]["elements_detail"]
        assert d["subject"]["score"] == pytest.approx(1.0, abs=0.01)
        assert d["color"]["score"] == pytest.approx(1.0, abs=0.01)

    def test_length_gradient_outside_band(self):
        # length_strict=False：带外 50% 带宽 → 长度分 ≈10（20 × (1-0.5)）
        # batch en 带宽 = hi-100；hi 默认 400 → 带宽 300；dist=150 → 10 分
        # 550 词：band=[100,400]，dist=150 → ratio=0.5 → length_points=10
        prompt = " ".join(f"w{i}" for i in range(550)) + " cinematic neon city." * 3
        r = evaluate(prompt, {}, "", "en", tier="batch", length_strict=False)
        assert r["checks"]["length"] is False
        assert r["checks"]["length_points"] == pytest.approx(10.0, abs=2.0)

    def test_length_strict_true_still_binary(self):
        r = evaluate("A tiny card. " * 5, {}, "", "en", tier="batch", length_strict=True)
        assert r["checks"]["length_points"] == 0
        r2 = evaluate("A full scene with hero and action. " * 20, {}, "", "en", tier="batch", length_strict=True)
        assert r2["checks"]["length_points"] == 20


# ─────────────────────────── 组5：词表资产化（P1-4 + P2-2） ───────────────────────────

class TestElementKeywordsAsset:
    def test_asset_schema_six_elements_three_langs(self):
        kw, from_asset = load_element_keywords()
        assert from_asset is True
        # 必含 6 要素（loader 允许扩展第 7 要素，评审复验 Info）
        assert {"subject", "action", "environment", "lighting", "color", "style"} <= set(kw.keys())
        for elem, langs in kw.items():
            for lang in ("en", "zh", "ru"):
                assert langs.get(lang), f"{elem}.{lang} 为空"

    def test_ru_keyword_hits(self):
        # 俄语词命中（P2-2 多语种）
        r = evaluate("Персонаж в городе, свет, стиль нуар. " * 4, {}, "", "ru", tier="batch")
        d = r["checks"]["elements_detail"]
        assert d["subject"]["hit"] is True
        assert d["environment"]["hit"] is True

    def test_video_and_image_share_keywords(self):
        from prompt_engine.evaluator import evaluate_quality
        kw, _ = load_element_keywords()
        # 图片引擎也应从同一资产加载（模块加载后内部引用一致）
        assert "cinematography" in kw["style"]["en"]   # #52 扩充词在资产中
        # 图片引擎命中扩充词
        r = evaluate_quality("Documentary cinematography with haze and grain. " * 3, {}, "", "en")
        assert r["checks"]["elements"]["style"] is True


# ─────────────────────────── 组6：FP 去重（P1-5） ───────────────────────────

class TestNegativesFpDedupe:
    def test_fp_counted_once_per_sample_key(self):
        # audio_block_missing 与 missing_audio 映射同一违规键：一次误报只归属一次
        samples = [
            # 预期 audio 类 tag，但 evaluate 未触发（miss）
            {"id": "s1", "prompt_text": "A quiet static wide shot. " * 5, "failure_tags": ["missing_audio"], "tier": "batch"},
            # 无预期 tag 却触发了 missing_audio（FP 事件）
            {"id": "s2", "prompt_text": "无声的画面缓缓展开。 " * 6, "failure_tags": ["exposure_break"], "tier": "batch"},
        ]
        out = evaluate_negatives(samples)
        # s2 误触发 missing_audio → FP 归属到映射该键的 tag（missing_audio 或 audio_block_missing 其一）
        assert out["totals"]["false_positives"] == 1
        total_fp = sum(p["false_positives"] for p in out["patterns"].values())
        assert total_fp == 1          # 不再重复累计


# ─────────────────────────── 组7：advice（P2-3） ───────────────────────────

class TestAdvice:
    def test_advice_short_prompt(self):
        r = evaluate("A man. " * 2, {}, "", "zh", tier="batch")
        assert isinstance(r["advice"], list) and r["advice"]
        joined = "".join(r["advice"])
        assert ("长度" in joined) or ("词" in joined)

    def test_advice_language_en(self):
        r = evaluate("A man. " * 2, {}, "", "en", tier="batch")
        joined = " ".join(r["advice"])
        assert "length" in joined.lower() or "words" in joined.lower()

    def test_advice_violation(self):
        r = evaluate("无声的画面缓缓展开。 " * 6, {}, "", "zh", tier="batch")
        assert any("音频" in a for a in r["advice"])

    def test_advice_can_be_disabled(self):
        r = evaluate("A man walks in the city. " * 6, {}, "", "en", tier="batch", enable_advice=False)
        assert r["advice"] == []


# ─────────────────────────── 组1.4：select_best tie-break（P1-3） ───────────────────────────

class TestSelectBestTieBreak:
    def test_same_score_fewer_violations_wins(self, monkeypatch):
        # 真同分：score 相同、违规数不同 → 违规少者胜（P1-3 tie-break，评审 W5 修复）
        import video_prompt_engine.evaluator as ev

        def fake_evaluate(prompt, video, **kwargs):
            if str(prompt).startswith("CLEAN"):
                return {"score": 90.0, "violations": {}}
            return {"score": 90.0, "violations": {"missing_audio": -5}}

        monkeypatch.setattr(ev, "evaluate", fake_evaluate)
        best_prompt, _, _ = select_best([("DIRTY-1", {}), ("CLEAN-2", {})], "", "en", tier="batch")
        assert best_prompt == "CLEAN-2"

    def test_same_score_same_violations_first_wins(self, monkeypatch):
        # 同分同违规 → 先出现者胜（稳定）
        import video_prompt_engine.evaluator as ev

        def fake_evaluate(prompt, video, **kwargs):
            return {"score": 90.0, "violations": {}}

        monkeypatch.setattr(ev, "evaluate", fake_evaluate)
        best_prompt, _, _ = select_best([("FIRST", {}), ("SECOND", {})], "", "en", tier="batch")
        assert best_prompt == "FIRST"
# ─────────────────────────── 组8：/v1/video/evaluate 端点（P2-4） ───────────────────────────

class TestEvaluateEndpoint:
    def _client(self):
        from fastapi.testclient import TestClient
        from video_prompt_engine.api.rest import app
        return TestClient(app)

    def test_evaluate_endpoint_basic(self):
        client = self._client()
        r = client.post("/v1/video/evaluate", json={
            "prompts": ["A hero in the city. " * 8], "language": "en",
        })
        assert r.status_code == 200
        data = r.json()
        assert data["meta"]["count"] == 1
        assert data["meta"]["evaluator"] == "v0.10-deterministic"
        res = data["results"][0]
        assert 0 <= res["score"] <= 100
        assert res["tier"] in ("batch", "refined", "asset", "variant")
        assert res["form"] == "asset"          # <100 词 → asset 形态
        assert "checks" in res and "violations" in res
        assert isinstance(res["advice"], list) and res["advice"]

    def test_evaluate_endpoint_detail_off(self):
        client = self._client()
        r = client.post("/v1/video/evaluate", json={
            "prompts": ["A hero in the city. " * 8], "detail": False,
        })
        assert r.status_code == 200
        res = r.json()["results"][0]
        assert "advice" not in res
        assert "compare" not in res

    def test_evaluate_endpoint_compare_delta(self):
        client = self._client()
        before = "A hero in the city. " * 8
        after = "A hero in the city, neon light, cinematic, dolly shot. " * 8
        r = client.post("/v1/video/evaluate", json={
            "prompts": [after], "compare": [before], "language": "en",
        })
        assert r.status_code == 200
        cmp = r.json()["results"][0]["compare"]
        assert cmp["score_delta"] > 0
        assert "elements" in cmp["by_criterion"]
        assert "motion" in cmp["by_criterion"]   # dolly 镜头运动

    def test_evaluate_endpoint_compare_mismatch_422(self):
        client = self._client()
        r = client.post("/v1/video/evaluate", json={
            "prompts": ["a" * 50, "b" * 50], "compare": ["x" * 50],
        })
        assert r.status_code == 422

    def test_evaluate_endpoint_empty_prompt_422(self):
        client = self._client()
        r = client.post("/v1/video/evaluate", json={"prompts": ["   "]})
        assert r.status_code == 422

    def test_evaluate_endpoint_too_many_422(self):
        client = self._client()
        r = client.post("/v1/video/evaluate", json={"prompts": ["x" * 50] * 21})
        assert r.status_code == 422

    def test_evaluate_endpoint_zh_advice(self):
        client = self._client()
        r = client.post("/v1/video/evaluate", json={
            "prompts": ["无声的画面缓缓展开。 " * 6], "language": "zh",
        })
        assert r.status_code == 200
        res = r.json()["results"][0]
        assert any("音频" in a for a in res["advice"])


# ─────────────────────────── 组9：词表资产一致性（评审 W2/W10 修复） ───────────────────────────

class TestElementAssetConsistency:
    def test_fallback_matches_asset(self):
        import json as _json
        from pathlib import Path as _Path
        from prompt_engine_core import knowledge as _k

        asset = _json.loads(
            (_Path(_k.__file__).resolve().parent / "knowledge" / "element_keywords.json").read_text(encoding="utf-8")
        )
        assert _k._ELEMENT_KEYWORDS_FALLBACK == asset["elements"]

    def test_loader_accepts_extended_elements(self, tmp_path):
        # 资产允许扩展第 7 要素（校验只要求必含 6 键 + 各语言列表非空）
        import json as _json
        from prompt_engine_core.knowledge import load_element_keywords

        data = {
            "elements": {
                k: {"en": ["w"], "zh": ["词"], "ru": ["с"]}
                for k in ("subject", "action", "environment", "lighting", "color", "style")
            }
        }
        data["elements"]["extra"] = {"en": ["x"], "zh": ["新"], "ru": ["х"]}
        p = tmp_path / "kw.json"
        p.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
        kw, from_asset = load_element_keywords(str(p))
        assert from_asset and "extra" in kw

    def test_empty_language_list_rejected(self, tmp_path):
        import json as _json
        from prompt_engine_core.knowledge import load_element_keywords

        data = {
            "elements": {
                k: {"en": ["w"], "zh": ["词"], "ru": ["с"]}
                for k in ("subject", "action", "environment", "lighting", "color", "style")
            }
        }
        data["elements"]["subject"]["ru"] = []
        p = tmp_path / "kw2.json"
        p.write_text(_json.dumps(data, ensure_ascii=False), encoding="utf-8")
        _kw, from_asset = load_element_keywords(str(p))
        assert from_asset is False


# ─────────────────────────── 组10：词干/中文 form（评审复验 W1-新/W3-新修复） ───────────────────────────

class TestFidelityStem:
    def test_run_plural_tense_match(self):
        # motivating case：run→runs 词形归一命中（W3-新修复）
        r = evaluate("The hero run in the snow. " * 4, {}, source_prompt="The hero runs in the snow.",
                     language="en", tier="batch")
        assert r["checks"]["fidelity"] == 1.0

    def test_running_doubled_consonant_match(self):
        # running→run 双写辅音归并命中
        r = evaluate("The hero running in the snow. " * 4, {}, source_prompt="The hero run in the snow.",
                     language="en", tier="batch")
        assert r["checks"]["fidelity"] == 1.0

    def test_stares_does_not_hit_star(self):
        # 假阳性回归：stares→stare 不得撞 star（W3-新修复）
        r = evaluate("A bright star in the dark sky. " * 4, {}, source_prompt="She stares at the horizon.",
                     language="en", tier="batch")
        assert r["checks"]["fidelity"] == 0.0

    def test_zh_form_uses_chars_not_words(self):
        # 中文 form 用字符数（measure），长中文不再误判 asset（W1-新修复）
        zh = "一位将军在雪地中缓慢行走，镜头缓缓推近。" * 20
        r = evaluate(zh, {}, language="zh", tier="batch")
        assert r["checks"]["form"] == "regular"
