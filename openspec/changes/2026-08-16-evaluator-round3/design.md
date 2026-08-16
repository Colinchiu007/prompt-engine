# 评估器 round3 — 技术设计

## 1. zh/ru 长度兜底（P0-1）

```python
def detect_tier(prompt, video=None, explicit_tier=None, max_length=None, language="en"):
    ...
    if language in ("zh", "ru"):
        if len(str(prompt)) > 2000:            # 与 zh/ru batch 带上界联动（evaluator.py:686）
            return "refined"
    elif count_words(prompt) > _batch_hi(max_length):
        return "refined"
```

- `evaluate()` 内：`length_fallback` 并入同条件；`checks["tier_auto"]="length"`；`trailer_waiver` 同条件豁免（防 missing_trailer=-10 误伤）。
- language 判定函数 `_detect_lang(text)`：含 CJK → zh；含西里尔 → ru；否则 en（与 258 哨兵脚本三路判定共用，抽到共享 util 或各自实现并同步）。
- missing_audio 耦合修（refined 分支）：`_AUDIO_INTENT_WORDS` 扩 zh：音效/环境声/雨声/配乐/旁白/对话/音乐/背景音乐/风声/枪声；扩 ru：звук/музыка/речь/голос/диалог/эффект。
- 边界记录：refined hi 固定 `max_length or 5000`，5200+ 字中文仍 0 分（残余边界，docstring 注明）。

## 2. CJK 单字词表 v3（P0-2）

原则：**显式合成词表替代单字子串**；subject 保留「人」（四人/每人/有人 误击率低）。`element_keywords.json` version 2→3。

| 要素 | 移除单字 | 新增合成词 |
|---|---|---|
| subject | —（保留 人） | 人物/男人/女人/男子/少年/青年/老人 |
| action | 飞奔战走跑追舞骑立坐望持挥攻 | 飞翔/飞行/飞奔/奔跑/战斗/作战/行走/走出/走近/走进/跑步/追逐/追赶/追捕/追上/舞蹈/跳舞/骑马/站立/站起/坐下/凝视/注视/遥望/眺望/手持/挥舞/挥动/攻击/进攻/飞溅/飞过（不放 追踪/追拍） |
| environment | 室/城/景 | 室内/室外/城市/城堡/背景/前景/场景/景色/景观/夜景（不放 中景/近景/远景） |
| lighting | 光 | 光线/光源/灯光/阳光/月光/日光/烛光/火光/主光/暖光/冷光/白光/红光/蓝光/绿光/荧光/微光/亮光/发光/闪光/辉光/逆光/霓虹/光晕/光束 |
| color | 色/灰/红/蓝/绿/金/黑/白 | 色彩/色调/颜色/配色/色温/灰色/灰白/银灰/红色/绯红/鲜红/暗红/血红/橙红/蓝色/湛蓝/深蓝/淡蓝/蔚蓝/绿色/翠绿/深绿/橄榄绿/金色/金黄/铂金/黑色/漆黑/墨黑/乌黑/白色/纯白/雪白/苍白/黑白 |
| style | —（无单字） | 不动 |

- 动词多形态必须齐收（走出/走近/走过/飞过…），防召回损失。
- 反例必须通过：角色→非 color；曝光/时光→非 lighting；金属→非 color；中景/远景→非 environment；绝望→非 action；战术→非 action。
- round2 测试 `test_zh_words_keep_substring`（"室内灯光下，将军站着"）语义升级为合成词命中，断言不破。
- 可选 P2-2：en 短卡词表补 demon/painting/illustration/orb/hellscape（golden 地板缺口）。

## 3. 258 哨兵脚本（P0-3）

- `scripts/eval_corpus_258.py`：固定路径 `video_prompt_engine/knowledge/seed_higgsfield_prompts.json`；硬断言 `total==258`；tier=None、length_strict=False；三路语言判定（与 evaluator 共用口径）；输出 n/mean/median/ge90/ge80/lt60/missing_audio + `--json`；退出码 0/1/2。
- 门禁阈值（首版宽带宽）：mean≥88.0、ge90≥190、lt60≤30、missing_audio≤40；落地 round3 后重定基再收紧（写死当前值）。
- CI：test.yml 独立 step `python scripts/eval_corpus_258.py`，`timeout-minutes: 10`。
- 路径定位 `Path(__file__).resolve().parent.parent`，禁相对路径。

## 4. 正则缓存（P1-1）

```python
@lru_cache(maxsize=2048)
def _WORD_BOUNDARY_RE(token): ...   # 键仅 token
@lru_cache(maxsize=2048)
def _CYRILLIC_BOUNDARY_RE(token): ...
```

- 不动 flags 参数（两函数固定 IGNORECASE）；re.Pattern 无 mutation，缓存安全。
- maxsize=2048 防动态 token（跨镜承接/角色名）无界膨胀；淘汰后重编译正确性不变。

## 5. 镜头 instrumentation（P1-2）

- `checks["shot_types"]/["camera_types"]/["motion_types"]` + `_count`；仅输出不改分。
- 分型词表（保守）：wide（wide/establishing/panoramic/aerial/全景/远景）、medium（medium/mid-shot/mid shot/中景）、closeup（close-up/macro/insert/特写/近景/微距）、overhead（overhead/top-down/bird's eye/俯拍/航拍）、lowangle（low-angle/worm's eye/仰拍/低机位）、tracking（tracking/dolly/follow shot/跟拍/推移）、static（static shot/static camera/locked-off/固定机位/静止镜头）；禁用裸 still/extreme/摇（评审 I5：裸 wide/aerial 保留为景别核心词，文档措辞与实现同步）；cam_position 不含裸 view（评审 I4：「a beautiful view of the city」假阳性）。
- 运镜型（pan/tilt/tracking/zoom/crane/handheld/slomo/rotate/drift）归 motion_types；tracking/dolly/跟拍/推移 为景别-运镜双属特例（评审 I6）。
- 否定感知（评审 W1）：按分句全出现语义——复用 `_occurrence_is_negated`（与 `_negated` 一致），「tracking shot, but no tracking in the second half」前半正向不误抑；拉丁/CJK 通用（无/不/没有/禁止/切勿/避免 均覆盖）。
- 与 video meta 字段（video.shot/camera/motion_intensity）合并输出（meta 有值直接并入 types）。
- 分数梯度 0/20/20 备选（只惩罚「说 shot 无景别」）——golden 零影响，但本轮默认不启用。

## 6. 无 source 缩放封顶（P2-1）

```python
score = (length_points + elements_score*30 + shot + cam + mot + fidelity*20) / 1.2 + sum(violations.values())
if not source_prompt:
    score = min(score, 90 + 7 * checks["elements_score"])
return {"score": round(max(0, min(100, score)), 1), ...}
```

- 100 保留给保真已验证；无 source 最高 97（elements_score=1.0 时）。
- `elements_score` 双重使用（主公式 + ceiling 缩放）在 docstring 注明；未来权重调整 ceiling 自动跟随。
- 快照断言（实测 2026-08-16）：hg-scene_74-020（elem 1.0）→ 97.0（恰落封顶）；hg-scene_74-011（elem 0.833）→ 95.8（cap 95.83）；短卡 4 条维持 43.1/44.4/55.6/39.7 不塌；带 source 保真 1.0 → 100。
- 封顶验收口径（修正版）：7 条封顶样本全部 ≤97、不再顶格 100，且随 elements_score 单调分层（95.8-97.0 分布）——「两两不等」因 golden 样本 elements 覆盖率相近不可达，以分层分布为准。
- round4 主题记录：短卡地板（en 词表 + asset/variant 层镜头权重 tier-aware）。

## 版本与指纹

- `_EVALUATOR_VERSION = "v0.12-deterministic"`；词表 version 4 随 `_asset_fingerprint` 自动反映；rest.py meta 复用常量。

## 评审修复（Round3 Review 2026-08-16，C1+W1-W6+I 系列）

- **C1 CI 超时结构**：`test.yml` job 级 `timeout-minutes 5→15`（哨兵 step 10 分钟上限不再被 job 罩死）。
- **W1 否定分句化**：`_TYPE_NEGATION_RE` 删除，`_type_token_negated` 复用 `_occurrence_is_negated` 全出现分句语义。
- **W2 zh 动作形态**：v3→v4 补 走着/走起/走来/跑去/跑来/挥手/望着/坐着/看着/站住/站定（JSON + knowledge.py fallback 同步）。
- **W3 音频词单表**：refined 分支复用 `_AUDIO_INTENT_WORDS`（补 en dialogue/voiceover/narration/vocal + zh 环境声/雨声/风声/枪声 + ru 词）。
- **W4 API 语言自动判定**：`VideoEvaluateRequest.language` 默认 None；`/v1/video/evaluate` 逐条 `detect_lang` 自动判定（共享 util，与哨兵同口径）。
- **W5 language 归一化**：`evaluate()`/`detect_tier()` 入口 `str(language or "en").lower()[:2]`，zh-CN/EN 统一口径。
- **W6 阈值单一来源**：`_CHAR_BATCH_HI = 2000` 常量（detect_tier / length_fallback / batch 分带三处共用）。
- I1 哨兵输入损坏返回 2；I2/I3 封顶/地板测试改为真实绑定断言（score==cap、4 条短卡地板快照）；I4 cam_position 去裸 view；I5/I6 文档措辞同步；I7 Impact 补充图片引擎共享影响；I8/I9 注释与换行。
- 回归证据：全量 947→（评审后复跑）通过；golden MAE 14.85 / r 0.920 与 258 四指标（91.0/216/225/20/20）均与重定基值一致（零回归）。
